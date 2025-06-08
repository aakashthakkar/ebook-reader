# PDF to Audio eBook Reader

A sophisticated web application that converts PDF documents into interactive audiobooks with click-to-play functionality. Upload any PDF, and click on any word to start listening from that position with high-quality text-to-speech.

## 🎯 Features

### Core Functionality
- **Smart PDF Text Extraction**: Dual-engine text extraction using both `pdfplumber` and `PyPDF2` for maximum compatibility
- **Interactive Click-to-Play**: Click any word in the extracted text to start audio playback from that exact position
- **On-Demand Audio Generation**: Audio is generated in real-time using Microsoft Edge TTS as you navigate through the text
- **Pattern Detection & Filtering**: Automatically detect and optionally skip repeated headers, footers, and page numbers during playback
- **Multiple High-Quality Voices**: Choose from 6 different neural voices including Andrew, Jenny, Aria, Guy, and Christopher
- **Real-Time Visual Feedback**: Current word highlighting and chunk-based progress tracking during playback

### User Experience
- **Modern Web Interface**: Beautiful, responsive UI built with Tailwind CSS and Lucide icons
- **Drag & Drop Upload**: Easy PDF upload with visual feedback
- **Floating Audio Controls**: Sticky audio player that follows you as you scroll
- **Smart Content Filtering**: Toggle to skip repetitive content like headers and footers
- **Large File Support**: Handles PDFs up to 100MB in size
- **Word-Level Navigation**: Precise control over audio playback position

### Technical Features
- **RESTful API**: Clean API endpoints for PDF processing and audio generation
- **Chunked Processing**: Intelligent text chunking for optimal performance (100-word chunks)
- **Base64 Audio Streaming**: Efficient audio delivery without file storage
- **Docker Support**: Complete containerization with Docker and docker-compose
- **Environment Configuration**: Flexible configuration via environment variables

## 🚀 Quick Start

### Prerequisites
- Python 3.7 or higher
- pip (Python package installer)

### Installation

1. **Clone and Navigate**
   ```bash
   git clone <your-repo-url>
   cd ebook-reader
   ```

2. **Set Up Virtual Environment**
   
   For Fish shell users:
   ```fish
   python -m venv venv
   source venv/bin/activate.fish
   ```
   
   For Bash/Zsh users:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment (Optional)**
   Create a `.env` file in the project root:
   ```bash
   # .env
   DEBUG=True
   HOST=0.0.0.0
   PORT=8000
   SECRET_KEY=your-secret-key-here
   ```

5. **Run the Application**
   ```bash
   python app.py
   ```
   
   Access the application at: `http://localhost:8000`

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)
```bash
docker-compose up --build
```

### Manual Docker Build
```bash
docker build -t ebook-reader .
docker run -p 8000:8000 ebook-reader
```

## 📖 Usage Guide

### Web Interface
1. **Upload PDF**: Drag and drop or click to select a PDF file
2. **Choose Voice**: Select from 6 available neural voices (Andrew is recommended)
3. **Configure Settings**: Toggle "Skip Headers/Footers" to filter out repetitive content
4. **Interactive Reading**: Click any word to start audio playbook from that position
5. **Control Playback**: Use the floating audio controls to pause, resume, or navigate

### Pattern Detection & Filtering
The application includes intelligent pattern detection to improve the listening experience:

- **Automatic Detection**: Identifies repeated headers, footers, and page numbers across the document
- **Smart Filtering**: Uses spatial analysis and frequency detection to find patterns that appear on multiple pages
- **Optional Feature**: Toggle on/off via the "Skip Headers/Footers" control in the audio player
- **Conservative Approach**: Only filters content that appears consistently across multiple pages to avoid removing important text
- **Real-time Feedback**: Shows how many words were filtered when the feature is enabled

**Pattern Types Detected:**
- Headers: Text in the top 15% of pages that repeats across multiple pages
- Footers: Text in the bottom 15% of pages that repeats across multiple pages  
- Page Numbers: Numeric text in corner positions
- Running Headers: Consistent text in the same position across consecutive pages

### Available Voices
- **Andrew (Neural)** - ⭐ Recommended: High-quality English male voice
- **Andrew (Multilingual)** - Advanced multilingual support
- **Jenny (Neural)** - Friendly and considerate female voice
- **Aria (Neural)** - Positive and confident female voice
- **Guy (Neural)** - Passionate male voice for engaging content
- **Christopher (Neural)** - Reliable and authoritative male voice

## 🔌 API Reference

### Upload PDF
**Endpoint**: `POST /api/upload`

**Request**: Multipart form data with PDF file
```bash
curl -X POST -F "file=@document.pdf" http://localhost:8000/api/upload
```

**Response**:
```json
{
  "text": "Extracted text content...",
  "filename": "document.pdf",
  "text_length": 12345
}
```

### Generate Audio
**Endpoint**: `POST /api/generate-audio`

**Request**:
```json
{
  "text": "Text to convert to speech",
  "model": "edge-tts-andrew"
}
```

**Response**:
```json
{
  "success": true,
  "audio_data": "base64-encoded-audio-data",
  "sample_rate": 24000,
  "duration": 5.23,
  "text": "Original text",
  "voice_used": "Andrew (Neural)"
}
```

## ⚙️ Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `True` | Enable debug mode |
| `HOST` | `0.0.0.0` | Server host address |
| `PORT` | `8000` | Server port |
| `SECRET_KEY` | Auto-generated | Flask secret key |

### Application Limits
- **Max PDF Size**: 100MB
- **Max Text Length**: 2 million characters
- **Audio Chunk Size**: 100 words
- **Sample Rate**: 24kHz

## 🛠️ Development

### Project Structure
```
ebook-reader/
├── app.py              # Main Flask application
├── config.py           # Configuration and voice models
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html     # Web interface
├── Dockerfile         # Docker configuration
├── docker-compose.yml # Docker Compose setup
└── README.md          # This file
```

### Key Dependencies
- **Flask**: Web framework and API server
- **pdfplumber**: Primary PDF text extraction
- **PyPDF2**: Fallback PDF text extraction
- **edge-tts**: Microsoft Edge Text-to-Speech
- **soundfile**: Audio file processing
- **numpy**: Numerical operations for audio

### Adding New Voices
Edit `config.py` and add new voice configurations to `AVAILABLE_MODELS`:
```python
'new-voice-key': {
    'name': 'Voice Name',
    'description': 'Voice description',
    'voice_id': 'edge-tts-voice-id',
    'speed': 'Real-time streaming',
    'sample_rate': 24000,
    'type': 'edge-tts'
}
```

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit changes: `git commit -am 'Add feature'`
4. Push to branch: `git push origin feature-name`
5. Submit a pull request

## 🐛 Troubleshooting

### Common Issues
- **Audio not playing**: Check browser audio permissions and volume
- **PDF upload fails**: Ensure PDF is not corrupted and under 100MB
- **Voice not loading**: Verify internet connection for Edge TTS service
- **Virtual environment issues**: Make sure you're using the correct activation script for your shell

### Support
For issues and questions, please create an issue in the repository with:
- Operating system and version
- Python version
- Error messages or logs
- Steps to reproduce the problem