import os
import io
import logging
from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pdfplumber
import soundfile as sf
import tempfile
import traceback
from config import Config
import asyncio
import numpy as np
import edge_tts
import base64

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Load configuration
app.config.from_object(Config)
Config.init_app(app)

def extract_words_from_pdf_bytes(file_bytes):
    """Extract words and their coordinates from PDF bytes using pdfplumber."""
    all_words = []
    global_word_index = 0
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Use extract_words to get precise coordinate data for each word.
                words = page.extract_words(x_tolerance=2, use_text_flow=True)
                
                for word in words:
                    all_words.append({
                        "text": word["text"],
                        "page": page_num + 1,
                        "index": global_word_index,
                        "x": float(word["x0"]),
                        "y": float(word["top"]),
                        "width": float(word["x1"] - word["x0"]),
                        "height": float(word["bottom"] - word["top"]),
                        "page_width": float(page.width),
                        "page_height": float(page.height)
                    })
                    global_word_index += 1
    except Exception as e:
        logger.error(f"pdfplumber failed to extract words: {e}")
        return None
    return all_words

async def generate_audio_edge_tts_async(text, voice_id):
    """Generate audio using Edge TTS asynchronously"""
    try:
        logger.info(f"Generating audio with Edge TTS ({voice_id}) for text: {text[:50]}...")
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_path = temp_file.name
        
        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(temp_path)
        
        audio_data, sample_rate = sf.read(temp_path)
        
        os.unlink(temp_path)
        
        logger.info(f"Edge TTS completed: {len(audio_data)} samples at {sample_rate}Hz")
        return audio_data, sample_rate
        
    except Exception as e:
        logger.error(f"Error with Edge TTS: {e}")
        raise

def generate_audio_edge_tts_sync(text, voice_id):
    """Synchronous wrapper for Edge TTS"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(generate_audio_edge_tts_async(text, voice_id))
    except Exception as e:
        logger.error(f"Error in Edge TTS sync wrapper: {e}")
        raise

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html', models=Config.AVAILABLE_MODELS)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle PDF file upload and extract word data."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Please upload a PDF file'}), 400
        
        file_bytes = file.read()
        words_data = extract_words_from_pdf_bytes(file_bytes)
        
        if words_data is None:
            return jsonify({'error': 'Could not extract words from PDF'}), 500
        
        return jsonify({
            'words': words_data,
            'filename': secure_filename(file.filename),
            'word_count': len(words_data)
        })
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        traceback.print_exc()
        return jsonify({'error': 'An unexpected error occurred during processing.'}), 500

@app.route('/api/generate-audio', methods=['POST'])
def generate_audio():
    """Generate audio using Edge TTS"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        model_key = data.get('model', 'edge-tts-andrew')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        if len(text) > 10000:
            return jsonify({'error': 'Text too long for single request'}), 400
        
        if model_key not in Config.AVAILABLE_MODELS:
            return jsonify({'error': 'Invalid model selected'}), 400
        
        voice_config = Config.AVAILABLE_MODELS[model_key]
        voice_id = voice_config['voice_id']
        
        logger.info(f"Generating audio with {voice_id} for {len(text)} characters")
        audio_data, sample_rate = generate_audio_edge_tts_sync(text, voice_id)
        
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, sample_rate, format='WAV')
        audio_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        duration = len(audio_data) / sample_rate
        
        logger.info(f"Generated audio: {duration:.2f}s, {len(audio_data)} samples")
        
        return jsonify({
            'success': True,
            'audio_data': audio_base64,
            'sample_rate': sample_rate,
            'duration': duration,
            'text': text,
            'voice_used': voice_config['name']
        })
        
    except Exception as e:
        logger.error(f"Generate audio error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT) 