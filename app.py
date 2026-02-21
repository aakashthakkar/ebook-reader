import os
import io
import json
import logging
import re
from flask import Flask, request, render_template, jsonify, redirect, url_for, make_response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pdfplumber
import soundfile as sf
import tempfile
import traceback
from config import Config
import numpy as np
import base64
from auth_service import auth_service, token_required
from kokoro import KPipeline
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="bs4")

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
    current_line_height = max(word["bottom"] - word["top"] for word in line_words)
    prev_line_height = max(word["bottom"] - word["top"] for word in prev_line)
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

def group_words_by_lines_converted(words, y_tolerance=3):
    """Group words into lines based on their vertical position - for converted word objects."""
    if not words:
        return []
    
    # Sort words by vertical position first, then horizontal
    sorted_words = sorted(words, key=lambda w: (w["y"], w["x"]))
    
    lines = []
    current_line = []
    current_y = None
    
    for word in sorted_words:
        word_y = word["y"]
        
        if current_y is None or abs(word_y - current_y) <= y_tolerance:
            # Same line
            current_line.append(word)
            current_y = word_y if current_y is None else current_y
        else:
            # New line
            if current_line:
                # Sort current line by horizontal position
                current_line.sort(key=lambda w: w["x"])
                lines.append(current_line)
            current_line = [word]
            current_y = word_y
    
    # Don't forget the last line
    if current_line:
        current_line.sort(key=lambda w: w["x"])
        lines.append(current_line)
    
    return lines

def _get_epub_content_items(book):
    """Get content items from EPUB in spine order, handling all item types.
    
    Many EPUBs use text/html with .html extensions which ebooklib classifies as
    ITEM_UNKNOWN rather than ITEM_DOCUMENT. We use the spine for reading order
    and fall back to scanning all HTML-like items.
    """
    items_by_id = {}
    items_by_name = {}
    html_extensions = ('.xhtml', '.html', '.htm', '.xml')
    html_media_types = ('application/xhtml+xml', 'text/html', 'application/html')

    for item in book.get_items():
        item_id = item.get_id() if hasattr(item, 'get_id') else None
        item_name = item.get_name()
        if item_id:
            items_by_id[item_id] = item
        if item_name:
            items_by_name[item_name] = item

    ordered = []
    seen = set()
    for spine_entry in book.spine:
        item_id = spine_entry[0] if isinstance(spine_entry, (list, tuple)) else spine_entry
        item = items_by_id.get(item_id)
        if item and item.get_name() not in seen:
            seen.add(item.get_name())
            ordered.append(item)

    if not ordered:
        for item in book.get_items():
            name = item.get_name()
            media = getattr(item, 'media_type', '') or ''
            is_html = any(name.lower().endswith(ext) for ext in html_extensions) or media in html_media_types
            if is_html and name not in seen:
                seen.add(name)
                ordered.append(item)

    return ordered


