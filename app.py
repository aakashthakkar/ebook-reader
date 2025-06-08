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
    """Extract words and their coordinates from PDF bytes using pdfplumber with paragraph detection."""
    all_words = []
    global_word_index = 0
    global_paragraph_id = 0
    
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Extract words with precise coordinate data
                words = page.extract_words(x_tolerance=2, use_text_flow=True)
                
                if not words:
                    continue
                
                # Detect paragraph boundaries using line spacing and positioning
                paragraphs = detect_paragraphs_in_page(words)
                
                for paragraph in paragraphs:
                    for word in paragraph['words']:
                        all_words.append({
                            "text": word["text"],
                            "page": page_num + 1,
                            "index": global_word_index,
                            "paragraph_id": global_paragraph_id,
                            "paragraph_start": word.get("paragraph_start", False),
                            "paragraph_end": word.get("paragraph_end", False),
                            "x": float(word["x0"]),
                            "y": float(word["top"]),
                            "width": float(word["x1"] - word["x0"]),
                            "height": float(word["bottom"] - word["top"]),
                            "page_width": float(page.width),
                            "page_height": float(page.height)
                        })
                        global_word_index += 1
                    global_paragraph_id += 1
                    
    except Exception as e:
        logger.error(f"pdfplumber failed to extract words: {e}")
        return None
    return all_words

def detect_paragraphs_in_page(words):
    """Detect paragraph boundaries using smart whitespace analysis - works for any PDF type."""
    if not words:
        return []
    
    paragraphs = []
    current_paragraph = []
    
    # Group words by approximate lines first
    lines = group_words_by_lines(words)
    
    # Calculate common horizontal alignment zones for better paragraph detection
    left_margins = [line[0]["x0"] for line in lines if line]
    common_margins = {}
    for margin in left_margins:
        # Group similar margins (within 5px)
        found_group = False
        for existing_margin in common_margins:
            if abs(margin - existing_margin) <= 5:
                common_margins[existing_margin] += 1
                found_group = True
                break
        if not found_group:
            common_margins[margin] = 1
    
    # Find the most common alignment (main text alignment)
    main_text_margin = max(common_margins.keys(), key=common_margins.get) if common_margins else 0
    
    for line_idx, line_words in enumerate(lines):
        if not line_words:
            continue
            
        # Check if this line starts a new paragraph
        is_new_paragraph = False
        
        if line_idx == 0:
            # First line is always start of a paragraph
            is_new_paragraph = True
        else:
            prev_line = lines[line_idx - 1] if line_idx > 0 else []
            
            if prev_line:
                # Check if previous line appears incomplete (likely continues to this line)
                prev_line_text = ' '.join(word["text"] for word in prev_line).strip()
                current_line_text = ' '.join(word["text"] for word in line_words).strip()
                
                # If previous line seems incomplete, don't break here
                if is_incomplete_line(prev_line_text, current_line_text):
                    is_new_paragraph = False
                else:
                    # ENHANCED HORIZONTAL ALIGNMENT CHECK
                    # If current line is aligned with main text body, consider it a continuation
                    current_margin = line_words[0]["x0"]
                    prev_margin = prev_line[0]["x0"]
                    
                    # Check if both lines are aligned with main text (likely continuation)
                    both_main_aligned = (abs(current_margin - main_text_margin) <= 8 and 
                                       abs(prev_margin - main_text_margin) <= 8)
                    
                    if both_main_aligned:
                        # Both lines are main text aligned - be more conservative about splitting
                        # Only split if there are very strong spatial indicators
                        if (has_aggressive_vertical_spacing(line_words, prev_line) and
                            has_significant_indentation_change(line_words, prev_line, main_text_margin)):
                            is_new_paragraph = True
                        elif is_clear_paragraph_break(prev_line, line_words):
                            is_new_paragraph = True
                    else:
                        # SMART WHITESPACE-BASED PARAGRAPH DETECTION (original logic for non-aligned text)
                        
                        # 1. Vertical spacing - balanced threshold
                        if has_aggressive_vertical_spacing(line_words, prev_line):
                            is_new_paragraph = True
                        
                        # 2. Horizontal indentation changes - significant shifts
                        elif has_indentation_change(line_words, prev_line):
                            is_new_paragraph = True
                        
                        # 3. Line length analysis - short lines often indicate paragraph breaks
                        elif is_short_line_break(prev_line, line_words):
                            is_new_paragraph = True
                        
                        # 4. Font size or formatting changes (if available)
                        elif has_formatting_change(line_words, prev_line):
                            is_new_paragraph = True
        
        if is_new_paragraph and current_paragraph:
            # Mark the end of the previous paragraph
            if current_paragraph:
                current_paragraph[-1]["paragraph_end"] = True
            
            # Save the previous paragraph
            paragraphs.append({
                'words': current_paragraph,
                'paragraph_id': len(paragraphs)
            })
            current_paragraph = []
        
        # Mark paragraph start
        if is_new_paragraph and line_words:
            line_words[0]["paragraph_start"] = True
        
        # Add all words from this line to current paragraph
        current_paragraph.extend(line_words)
    
    # Don't forget the last paragraph
    if current_paragraph:
        current_paragraph[-1]["paragraph_end"] = True
        paragraphs.append({
            'words': current_paragraph,
            'paragraph_id': len(paragraphs)
        })
    
    return paragraphs

