# Multi-stage build with explicit architecture support
# Use official Python image with explicit platform support
FROM python:3.11-slim

# Print architecture info for debugging
RUN echo "Building for architecture: $(uname -m)" && \
    echo "Platform: $(uname -s)" && \
    python3 --version

# Set working directory
WORKDIR /app

# Set environment variables for better compatibility
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Update package lists and install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    curl \
    libffi-dev \
    libssl-dev \
    pkg-config \
    libsndfile1 \
    espeak \
    espeak-data \
    libespeak1 \
    libespeak-dev \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

# Clone the repository from GitHub
RUN git clone https://github.com/aakashthakkar/ebook-reader.git . && \
    rm -rf .git && \
    ls -la

# Upgrade pip and install Python dependencies
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Add labels for better image management
LABEL maintainer="aakashthakkar" \
      description="PDF to Audio eBook Reader" \
      version="1.0"

# Health check with better error handling
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["python", "app.py"] 