def extract_words_from_epub_bytes(file_bytes):
    """Extract words and paragraph structure from EPUB bytes."""
    all_words = []
    global_word_index = 0
    global_paragraph_id = 0
    
    try:
        book = epub.read_epub(io.BytesIO(file_bytes))
        content_items = _get_epub_content_items(book)
        
        chapter_num = 0
        for item in content_items:
            content = item.get_content()
            soup = BeautifulSoup(content, 'lxml')
            
            body = soup.find('body')
            if not body:
                body = soup  # some fragments lack <body>
            
            body_text = body.get_text(strip=True)
            if not body_text or len(body_text) < 10:
                continue
            
            chapter_num += 1
            
            block_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote']
            paragraphs = body.find_all(block_tags)
            
            if not paragraphs:
                divs = body.find_all('div')
                paragraphs = [d for d in divs if d.string or (d.get_text(strip=True) and not d.find(block_tags))]
            
            if not paragraphs:
                full_text = body.get_text(separator=' ', strip=True)
                if full_text:
                    class FakeParagraph:
                        def __init__(self, t): self._t = t
                        def get_text(self, strip=False): return self._t.strip() if strip else self._t
                    paragraphs = [FakeParagraph(full_text)]
            
            seen_texts = set()
            for p_tag in paragraphs:
                text = p_tag.get_text(strip=True) if hasattr(p_tag, 'get_text') else str(p_tag)
                text = re.sub(r'\s+', ' ', text).strip()
                
                if not text or len(text) < 2:
                    continue
                
                if text in seen_texts:
                    continue
                seen_texts.add(text)
                
                words = text.split()
                if not words:
                    continue
                
                for i, word_text in enumerate(words):
                    all_words.append({
                        "text": word_text,
                        "page": chapter_num,
                        "index": global_word_index,
                        "paragraph_id": global_paragraph_id,
                        "paragraph_start": i == 0,
                        "paragraph_end": i == len(words) - 1,
                        "x": 0, "y": 0, "width": 0, "height": 0,
                        "page_width": 0, "page_height": 0
                    })
                    global_word_index += 1
                global_paragraph_id += 1
        
        logger.info(f"EPUB extraction: {len(all_words)} words from {chapter_num} chapters")
        
    except Exception as e:
        logger.error(f"EPUB extraction failed: {e}")
        traceback.print_exc()
        return None
    
    return all_words

# Initialize Kokoro pipelines globally for better performance
# Maintain separate pipelines for different language codes (EN-US 'a' and EN-GB 'b')
kokoro_pipelines = {}

def get_kokoro_pipeline(lang_code='a'):
    """Get or initialize Kokoro pipeline (singleton pattern for performance)"""
    global kokoro_pipelines
    if lang_code not in kokoro_pipelines:
        logger.info(f"Initializing Kokoro pipeline with lang_code: {lang_code}")
        kokoro_pipelines[lang_code] = KPipeline(lang_code=lang_code)
        logger.info(f"Kokoro pipeline for lang_code '{lang_code}' initialized successfully")
    return kokoro_pipelines[lang_code]

def generate_audio_kokoro(text, voice_id, lang_code='a'):
    """Generate audio using Kokoro TTS"""
    try:
        logger.info(f"Generating audio with Kokoro ({voice_id}) for text: {text[:50]}...")
        
        # Get or initialize pipeline
        pipeline = get_kokoro_pipeline(lang_code)
        
        # Generate audio - Kokoro returns a generator that yields (graphemes, phonemes, audio)
        # We collect all audio chunks and concatenate them
        audio_chunks = []
        for gs, ps, audio in pipeline(text, voice=voice_id):
            audio_chunks.append(audio)
        
        # Concatenate all audio chunks
        if audio_chunks:
            audio_data = np.concatenate(audio_chunks)
        else:
            raise ValueError("No audio generated from Kokoro")
        
        # Kokoro outputs at 24kHz by default
        sample_rate = 24000
        
        logger.info(f"Kokoro TTS completed: {len(audio_data)} samples at {sample_rate}Hz")
        return audio_data, sample_rate
        
    except Exception as e:
        logger.error(f"Error with Kokoro TTS: {e}")
        traceback.print_exc()
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

