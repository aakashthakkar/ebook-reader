import os
import io
import logging
from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import PyPDF2
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

def extract_text_from_pdf_bytes(file_bytes):
    """Extract text from PDF bytes using multiple methods for better accuracy"""
    text = ""
    
    try:
        # Method 1: Using pdfplumber (better for complex layouts)
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
    
    try:
        # Method 2: Using PyPDF2 as fallback
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        logger.warning(f"PyPDF2 failed: {e}")
    
    return text.strip()

def extract_text_from_pdf(file_path):
    """Extract text from PDF using multiple methods for better accuracy"""
    text = ""
    
    try:
        # Method 1: Using pdfplumber (better for complex layouts)
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        if text.strip():
            return text.strip()
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
    
    try:
        # Method 2: Using PyPDF2 as fallback
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        logger.warning(f"PyPDF2 failed: {e}")
    
    return text.strip()

async def generate_audio_edge_tts_async(text, voice_id):
    """Generate audio using Edge TTS asynchronously"""
    try:
        logger.info(f"Generating audio with Edge TTS ({voice_id}) for text: {text[:50]}...")
        
        # Create temporary file for audio output
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Generate audio
        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(temp_path)
        
        # Read the generated audio file and convert to WAV format
        audio_data, sample_rate = sf.read(temp_path)
        
        # Clean up temporary file
        os.unlink(temp_path)
        
        logger.info(f"Edge TTS completed: {len(audio_data)} samples at {sample_rate}Hz")
        return audio_data, sample_rate
        
    except Exception as e:
        logger.error(f"Error with Edge TTS: {e}")
        raise

def generate_audio_edge_tts_sync(text, voice_id):
    """Synchronous wrapper for Edge TTS"""
    # Create new event loop for this thread
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
    """Handle PDF file upload and text extraction"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Please upload a PDF file'}), 400
        
        # Process PDF directly from memory
        file_bytes = file.read()
        text = extract_text_from_pdf_bytes(file_bytes)
        
        if not text:
            return jsonify({'error': 'Could not extract text from PDF'}), 400
        
        return jsonify({
            'text': text,
            'filename': file.filename,
            'text_length': len(text)
        })
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-audio', methods=['POST'])
def generate_audio():
    """Generate audio using Edge TTS"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        model_key = data.get('model', 'edge-tts-andrew')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        if len(text) > 10000:  # Reasonable limit for single request
            return jsonify({'error': 'Text too long for single request'}), 400
        
        # Get voice configuration
        if model_key not in Config.AVAILABLE_MODELS:
            return jsonify({'error': 'Invalid model selected'}), 400
        
        voice_config = Config.AVAILABLE_MODELS[model_key]
        voice_id = voice_config['voice_id']
        
        # Generate audio with Edge TTS
        logger.info(f"Generating audio with {voice_id} for {len(text)} characters")
        audio_data, sample_rate = generate_audio_edge_tts_sync(text, voice_id)
        
        # Convert audio to base64
        buffer = io.BytesIO()
        sf.write(buffer, audio_data, sample_rate, format='WAV')
        audio_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        # Calculate duration
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