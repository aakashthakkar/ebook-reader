import os
import io
import json
import logging
from flask import Flask, request, render_template, jsonify, redirect, url_for, make_response
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
from auth_service import auth_service, token_required

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

# Authentication Routes
@app.route('/')
def index():
    """Redirect to login page"""
    return redirect(url_for('login'))

@app.route('/login')
def login():
    """Serve the login page"""
    return render_template('login.html')

@app.route('/signup')
def signup():
    """Serve the signup page"""
    return render_template('signup.html')

@app.route('/app')
def app_main():
    """Serve the main app (protected)"""
    return render_template('index.html', models=Config.AVAILABLE_MODELS)

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Handle user login"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        result = auth_service.authenticate_user(email, password)
        if 'error' in result:
            return jsonify(result), 401
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Authentication failed'}), 500

@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    """Handle user signup"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        result = auth_service.create_user(email, password, name)
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return jsonify({'error': 'Registration failed'}), 500

@app.route('/api/user/pdfs', methods=['GET'])
@token_required
def get_user_pdfs():
    """Get all PDFs for the current user"""
    try:
        user_id = request.current_user['id']
        result = auth_service.get_user_pdfs(user_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting user PDFs: {e}")
        return jsonify({'error': 'Failed to get PDFs'}), 500

@app.route('/api/upload', methods=['POST'])
@token_required
def upload_file():
    """Handle PDF file upload and extract word data (protected route)."""
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
        
        # Save PDF to user's storage
        user_id = request.current_user['id']
        filename = secure_filename(file.filename)
        
        pdf_result = auth_service.save_user_pdf(user_id, filename, file_bytes)
        if 'error' in pdf_result:
            logger.warning(f"Failed to save PDF to storage: {pdf_result['error']}")
            # Continue anyway for now, just log the error
        
        return jsonify({
            'words': words_data,
            'filename': filename,
            'word_count': len(words_data),
            'file_id': pdf_result.get('pdf', {}).get('file_id') if 'pdf' in pdf_result else None
        })
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        traceback.print_exc()
        return jsonify({'error': 'An unexpected error occurred during processing.'}), 500

@app.route('/api/generate-audio', methods=['POST'])
@token_required
def generate_audio():
    """Generate audio using Edge TTS (protected route)"""
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

@app.route('/api/reading-progress', methods=['GET', 'POST'])
@token_required
def reading_progress():
    """Get or update reading progress for a PDF"""
    try:
        user_id = request.current_user['id']
        
        if request.method == 'GET':
            pdf_id = request.args.get('pdf_id')
            if not pdf_id:
                return jsonify({'error': 'PDF ID is required'}), 400
            
            result = auth_service.get_reading_progress(user_id, pdf_id)
            return jsonify(result)
        
        elif request.method == 'POST':
            data = request.get_json()
            pdf_id = data.get('pdf_id')
            current_page = data.get('current_page')
            current_word_index = data.get('current_word_index')
            total_words = data.get('total_words')
            
            if not all([pdf_id, current_page is not None, current_word_index is not None, total_words]):
                return jsonify({'error': 'All progress fields are required'}), 400
            
            result = auth_service.update_reading_progress(
                user_id, pdf_id, current_page, current_word_index, total_words
            )
            return jsonify(result)
    
    except Exception as e:
        logger.error(f"Reading progress error: {e}")
        return jsonify({'error': 'Failed to handle reading progress'}), 500

@app.route('/api/reading-progress-beacon', methods=['POST'])
def reading_progress_beacon():
    """Handle reading progress updates from navigator.sendBeacon (no auth required)"""
    try:
        # Get auth token from form data
        auth_token = request.form.get('auth_token')
        progress_data_str = request.form.get('progress_data')
        
        if not auth_token or not progress_data_str:
            return jsonify({'error': 'Missing token or progress data'}), 400
        
        # Verify token manually since we can't use the decorator
        result = auth_service.verify_token(auth_token)
        if 'error' in result:
            return jsonify({'error': 'Invalid token'}), 401
        
        user_id = result['user']['id']
        progress_data = json.loads(progress_data_str)
        
        pdf_id = progress_data.get('pdf_id')
        current_page = progress_data.get('current_page')
        current_word_index = progress_data.get('current_word_index')
        total_words = progress_data.get('total_words')
        
        if not all([pdf_id, current_page is not None, current_word_index is not None, total_words]):
            return jsonify({'error': 'All progress fields are required'}), 400
        
        result = auth_service.update_reading_progress(
            user_id, pdf_id, current_page, current_word_index, total_words
        )
        
        return jsonify({'success': True})
    
    except Exception as e:
        logger.error(f"Beacon reading progress error: {e}")
        return jsonify({'error': 'Failed to handle beacon progress'}), 500

@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify_auth():
    """Verify authentication token"""
    return jsonify({
        'success': True,
        'user': {
            'id': request.current_user['id'],
            'email': request.current_user['email'],
            'name': request.current_user['name']
        }
    })

@app.route('/api/user/pdfs/<file_id>', methods=['GET'])
@token_required
def get_user_pdf_file(file_id):
    """Get PDF file content for the current user"""
    try:
        user_id = request.current_user['id']
        result = auth_service.get_user_pdf_file(user_id, file_id)
        
        if 'error' in result:
            return jsonify(result), 404
        
        file_data = result['file_data']
        metadata = result['metadata']
        
        response = make_response(file_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename="{metadata["filename"]}"'
        response.headers['Content-Length'] = len(file_data)
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting PDF file: {e}")
        return jsonify({'error': 'Failed to get PDF file'}), 500

@app.route('/api/user/pdfs/<file_id>', methods=['DELETE'])
@token_required
def delete_user_pdf_file(file_id):
    """Delete PDF file for the current user"""
    try:
        user_id = request.current_user['id']
        result = auth_service.delete_user_pdf(user_id, file_id)
        
        if 'error' in result:
            return jsonify(result), 404
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error deleting PDF file: {e}")
        return jsonify({'error': 'Failed to delete PDF file'}), 500

@app.route('/api/user/pdfs/<file_id>/words', methods=['GET'])
@token_required
def get_pdf_words(file_id):
    """Get cached word data for a PDF"""
    try:
        # For now, we'll return empty since we don't cache words yet
        # In a full implementation, you'd cache the word extraction results
        # This endpoint allows the frontend to check if cached data exists
        return jsonify({'words': [], 'cached': False})
        
    except Exception as e:
        logger.error(f"Error getting PDF words: {e}")
        return jsonify({'error': 'Failed to get PDF words'}), 500

@app.route('/api/extract-words', methods=['POST'])
@token_required
def extract_words_only():
    """Extract words from PDF without saving the file"""
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
            'word_count': len(words_data)
        })
    
    except Exception as e:
        logger.error(f"Extract words error: {e}")
        return jsonify({'error': 'An unexpected error occurred during processing.'}), 500

if __name__ == '__main__':
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT) 