#!/usr/bin/env python3
"""
Run script for PDF to Audio Converter
"""

import sys
import os
from pathlib import Path

def main():
    """Main run function"""
    # Add current directory to path
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir))
    
    # Check if setup was run
    if not Path(".env").exists():
        print("⚠️  No .env file found. Running setup first...")
        print("Please run: python setup.py")
        sys.exit(1)
    
    # Import and run the app
    try:
        from app import app
        from config import Config
        
        print("🚀 Starting PDF to Audio Converter...")
        print(f"📍 Server will run at: http://{Config.HOST}:{Config.PORT}")
        print("💡 Press Ctrl+C to stop the server")
        
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG
        )
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please run: python setup.py")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 