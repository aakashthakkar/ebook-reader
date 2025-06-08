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
    
    # Edge TTS Voice configurations
    AVAILABLE_MODELS = {
        'edge-tts-andrew': {
            'name': 'Andrew (Neural)',
            'description': 'High-quality English male voice with natural pronunciation - Edge TTS',
            'voice_id': 'en-US-AndrewNeural',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'edge-tts'
        },
        'edge-tts-andrew-multilingual': {
            'name': 'Andrew (Multilingual)',
            'description': 'Advanced multilingual male voice - Edge TTS',
            'voice_id': 'en-US-AndrewMultilingualNeural',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'edge-tts'
        },
        'edge-tts-jenny': {
            'name': 'Jenny (Neural)',
            'description': 'Friendly and considerate female voice - Edge TTS',
            'voice_id': 'en-US-JennyNeural',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'edge-tts'
        },
        'edge-tts-aria': {
            'name': 'Aria (Neural)',
            'description': 'Positive and confident female voice - Edge TTS',
            'voice_id': 'en-US-AriaNeural',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'edge-tts'
        },
        'edge-tts-guy': {
            'name': 'Guy (Neural)',
            'description': 'Passionate male voice for engaging content - Edge TTS',
            'voice_id': 'en-US-GuyNeural',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'edge-tts'
        },
        'edge-tts-christopher': {
            'name': 'Christopher (Neural)',
            'description': 'Reliable and authoritative male voice - Edge TTS',
            'voice_id': 'en-US-ChristopherNeural',
            'speed': 'Real-time streaming',
            'sample_rate': 24000,
            'type': 'edge-tts'
        }
    }
    
    @staticmethod
    def init_app(app):
        # Create required directories
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True) 