def detect_repeated_patterns(words):
    """Detect repeated patterns like headers, footers, and page numbers across the document."""
    if not words or len(words) < 50:  # Skip for very short documents
        return {
            'headers': [],
            'footers': [],
            'page_numbers': [],
            'other_repeats': [],
            'total_filtered': 0
        }
    
    # Group words by page
    pages = {}
    for word in words:
        page = word['page']
        if page not in pages:
            pages[page] = []
        pages[page].append(word)
    
    if len(pages) < 2:  # Need at least 2 pages to detect patterns
        return {
            'headers': [],
            'footers': [],
            'page_numbers': [],
            'other_repeats': [],
            'total_filtered': 0
        }
    
    patterns = {
        'headers': [],
        'footers': [],
        'page_numbers': [],
        'other_repeats': []
    }
    
    # Analyze each page for potential patterns
    page_patterns = {}  # Store patterns per page for comparison
    
    for page_num, page_words in pages.items():
        if not page_words:
            continue
            
        # Calculate page dimensions
        page_height = max(word['page_height'] for word in page_words)
        page_width = max(word['page_width'] for word in page_words)
        
        # Define header and footer zones (top/bottom 20% of page for better coverage)
        header_threshold = page_height * 0.20
        footer_threshold = page_height * 0.80
        
        # Group words by approximate lines
        lines = group_words_by_lines_converted(page_words)
        
        page_patterns[page_num] = {
            'headers': [],
            'footers': [],
            'page_numbers': [],
            'other_repeats': []
        }
        
        for line in lines:
            if not line:
                continue
                
            line_text = ' '.join(word['text'] for word in line).strip()
            line_y = sum(word['y'] for word in line) / len(line)
            line_x = sum(word['x'] for word in line) / len(line)
            
            # Skip very short text (less than 3 characters) unless it's potentially a page number
            if len(line_text) < 3 and not line_text.isdigit():
                continue
            
            # Check for file paths and URLs (common in footers)
            is_file_path = False
            if any(indicator in line_text.lower() for indicator in ['file:///', 'http://', 'https://', '.html', '.pdf', '.com', '.org']):
                is_file_path = True
            elif '/' in line_text and len(line_text) > 10:  # Likely a file path
                is_file_path = True
            
            if is_file_path and line_y >= footer_threshold:
                page_patterns[page_num]['footers'].append({
                    'text': line_text,
                    'y': line_y,
                    'x': line_x,
                    'words': line,
                    'page': page_num
                })
            
            # Classify potential patterns
            if line_y <= header_threshold:
                # Potential header
                page_patterns[page_num]['headers'].append({
                    'text': line_text,
                    'y': line_y,
                    'x': line_x,
                    'words': line,
                    'page': page_num
                })
            elif line_y >= footer_threshold:
                # Potential footer
                page_patterns[page_num]['footers'].append({
                    'text': line_text,
                    'y': line_y,
                    'x': line_x,
                    'words': line,
                    'page': page_num
                })
            
            # Check for page numbers (expanded patterns)
            is_page_number = False
            
            # Pattern 1: Simple digits (1, 2, 3, etc.)
            if line_text.isdigit() and len(line_text) <= 4:
                is_page_number = True
            
            # Pattern 2: "Page X" or "Page X of Y" formats
            elif 'page' in line_text.lower() and any(char.isdigit() for char in line_text):
                is_page_number = True
            
            # Pattern 3: "X of Y" format
            elif ' of ' in line_text.lower() and any(char.isdigit() for char in line_text):
                is_page_number = True
            
            # Pattern 4: Roman numerals
            elif len(line_text) <= 10 and all(c.lower() in 'ivxlcdm ' for c in line_text.strip()):
                is_page_number = True
            
            # Pattern 5: Numbers with dashes or dots (1-1, 1.1, etc.)
            elif len(line_text) <= 15 and any(char.isdigit() for char in line_text) and \
                 any(sep in line_text for sep in ['-', '.', '/']):
                is_page_number = True
            
            if is_page_number:
                # Check if it's in corner or edge positions (expanded areas)
                is_edge_position = (line_x < page_width * 0.3 or line_x > page_width * 0.7) or \
                                  (line_y < page_height * 0.15 or line_y > page_height * 0.85)
                if is_edge_position:
                    page_patterns[page_num]['page_numbers'].append({
                        'text': line_text,
                        'y': line_y,
                        'x': line_x,
                        'words': line,
                        'page': page_num
                    })
    
    # Find repeating patterns across pages
    all_pages = list(pages.keys())
    min_pages_for_pattern = max(2, len(all_pages) // 4)  # Must appear on at least 1/4 of pages or minimum 2
    
    # Check headers
    header_candidates = {}
    for page_num, page_data in page_patterns.items():
        for header in page_data['headers']:
            text = header['text']
            if text not in header_candidates:
                header_candidates[text] = []
            header_candidates[text].append(header)
    
    for text, occurrences in header_candidates.items():
        if len(occurrences) >= min_pages_for_pattern:
            # Check if positions are similar (within 20% of page height)
            avg_y = sum(h['y'] for h in occurrences) / len(occurrences)
            position_consistent = all(abs(h['y'] - avg_y) < h['words'][0]['page_height'] * 0.2 for h in occurrences)
            
            if position_consistent:
                patterns['headers'].extend([h['words'] for h in occurrences])
    
    # Check footers
    footer_candidates = {}
    for page_num, page_data in page_patterns.items():
        for footer in page_data['footers']:
            text = footer['text']
            if text not in footer_candidates:
                footer_candidates[text] = []
            footer_candidates[text].append(footer)
    
    for text, occurrences in footer_candidates.items():
        if len(occurrences) >= min_pages_for_pattern:
            # Check if positions are similar
            avg_y = sum(f['y'] for f in occurrences) / len(occurrences)
            position_consistent = all(abs(f['y'] - avg_y) < f['words'][0]['page_height'] * 0.2 for f in occurrences)
            
            if position_consistent:
                patterns['footers'].extend([f['words'] for f in occurrences])
    
    # Check page numbers (less strict - can appear on most pages)
    pagenum_candidates = {}
    for page_num, page_data in page_patterns.items():
        for pagenum in page_data['page_numbers']:
            # For page numbers, we group by position rather than exact text
            position_key = f"{int(pagenum['x']/50)}_{int(pagenum['y']/50)}"  # Group by approximate position
            if position_key not in pagenum_candidates:
                pagenum_candidates[position_key] = []
            pagenum_candidates[position_key].append(pagenum)
    
    for position_key, occurrences in pagenum_candidates.items():
        if len(occurrences) >= min(2, len(all_pages) // 3):  # At least 2 pages or third of the pages
            patterns['page_numbers'].extend([p['words'] for p in occurrences])
    
    # Flatten patterns to get word indices for filtering
    patterns['total_filtered'] = sum(len(pattern_list) for pattern_list in patterns.values())
    
    logger.info(f"Pattern detection found: {len(patterns['headers'])} header lines, "
                f"{len(patterns['footers'])} footer lines, "
                f"{len(patterns['page_numbers'])} page number lines")
    
    return patterns

def filter_patterns_from_words(words, skip_patterns=True):
    """Filter out detected patterns from the words array if skip_patterns is True."""
    if not skip_patterns or not words:
        return words, {'total_filtered': 0}
    
    logger.info(f"Starting pattern filtering on {len(words)} words")
    
    # Detect patterns
    patterns = detect_repeated_patterns(words)
    
    if patterns['total_filtered'] == 0:
        logger.info("No patterns detected, returning original words")
        return words, patterns
    
    # Create a set of word indices to skip
    words_to_skip = set()
    
    for pattern_type in ['headers', 'footers', 'page_numbers', 'other_repeats']:
        for line_words in patterns[pattern_type]:
            for word in line_words:
                # Use the word's original index if available, otherwise find by matching
                if 'index' in word:
                    words_to_skip.add(word['index'])
                else:
                    # Fallback: find the word index in the original words array
                    for i, original_word in enumerate(words):
                        if (original_word['text'] == word['text'] and 
                            original_word['page'] == word['page'] and
                            abs(original_word['x'] - word['x']) < 1 and
                            abs(original_word['y'] - word['y']) < 1):
                            words_to_skip.add(i)
                            break
    
    # Filter words and reindex
    filtered_words = []
    new_index = 0
    
    for i, word in enumerate(words):
        if i not in words_to_skip:
            word_copy = word.copy()
            word_copy['index'] = new_index
            word_copy['original_index'] = i  # Keep track of original position
            filtered_words.append(word_copy)
            new_index += 1
    
    patterns['total_filtered'] = len(words_to_skip)
    logger.info(f"Filtered {len(words_to_skip)} words from {len(words)} total words, result: {len(filtered_words)} words")
    
    # Verify no duplicates in filtered words
    indices = [w['index'] for w in filtered_words]
    if len(indices) != len(set(indices)):
        logger.warning(f"Duplicate indices found in filtered words! indices length: {len(indices)}, unique: {len(set(indices))}")
    
    return filtered_words, patterns

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
    """Handle PDF or EPUB file upload and extract word data (protected route)."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        filename_lower = file.filename.lower()
        is_pdf = filename_lower.endswith('.pdf')
        is_epub = filename_lower.endswith('.epub')
        
        if not is_pdf and not is_epub:
            return jsonify({'error': 'Please upload a PDF or EPUB file'}), 400
        
        skip_patterns = request.form.get('skip_patterns', 'false').lower() == 'true'
        
        file_bytes = file.read()
        
        if is_epub:
            words_data = extract_words_from_epub_bytes(file_bytes)
        else:
            words_data = extract_words_from_pdf_bytes(file_bytes)
        
        if words_data is None:
            return jsonify({'error': 'Could not extract words from file'}), 500
        
        original_word_count = len(words_data)
        pattern_info = {'total_filtered': 0}
        
        if skip_patterns and is_pdf:
            words_data, pattern_info = filter_patterns_from_words(words_data, skip_patterns=True)
            logger.info(f"Pattern filtering: {pattern_info['total_filtered']} words filtered from {original_word_count}")
        
        user_id = request.current_user['id']
        filename = secure_filename(file.filename)
        
        pdf_result = auth_service.save_user_pdf(user_id, filename, file_bytes)
        if 'error' in pdf_result:
            logger.warning(f"Failed to save file to storage: {pdf_result['error']}")
        
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
            'original_word_count': original_word_count,
            'patterns_filtered': pattern_info['total_filtered'],
            'skip_patterns_enabled': skip_patterns,
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
    """Generate audio using Kokoro TTS (protected route)"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        model_key = data.get('model', 'kokoro-af-heart')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        if len(text) > 10000:
            return jsonify({'error': 'Text too long for single request'}), 400
        
        if model_key not in Config.AVAILABLE_MODELS:
            return jsonify({'error': 'Invalid model selected'}), 400
        
        voice_config = Config.AVAILABLE_MODELS[model_key]
        voice_id = voice_config['voice_id']
        lang_code = voice_config.get('lang_code', 'a')  # Default to American English
        
        logger.info(f"Generating audio with {voice_id} for {len(text)} characters")
        
        audio_data, sample_rate = generate_audio_kokoro(text, voice_id, lang_code)
        
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
        
        content_type = 'application/pdf'
        if metadata['filename'].lower().endswith('.epub'):
            content_type = 'application/epub+zip'
        
        response = make_response(file_data)
        response.headers['Content-Type'] = content_type
        response.headers['Content-Disposition'] = f'inline; filename="{metadata["filename"]}"'
        response.headers['Content-Length'] = len(file_data)
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting PDF file: {e}")
        return jsonify({'error': 'Failed to get PDF file'}), 500

@app.route('/api/user/pdfs/<file_id>', methods=['DELETE'])
@token_required
def delete_user_pdf_file(file_id):
    """Delete PDF file and all associated data for the current user"""
    try:
        user_id = request.current_user['id']
        logger.info(f"DELETE request for PDF {file_id} by user {user_id}")
        
        result = auth_service.delete_user_pdf(user_id, file_id)
        
        if 'error' in result:
            logger.warning(f"Delete failed for PDF {file_id}: {result['error']}")
            return jsonify(result), 404
        
        # Log the comprehensive cleanup results
        if 'deletion_summary' in result:
            summary = result['deletion_summary']
            logger.info(f"Complete PDF deletion summary for {file_id}:")
            logger.info(f"  - Local file: {'✓' if summary['local_file_deleted'] else '✗'}")
            logger.info(f"  - Word cache: {'✓' if summary['word_cache_deleted'] else '✗'}")
            logger.info(f"  - Reading progress: {'✓' if summary['reading_progress_deleted'] else '✗'} ({summary['progress_records_count']} records)")
            logger.info(f"  - Metadata: {'✓' if summary['metadata_deleted'] else '✗'}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error deleting PDF file {file_id}: {e}")
        return jsonify({'error': 'Failed to delete PDF file'}), 500

@app.route('/api/user/pdfs/<file_id>/words', methods=['GET'])
@token_required
def get_pdf_words(file_id):
    """Get cached word data for a PDF with optional pattern filtering"""
    try:
        user_id = request.current_user['id']
        skip_patterns = request.args.get('skip_patterns', 'false').lower() == 'true'
        
        result = auth_service.get_cached_words(user_id, file_id)
        if isinstance(result, tuple):
            return jsonify(result[0]), result[1]
        
        if 'error' in result:
            return jsonify(result), 500
        
        # Treat empty cached data as uncached so the frontend triggers re-extraction
        if result.get('cached') and (not result.get('words') or len(result['words']) == 0):
            result['cached'] = False
        
        if skip_patterns and result.get('cached') and 'words' in result:
            original_word_count = len(result['words'])
            filtered_words, pattern_info = filter_patterns_from_words(result['words'], skip_patterns=True)
            
            result['words'] = filtered_words
            result['word_count'] = len(filtered_words)
            result['original_word_count'] = original_word_count
            result['patterns_filtered'] = pattern_info['total_filtered']
            result['skip_patterns_enabled'] = True
            
            logger.info(f"Pattern filtering applied: {pattern_info['total_filtered']} words filtered from {original_word_count}")
        else:
            result['skip_patterns_enabled'] = False
            result['patterns_filtered'] = 0
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting PDF words: {e}")
        return jsonify({'error': 'Failed to get PDF words'}), 500

@app.route('/api/extract-words', methods=['POST'])
@token_required
def extract_words_only():
    """Extract words from PDF and cache the results with optional pattern filtering"""
    try:
        user_id = request.current_user['id']
        skip_patterns = request.form.get('skip_patterns', 'false').lower() == 'true'
        
        # Check if file_id is provided for caching
        file_id = request.form.get('file_id')
        
        # Check cache only when no file is uploaded alongside the request
        has_file = 'file' in request.files and request.files['file'].filename != ''
        if file_id and not has_file:
            cached_result = auth_service.get_cached_words(user_id, file_id)
            if cached_result['cached'] and cached_result.get('words') and len(cached_result['words']) > 0:
                logger.info(f"Using cached word data for file {file_id}")
                
                words_data = cached_result['words']
                original_word_count = len(words_data)
                pattern_info = {'total_filtered': 0}
                
                if skip_patterns:
                    words_data, pattern_info = filter_patterns_from_words(words_data, skip_patterns=True)
                    logger.info(f"Pattern filtering on cached data: {pattern_info['total_filtered']} words filtered from {original_word_count}")
                
                return jsonify({
                    'words': words_data,
                    'word_count': len(words_data),
                    'original_word_count': original_word_count,
                    'patterns_filtered': pattern_info['total_filtered'],
                    'skip_patterns_enabled': skip_patterns,
                    'cached': True,
                    'cached_at': cached_result['cached_at']
                })
        
        # No usable cache - extract words from uploaded file
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        filename_lower = file.filename.lower()
        if not filename_lower.endswith('.pdf') and not filename_lower.endswith('.epub'):
            return jsonify({'error': 'Please upload a PDF or EPUB file'}), 400
        
        file_bytes = file.read()
        if filename_lower.endswith('.epub'):
            words_data = extract_words_from_epub_bytes(file_bytes)
        else:
            words_data = extract_words_from_pdf_bytes(file_bytes)
        
        if words_data is None:
            return jsonify({'error': 'Could not extract words from file'}), 500

        # Apply pattern filtering if requested
        original_word_count = len(words_data)
        pattern_info = {'total_filtered': 0}
        
        if skip_patterns:
            words_data, pattern_info = filter_patterns_from_words(words_data, skip_patterns=True)
            logger.info(f"Pattern filtering on new extraction: {pattern_info['total_filtered']} words filtered from {original_word_count}")
        
        # Cache the results if file_id is provided (cache the original unfiltered data)
        if file_id:
            # Always cache the original unfiltered data so we can apply different filtering later
            if skip_patterns:
                original_words = extract_words_from_epub_bytes(file_bytes) if filename_lower.endswith('.epub') else extract_words_from_pdf_bytes(file_bytes)
            else:
                original_words = words_data
            cache_result = auth_service.save_word_cache(user_id, file_id, original_words)
            if 'error' not in cache_result:
                logger.info(f"Cached word data for file {file_id}: {len(original_words)} words")
        
        return jsonify({
            'words': words_data,
            'word_count': len(words_data),
            'original_word_count': original_word_count,
            'patterns_filtered': pattern_info['total_filtered'],
            'skip_patterns_enabled': skip_patterns,
            'cached': False
        })
    
    except Exception as e:
        logger.error(f"Extract words error: {e}")
        return jsonify({'error': 'An unexpected error occurred during processing.'}), 500

# --- BACKGROUND MUSIC ENDPOINTS --- #

@app.route('/api/user/background-music', methods=['GET'])
@token_required
def get_user_background_music():
    """Get list of user's background music files"""
    try:
        user_id = request.current_user['id']
        result = auth_service.get_user_background_music(user_id)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting background music: {e}")
        return jsonify({'error': 'Failed to get background music'}), 500

@app.route('/api/upload-background-music', methods=['POST'])
@token_required
def upload_background_music():
    """Upload background music file for the current user"""
    try:
        user_id = request.current_user['id']
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check if it's an audio file
        allowed_extensions = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Please upload an audio file (mp3, wav, m4a, aac, ogg, flac)'}), 400
        
        # Check file size (limit to 500MB)
        file_bytes = file.read()
        if len(file_bytes) > 500 * 1024 * 1024:  # 500MB
            return jsonify({'error': 'File size too large. Maximum 500MB allowed.'}), 400
        
        result = auth_service.save_background_music(user_id, file.filename, file_bytes)
        
        if 'error' in result:
            return jsonify(result), 400
        
        logger.info(f"Background music uploaded: {result['file_id']} by user {user_id}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Background music upload error: {e}")
        return jsonify({'error': 'An unexpected error occurred during upload.'}), 500

@app.route('/api/user/background-music/<file_id>', methods=['GET'])
@token_required
def get_background_music_file(file_id):
    """Get background music file content for the current user"""
    try:
        user_id = request.current_user['id']
        result = auth_service.get_background_music_file(user_id, file_id)
        
        if 'error' in result:
            return jsonify(result), 404
        
        file_data = result['file_data']
        metadata = result['metadata']
        
        # Determine content type based on file extension
        file_ext = os.path.splitext(metadata['filename'])[1].lower()
        content_type_map = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.m4a': 'audio/mp4',
            '.aac': 'audio/aac',
            '.ogg': 'audio/ogg',
            '.flac': 'audio/flac'
        }
        content_type = content_type_map.get(file_ext, 'audio/mpeg')
        
        response = make_response(file_data)
        response.headers['Content-Type'] = content_type
        response.headers['Content-Disposition'] = f'inline; filename="{metadata["filename"]}"'
        response.headers['Content-Length'] = len(file_data)
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting background music file: {e}")
        return jsonify({'error': 'Failed to get background music file'}), 500

@app.route('/api/user/background-music/<file_id>', methods=['DELETE'])
@token_required
def delete_background_music_file(file_id):
    """Delete background music file for the current user"""
    try:
        user_id = request.current_user['id']
        logger.info(f"DELETE request for background music {file_id} by user {user_id}")
        
        result = auth_service.delete_background_music(user_id, file_id)
        
        if 'error' in result:
            logger.warning(f"Delete failed for background music {file_id}: {result['error']}")
            return jsonify(result), 404
        
        logger.info(f"Background music deleted: {file_id} by user {user_id}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error deleting background music file {file_id}: {e}")
        return jsonify({'error': 'Failed to delete background music file'}), 500

# --- USER PREFERENCES ENDPOINTS --- #

@app.route('/api/user/preferences', methods=['GET'])
@token_required
def get_user_preferences():
    """Get user's default preferences"""
    try:
        user_id = request.current_user['id']
        result = auth_service.get_user_preferences(user_id)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        return jsonify({'error': 'Failed to get user preferences'}), 500

@app.route('/api/user/preferences', methods=['PUT'])
@token_required
def update_user_preferences():
    """Update user's default preferences"""
    try:
        user_id = request.current_user['id']
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No preferences data provided'}), 400
        
        result = auth_service.update_user_preferences(user_id, data)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error updating user preferences: {e}")
        return jsonify({'error': 'Failed to update user preferences'}), 500

@app.route('/api/user/preferences/book/<pdf_id>', methods=['GET'])
@token_required
def get_book_preferences(pdf_id):
    """Get book-specific preferences"""
    try:
        user_id = request.current_user['id']
        result = auth_service.get_book_preferences(user_id, pdf_id)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting book preferences: {e}")
        return jsonify({'error': 'Failed to get book preferences'}), 500

@app.route('/api/user/preferences/book/<pdf_id>', methods=['PUT'])
@token_required
def update_book_preferences(pdf_id):
    """Update book-specific preferences"""
    try:
        user_id = request.current_user['id']
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No preferences data provided'}), 400
        
        result = auth_service.update_book_preferences(user_id, pdf_id, data)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error updating book preferences: {e}")
        return jsonify({'error': 'Failed to update book preferences'}), 500

@app.route('/api/user/preferences/book/<pdf_id>', methods=['DELETE'])
@token_required
def delete_book_preferences(pdf_id):
    """Delete book-specific preferences (revert to user defaults)"""
    try:
        user_id = request.current_user['id']
        result = auth_service.delete_book_preferences(user_id, pdf_id)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error deleting book preferences: {e}")
        return jsonify({'error': 'Failed to delete book preferences'}), 500

@app.route('/api/user/preferences/effective/<pdf_id>', methods=['GET'])
@token_required
def get_effective_preferences(pdf_id):
    """Get effective preferences for a book (combines user defaults with book overrides)"""
    try:
        user_id = request.current_user['id']
        result = auth_service.get_effective_preferences(user_id, pdf_id)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting effective preferences: {e}")
        return jsonify({'error': 'Failed to get effective preferences'}), 500

@app.route('/api/user/preferences/migrate', methods=['POST'])
@token_required
def migrate_localStorage_preferences():
    """Migrate preferences from localStorage to database (one-time migration helper)"""
    try:
        user_id = request.current_user['id']
        data = request.get_json()
        
        if not data or 'localStorage_prefs' not in data:
            return jsonify({'error': 'No localStorage preferences provided'}), 400
        
        localStorage_prefs = data['localStorage_prefs']
        
        # Extract preferences from localStorage format
        preferences = {}
        if 'voice' in localStorage_prefs:
            preferences['voice_model'] = localStorage_prefs['voice']
        if 'speed' in localStorage_prefs:
            preferences['voice_speed'] = float(localStorage_prefs['speed'])
        if 'skipPatterns' in localStorage_prefs:
            preferences['skip_patterns'] = bool(localStorage_prefs['skipPatterns'])
        
        if preferences:
            result = auth_service.update_user_preferences(user_id, preferences)
            
            if 'error' in result:
                return jsonify(result), 400
            
            return jsonify({
                'success': True, 
                'migrated': preferences,
                'message': 'Preferences successfully migrated from localStorage to database'
            })
        else:
            return jsonify({
                'success': True,
                'message': 'No valid preferences found to migrate'
            })
        
    except Exception as e:
        logger.error(f"Error migrating localStorage preferences: {e}")
        return jsonify({'error': 'Failed to migrate preferences'}), 500

if __name__ == '__main__':
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT) 