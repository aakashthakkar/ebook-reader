# Multi-stage build with explicit architecture support
# Use official Python image with explicit platform support
FROM python:3.11-slim

# Build arguments for cache busting - forces fresh git clone
ARG CACHEBUST=1
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown

# Print architecture and build info for debugging
RUN echo "Building for architecture: $(uname -m)" && \
    echo "Platform: $(uname -s)" && \
    echo "Build date: ${BUILD_DATE}" && \
    echo "Git commit: ${GIT_COMMIT}" && \
    echo "Cache bust: ${CACHEBUST}" && \
    echo "Current GMT time: $(date -u +"%Y-%m-%d %H:%M:%S GMT")" && \
    python3 --version

# Set working directory
WORKDIR /app

# Set environment variables for better compatibility
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PDF_STORAGE_PATH=/app/pdf_storage

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

# Clone the latest main branch from GitHub with cache busting
# The CACHEBUST arg ensures this layer is never cached
RUN echo "Cache bust value: ${CACHEBUST}" && \
    echo "Cloning latest main branch from GitHub..." && \
    git clone --depth 1 --branch main https://github.com/aakashthakkar/ebook-reader.git . && \
    echo "Successfully cloned repository" && \
    echo "Current commit:" && \
    git log -1 --oneline || echo "No git history available" && \
    rm -rf .git && \
    echo "Repository contents:" && \
    ls -la && \
    echo "Python files found:" && \
    find . -name "*.py" -type f

# Upgrade pip and install Python dependencies
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Create PDF storage directory and set up user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/pdf_storage && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app && \
    chmod 755 /app/pdf_storage

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Create volume for PDF storage (can be mounted to host)
VOLUME ["/app/pdf_storage"]

# Add labels for better image management
LABEL maintainer="aakashthakkar" \
      description="PDF to Audio eBook Reader with Local Storage" \
      version="1.0"

# Health check with better error handling
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run the application
CMD ["python", "app.py"] 