def is_incomplete_line(prev_line_text, current_line_text):
    """Detect if the previous line is incomplete and continues to the current line - GENERIC for any PDF type."""
    if not prev_line_text or not current_line_text:
        return False
    
    # CONSERVATIVE APPROACH: Only split when there are STRONG indicators
    # Don't split based on punctuation alone - rely primarily on spatial analysis
    
    # Very strong indicators that previous line is incomplete
    strong_incomplete_endings = [
        # Punctuation that clearly indicates continuation
        ',', ';', ':', '(', '"', "'", '-', '—', '–',
        # Words that clearly indicate incomplete thoughts
        'and', 'or', 'but', 'the', 'of', 'in', 'to', 'for', 'with', 'by', 'at', 'on', 'from',
        # Conjunctions and transitions that need continuation
        'if', 'because', 'since', 'while', 'although', 'though', 'unless', 'until', 'before', 'after', 'when', 'where', 'how', 'why'
    ]
    
    # Check if previous line ends with clear incomplete indicators
    prev_clearly_incomplete = any(prev_line_text.lower().endswith(' ' + ending) or prev_line_text.endswith(ending) 
                                 for ending in strong_incomplete_endings)
    
    # Very strong indicators that current line is a continuation  
    strong_continuation_starts = [
        # Punctuation that clearly continues previous line
        ')', '"', "'", '.', ',', ';',
        # Words that clearly continue previous thought
        'and', 'or', 'but', 'so', 'yet', 'then', 'however', 'therefore', 'moreover', 'furthermore'
    ]
    
    # Check if current line clearly starts a continuation
    current_clearly_continues = any(current_line_text.lower().startswith(start + ' ') or current_line_text.startswith(start)
                                   for start in strong_continuation_starts)
    
    # Strong indicator: current line starts with lowercase (very likely continuation)
    current_starts_lowercase = current_line_text and current_line_text[0].islower()
    
    # Return True only for CLEAR continuation indicators
    # This makes the algorithm rely more on spatial analysis rather than text patterns
    return (prev_clearly_incomplete or 
            current_clearly_continues or 
            current_starts_lowercase)

def has_aggressive_vertical_spacing(line_words, prev_line):
    """Detect vertical spacing between lines - very aggressive for shorter chunks."""
    if not prev_line or not line_words:
        return False
    
    # Calculate vertical spacing between lines
    prev_line_bottom = max(word["bottom"] for word in prev_line)
    current_line_top = min(word["top"] for word in line_words)
    line_spacing = current_line_top - prev_line_bottom
    
    # Calculate average line height for context
    current_line_height = max(word["bottom"] for word in line_words) - min(word["top"] for word in line_words)
    prev_line_height = max(word["bottom"] for word in prev_line) - min(word["top"] for word in prev_line)
    avg_line_height = (current_line_height + prev_line_height) / 2
    
    # BALANCED threshold: > 1.0x line height
    # This will catch meaningful spacing increases while avoiding over-splitting
    return line_spacing > avg_line_height * 1.0

