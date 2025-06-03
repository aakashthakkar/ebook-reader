#!/bin/bash

# Build and Push Script for eBook Reader Multi-Architecture Images
# Usage: ./build-and-push.sh [tag] [registry]

set -e

# Configuration
IMAGE_NAME="ebook-reader"
DEFAULT_TAG="latest"
DEFAULT_REGISTRY="docker.io"  # Docker Hub

# Parse arguments
TAG=${1:-$DEFAULT_TAG}
REGISTRY=${2:-$DEFAULT_REGISTRY}

# Set image names based on registry
if [ "$REGISTRY" = "docker.io" ] || [ "$REGISTRY" = "dockerhub" ]; then
    FULL_IMAGE_NAME="thakkaraakash/${IMAGE_NAME}:${TAG}"
    echo "🐳 Building for Docker Hub: $FULL_IMAGE_NAME"
elif [ "$REGISTRY" = "ghcr.io" ] || [ "$REGISTRY" = "github" ]; then
    FULL_IMAGE_NAME="ghcr.io/aakashthakkar/${IMAGE_NAME}:${TAG}"
    echo "📦 Building for GitHub Container Registry: $FULL_IMAGE_NAME"
else
    FULL_IMAGE_NAME="${REGISTRY}/thakkaraakash/${IMAGE_NAME}:${TAG}"
    echo "🏭 Building for custom registry: $FULL_IMAGE_NAME"
fi

echo "🏗️  Starting multi-architecture build..."

# Ensure buildx builder is available
echo "🔧 Setting up buildx builder..."
docker buildx use multiarch-builder 2>/dev/null || {
    echo "Creating new buildx builder..."
    docker buildx create --name multiarch-builder --driver docker-container --bootstrap
    docker buildx use multiarch-builder
}

# Build and push for multiple architectures
echo "🚀 Building and pushing multi-architecture image..."
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --push \
    --tag "$FULL_IMAGE_NAME" \
    --tag "${FULL_IMAGE_NAME%:*}:$(date +%Y%m%d)" \
    --label "org.opencontainers.image.source=https://github.com/aakashthakkar/ebook-reader" \
    --label "org.opencontainers.image.description=PDF to Audio eBook Reader" \
    --label "org.opencontainers.image.licenses=MIT" \
    .

echo "✅ Successfully built and pushed: $FULL_IMAGE_NAME"
echo "📋 Image also tagged with date: ${FULL_IMAGE_NAME%:*}:$(date +%Y%m%d)"

# Show image info
echo "🔍 Image information:"
docker buildx imagetools inspect "$FULL_IMAGE_NAME"

echo ""
echo "🎉 Build and push completed successfully!"
echo "📖 To run the image:"
echo "   docker run -p 8000:8000 $FULL_IMAGE_NAME"
echo ""
echo "💡 Supported platforms: linux/amd64, linux/arm64" 