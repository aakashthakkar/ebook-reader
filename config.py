import os
from dotenv import load_dotenv
from pathlib import Path
import tempfile

# Load environment variables
load_dotenv()

class Config:
    # Flask settings
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
    
    # Server settings
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8000))
    
    # JWT settings
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))  # 1 hour
    
    # Supabase settings
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '')
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    
    # File upload settings
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', '/tmp')  # Use /tmp by default, configurable via env var
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size
    
    # Text processing settings
    MAX_TEXT_LENGTH = 2_000_000  # 2 million characters (for books)
    CHUNK_SIZE = 100  # Process in chunks of exactly 100 words for on-demand streaming
    
    # Kokoro TTS Voice configurations
    # American English voices (lang_code='a')
    AVAILABLE_MODELS = {
        # Female American English voices
        'kokoro-af-heart': {
            'name': 'Heart (Female, US) ⭐',
            'description': 'Premium American English female voice - Grade A',
            'voice_id': 'af_heart',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-bella': {
            'name': 'Bella (Female, US)',
            'description': 'High-quality warm American English female voice - Grade A-',
            'voice_id': 'af_bella',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-nicole': {
            'name': 'Nicole (Female, US)',
            'description': 'Headphone-optimized American English female voice - Grade B-',
            'voice_id': 'af_nicole',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-sarah': {
            'name': 'Sarah (Female, US)',
            'description': 'Natural American English female voice - Grade C+',
            'voice_id': 'af_sarah',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-aoede': {
            'name': 'Aoede (Female, US)',
            'description': 'Smooth American English female voice - Grade C+',
            'voice_id': 'af_aoede',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-kore': {
            'name': 'Kore (Female, US)',
            'description': 'Clear American English female voice - Grade C+',
            'voice_id': 'af_kore',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-alloy': {
            'name': 'Alloy (Female, US)',
            'description': 'Versatile American English female voice - Grade C',
            'voice_id': 'af_alloy',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-nova': {
            'name': 'Nova (Female, US)',
            'description': 'Modern American English female voice - Grade C',
            'voice_id': 'af_nova',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-sky': {
            'name': 'Sky (Female, US)',
            'description': 'Bright American English female voice - Grade C-',
            'voice_id': 'af_sky',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-jessica': {
            'name': 'Jessica (Female, US)',
            'description': 'American English female voice - Grade D',
            'voice_id': 'af_jessica',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-af-river': {
            'name': 'River (Female, US)',
            'description': 'American English female voice - Grade D',
            'voice_id': 'af_river',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        # Male American English voices
        'kokoro-am-michael': {
            'name': 'Michael (Male, US)',
            'description': 'Strong American English male voice - Grade C+',
            'voice_id': 'am_michael',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-fenrir': {
            'name': 'Fenrir (Male, US)',
            'description': 'Deep American English male voice - Grade C+',
            'voice_id': 'am_fenrir',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-puck': {
            'name': 'Puck (Male, US)',
            'description': 'Energetic American English male voice - Grade C+',
            'voice_id': 'am_puck',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-echo': {
            'name': 'Echo (Male, US)',
            'description': 'American English male voice - Grade D',
            'voice_id': 'am_echo',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-eric': {
            'name': 'Eric (Male, US)',
            'description': 'American English male voice - Grade D',
            'voice_id': 'am_eric',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-liam': {
            'name': 'Liam (Male, US)',
            'description': 'American English male voice - Grade D',
            'voice_id': 'am_liam',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-onyx': {
            'name': 'Onyx (Male, US)',
            'description': 'American English male voice - Grade D',
            'voice_id': 'am_onyx',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-santa': {
            'name': 'Santa (Male, US)',
            'description': 'Jolly American English male voice - Grade D-',
            'voice_id': 'am_santa',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-am-adam': {
            'name': 'Adam (Male, US)',
            'description': 'American English male voice - Grade F+',
            'voice_id': 'am_adam',
            'lang_code': 'a',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        # Female British English voices (lang_code='b')
        'kokoro-bf-emma': {
            'name': 'Emma (Female, UK)',
            'description': 'High-quality British English female voice - Grade B-',
            'voice_id': 'bf_emma',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-bf-isabella': {
            'name': 'Isabella (Female, UK)',
            'description': 'Refined British English female voice - Grade C',
            'voice_id': 'bf_isabella',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-bf-alice': {
            'name': 'Alice (Female, UK)',
            'description': 'British English female voice - Grade D',
            'voice_id': 'bf_alice',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-bf-lily': {
            'name': 'Lily (Female, UK)',
            'description': 'British English female voice - Grade D',
            'voice_id': 'bf_lily',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        # Male British English voices (lang_code='b')
        'kokoro-bm-george': {
            'name': 'George (Male, UK)',
            'description': 'Distinguished British English male voice - Grade C',
            'voice_id': 'bm_george',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-bm-fable': {
            'name': 'Fable (Male, UK)',
            'description': 'Narrative British English male voice - Grade C',
            'voice_id': 'bm_fable',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-bm-lewis': {
            'name': 'Lewis (Male, UK)',
            'description': 'British English male voice - Grade D+',
            'voice_id': 'bm_lewis',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        },
        'kokoro-bm-daniel': {
            'name': 'Daniel (Male, UK)',
            'description': 'British English male voice - Grade D',
            'voice_id': 'bm_daniel',
            'lang_code': 'b',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'kokoro'
        }
    }
    
    @staticmethod
    def init_app(app):
        # Create required directories
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True) 