def has_indentation_change(line_words, prev_line):
    """Detect horizontal indentation changes - very aggressive for shorter chunks."""
    if not prev_line or not line_words:
        return False
    
    current_indent = line_words[0]["x0"]
    prev_indent = prev_line[0]["x0"]
    
    # BALANCED threshold - meaningful indentation changes > 10 pixels
    # This will catch significant indentation while avoiding minor variations
    return abs(current_indent - prev_indent) > 10

def is_short_line_break(prev_line, current_line):
    """Detect paragraph breaks based on line length patterns - very aggressive for shorter chunks."""
    if not prev_line or not current_line:
        return False
    
    # Calculate line widths
    prev_line_width = max(word["x1"] for word in prev_line) - min(word["x0"] for word in prev_line)
    current_line_width = max(word["x1"] for word in current_line) - min(word["x0"] for word in current_line)
    
    # Get page width context (approximate)
    page_width = max(max(word["x1"] for word in prev_line), max(word["x1"] for word in current_line))
    
    # Check if this looks like logical continuation vs paragraph break
    prev_line_text = ' '.join(word["text"] for word in prev_line).strip()
    current_line_text = ' '.join(word["text"] for word in current_line).strip()
    
    # Minimal continuation checking - only the most obvious cases
    continuation_endings = [',', ';', ':', '(', '"', "'", '-']
    logical_continuation = any(prev_line_text.endswith(ending) for ending in continuation_endings)
    
    # Minimal continuation starts - only obvious punctuation
    continuation_starts = [')', '"', "'", '.', ',', ';']
    starts_continuation = any(current_line_text.startswith(start) for start in continuation_starts)
    
    # Don't split only for very obvious continuations
    if logical_continuation or starts_continuation:
        return False
    
    # BALANCED line width thresholds for reasonable chunks
    # Break if previous line is quite short (< 60% of page width) OR
    # there's a significant width difference (> 30%)
    if (prev_line_width < page_width * 0.60 or 
        abs(prev_line_width - current_line_width) > page_width * 0.30):
        return True
    
    return False

def has_formatting_change(line_words, prev_line):
    """Detect formatting changes like font size differences - very aggressive for shorter chunks."""
    if not prev_line or not line_words:
        return False
    
    # Check if word height differs significantly (indicating font size change)
    current_heights = [word["bottom"] - word["top"] for word in line_words]
    prev_heights = [word["bottom"] - word["top"] for word in prev_line]
    
    if current_heights and prev_heights:
        avg_current_height = sum(current_heights) / len(current_heights)
        avg_prev_height = sum(prev_heights) / len(prev_heights)
        
        # BALANCED threshold: > 15% height difference
        # This will catch meaningful font changes while avoiding minor variations
        height_diff_ratio = abs(avg_current_height - avg_prev_height) / max(avg_current_height, avg_prev_height)
        return height_diff_ratio > 0.15
    
    return False

def group_words_by_lines(words, y_tolerance=3):
    """Group words into lines based on their vertical position."""
    if not words:
        return []
    
    # Sort words by vertical position first, then horizontal
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    
    lines = []
    current_line = []
    current_y = None
    
    for word in sorted_words:
        word_y = word["top"]
        
        if current_y is None or abs(word_y - current_y) <= y_tolerance:
            # Same line
            current_line.append(word)
            current_y = word_y if current_y is None else current_y
        else:
            # New line
            if current_line:
                # Sort current line by horizontal position
                current_line.sort(key=lambda w: w["x0"])
                lines.append(current_line)
            current_line = [word]
            current_y = word_y
    
    # Don't forget the last line
    if current_line:
        current_line.sort(key=lambda w: w["x0"])
        lines.append(current_line)
    
    return lines

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

