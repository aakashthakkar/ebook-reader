# PDF to Audio Converter

A modern web application that converts PDF documents to high-quality audio using state-of-the-art AI text-to-speech models. Built with Flask and featuring a beautiful, responsive UI.

## Features

- 🎯 **PDF Text Extraction**: Automatically extracts text from PDF documents using multiple parsing methods
- 📚 **Book Support**: Handle large PDFs up to 100MB and 2 million characters (equivalent to ~800 page books)
- 🤖 **Multiple AI Models**: Choose from various TTS models including Dia-1.6B, Bark, and ESPnet
- 🎵 **High-Quality Audio**: Generate natural-sounding speech with emotion and voice control
- 📱 **Responsive Design**: Modern, mobile-friendly interface with drag & drop support
- ⚡ **Smart Processing**: Automatic text chunking for long documents with progress tracking
- 💾 **Easy Download**: Download generated audio files in multiple formats

## Supported Models

### Dia 1.6B (Nari Labs) - Recommended
- **Features**: High-quality dialogue generation with voice cloning
- **Requirements**: ~10GB VRAM, GPU recommended
- **Specialty**: Realistic dialogue with speaker alternation and non-verbal sounds
- **Local Model**: Can use your downloaded model at `./llm/dia-v0_1.pth`

### Bark (Suno AI)
- **Features**: Multilingual TTS with various speakers and emotions
- **Requirements**: ~8GB VRAM, GPU recommended
- **Specialty**: Multiple languages and expressive speech

### ESPnet TTS
- **Features**: General-purpose text-to-speech
- **Requirements**: CPU compatible
- **Specialty**: Lightweight and fast processing

## Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager
- (Optional) NVIDIA GPU with CUDA for better performance

## 🚀 Quick Start

### Option 1: Local Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd TTS
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```

4. **Open your browser** to `http://localhost:8000`

### Option 2: Docker Deployment

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd TTS
   ```

2. **Using Docker Compose** (Recommended):
   ```bash
   docker-compose up -d
   ```

3. **Or build and run manually**:
   ```bash
   docker build -t pdf-tts .
   docker run -p 8000:8000 pdf-tts
   ```

4. **Access the application** at `http://localhost:8000`

## Usage

1. **Upload PDF**: Drag and drop or click to upload your PDF file (max 100MB - perfect for books!)
2. **Choose Model**: Select your preferred AI model from the dropdown
3. **Generate Audio**: Click "Generate Audio" and wait for processing (large texts are automatically chunked)
4. **Listen & Download**: Play the generated audio and download if desired

### Tips for Best Results

#### For Dia Model:
- Text is automatically formatted with speaker tags `[S1]` and `[S2]` for dialogue
- Optimal input length: 5-20 seconds of speech (roughly 50-200 words)
- Supports non-verbal sounds like `(laughs)`, `(coughs)`, etc.

#### For Bark Model:
- Works well with natural, conversational text
- Supports multiple languages
- Can generate various emotions and tones

## Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# HuggingFace Token (for model downloads)
HF_TOKEN=your_token_here

# Model Configuration
DEFAULT_MODEL=dia-1.6b
LOCAL_MODEL_PATH=./llm/dia-v0_1.pth

# Server Configuration
HOST=0.0.0.0
PORT=5000
FLASK_DEBUG=True

# GPU Configuration
DEVICE=auto  # auto, cpu, cuda
COMPUTE_DTYPE=float16
```

### Using Local Dia Model

If you have the Dia model downloaded locally:

1. Place the model file at `./llm/dia-v0_1.pth`
2. The application will automatically detect and use the local model
3. This reduces download time and ensures consistent performance

## API Endpoints

### REST API

- `POST /api/upload` - Upload and extract text from PDF
- `POST /api/generate` - Generate audio from text
- `GET /api/download/<filename>` - Download generated audio
- `GET /api/models` - Get available models
- `GET /health` - Health check

### Example API Usage

```bash
# Upload PDF
curl -X POST -F "file=@document.pdf" http://localhost:8000/api/upload

# Generate audio
curl -X POST -H "Content-Type: application/json" \
  -d '{"text":"Hello world","model":"dia-1.6b"}' \
  http://localhost:8000/api/generate
```

## Hardware Requirements

### Minimum Requirements
- **CPU**: 4 cores, 2.0 GHz
- **RAM**: 8GB
- **Storage**: 2GB free space

### Recommended for Dia/Bark Models
- **GPU**: NVIDIA RTX 3080 or better
- **VRAM**: 10GB+ for Dia, 8GB+ for Bark
- **RAM**: 16GB+
- **Storage**: 5GB+ free space

### CPU-Only Mode
- Use ESPnet TTS model for CPU-only processing
- Longer processing times but no GPU required

## Troubleshooting

### Common Issues

1. **Model Download Fails**
   - Check internet connection
   - Verify HuggingFace token if using gated models
   - Ensure sufficient disk space

2. **CUDA/GPU Issues**
   - Install CUDA toolkit compatible with PyTorch
   - Set `DEVICE=cpu` in `.env` for CPU-only mode
   - Check GPU memory usage with `nvidia-smi`

3. **PDF Text Extraction Issues**
   - Ensure PDF contains extractable text (not just images)
   - Try different PDF files to test
   - Check file size (max 100MB)

4. **Audio Generation Errors**
   - Check available system memory
   - Try shorter text inputs
   - Switch to a different model

### Performance Optimization

- **GPU Usage**: Ensure CUDA is properly installed
- **Memory**: Close other applications to free up RAM/VRAM
- **Text Length**: Keep inputs between 50-500 words for best results
- **Model Selection**: Use ESPnet for faster processing on CPU

## Development

### Project Structure
```
TTS/
├── app.py               # Main Flask application
├── config.py            # Configuration settings
├── requirements.txt     # Python dependencies
├── templates/
│   └── index.html      # Web interface
├── Dockerfile          # Docker build configuration
├── docker-compose.yml  # Docker Compose setup
├── .dockerignore       # Docker ignore rules
├── .env                # Environment variables
└── README.md           # This file
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is for educational and research purposes. Please respect the individual licenses of the AI models used:

- **Dia Model**: Apache 2.0 License
- **Bark Model**: Check Suno AI licensing
- **ESPnet**: Apache 2.0 License

## Acknowledgments

- [Nari Labs](https://github.com/nari-labs/dia) for the Dia TTS model
- [Suno AI](https://github.com/suno-ai/bark) for the Bark model
- [ESPnet](https://github.com/espnet/espnet) for the TTS framework
- [Hugging Face](https://huggingface.co/) for model hosting and transformers library

## Support

If you encounter issues or have questions:

1. Check the troubleshooting section above
2. Search existing GitHub issues
3. Create a new issue with detailed information
4. Include error logs and system specifications

---

**Note**: This application requires significant computational resources for optimal performance. Consider using cloud GPU instances for production deployments. 