def has_significant_indentation_change(line_words, prev_line, main_text_margin):
    """Detect significant indentation changes relative to main text alignment."""
    if not prev_line or not line_words:
        return False
    
    current_indent = line_words[0]["x0"]
    prev_indent = prev_line[0]["x0"]
    
    # Check for significant deviation from main text margin
    current_deviation = abs(current_indent - main_text_margin)
    prev_deviation = abs(prev_indent - main_text_margin)
    
    # Significant indentation change: either line deviates significantly from main text
    # OR there's a substantial change between the two lines
    significant_deviation = current_deviation > 15 or prev_deviation > 15
    substantial_change = abs(current_indent - prev_indent) > 20
    
    return significant_deviation or substantial_change

def is_clear_paragraph_break(prev_line, current_line):
    """Detect clear paragraph breaks for main-text-aligned lines."""
    if not prev_line or not current_line:
        return False
    
    prev_line_text = ' '.join(word["text"] for word in prev_line).strip()
    current_line_text = ' '.join(word["text"] for word in current_line).strip()
    
    # Very strong paragraph ending indicators
    strong_endings = ['.', '!', '?', ';"', '."', '!"', '?"']
    ends_with_strong = any(prev_line_text.endswith(ending) for ending in strong_endings)
    
    # Strong paragraph starting indicators
    strong_starts = ['Chapter', 'Section', 'Part', 'Book', 'Volume']
    starts_with_strong = any(current_line_text.startswith(start) for start in strong_starts)
    
    # Check if current line starts with capital letter (potential new sentence/paragraph)
    starts_with_capital = current_line_text and current_line_text[0].isupper()
    
    # Calculate line widths for additional context
    page_width = max(max(word["x1"] for word in prev_line), max(word["x1"] for word in current_line))
    prev_line_width = max(word["x1"] for word in prev_line) - min(word["x0"] for word in prev_line)
    
    # Previous line is quite short (likely end of paragraph)
    prev_line_short = prev_line_width < page_width * 0.50
    
    # Clear paragraph break indicators:
    # 1. Previous line ends with strong punctuation AND current starts with capital
    # 2. Previous line is short AND current starts with capital
    # 3. Current line starts with structural elements
    return ((ends_with_strong and starts_with_capital) or
            (prev_line_short and starts_with_capital and ends_with_strong) or
            starts_with_strong)

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
        
        # Cache the extracted words if PDF was saved successfully
        file_id = None
        if 'pdf' in pdf_result and 'file_id' in pdf_result['pdf']:
            file_id = pdf_result['pdf']['file_id']
            cache_result = auth_service.save_word_cache(user_id, file_id, words_data)
            if 'error' not in cache_result:
                logger.info(f"Cached word data for uploaded file {file_id}: {len(words_data)} words")
        
        return jsonify({
            'words': words_data,
            'filename': filename,
            'word_count': len(words_data),
            'file_id': file_id,
            'cached': file_id is not None
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
        user_id = request.current_user['id']
        result = auth_service.get_cached_words(user_id, file_id)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting PDF words: {e}")
        return jsonify({'error': 'Failed to get PDF words'}), 500

@app.route('/api/extract-words', methods=['POST'])
@token_required
def extract_words_only():
    """Extract words from PDF and cache the results"""
    try:
        user_id = request.current_user['id']
        
        # Check if file_id is provided for caching
        file_id = request.form.get('file_id')
        
        # First check if we have cached data for this file
        if file_id:
            cached_result = auth_service.get_cached_words(user_id, file_id)
            if cached_result['cached']:
                logger.info(f"Using cached word data for file {file_id}")
                return jsonify({
                    'words': cached_result['words'],
                    'word_count': cached_result['word_count'],
                    'cached': True,
                    'cached_at': cached_result['cached_at']
                })
        
        # No cache or file_id not provided, extract words from uploaded file
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
        
        # Cache the results if file_id is provided
        if file_id:
            cache_result = auth_service.save_word_cache(user_id, file_id, words_data)
            if 'error' not in cache_result:
                logger.info(f"Cached word data for file {file_id}: {len(words_data)} words")
        
        return jsonify({
            'words': words_data,
            'word_count': len(words_data),
            'cached': False
        })
    
    except Exception as e:
        logger.error(f"Extract words error: {e}")
        return jsonify({'error': 'An unexpected error occurred during processing.'}), 500

if __name__ == '__main__':
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT) 