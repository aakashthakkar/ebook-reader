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

# Get current timestamp and git info for cache busting
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CACHE_BUST=$(date +%s)
DATE_TAG=$(date -u +"%Y%m%d-%H%M")  # Include hour and minute for multiple daily builds
GMT_TIME=$(date -u +"%H:%M:%S GMT")

# Try to get the latest commit hash from GitHub (fallback if not available)
echo "🔍 Fetching latest commit info from GitHub..."
GIT_COMMIT=$(curl -s https://api.github.com/repos/aakashthakkar/ebook-reader/commits/main | grep '"sha"' | head -n 1 | cut -d '"' -f 4 | cut -c1-8) || {
    echo "⚠️  Could not fetch commit hash from GitHub API, using timestamp"
    GIT_COMMIT="$(date +%Y%m%d-%H%M%S)"
}

echo "📋 Build info:"
echo "   Build Date: $BUILD_DATE"
echo "   GMT Time: $GMT_TIME"
echo "   Date Tag: $DATE_TAG"
echo "   Cache Bust: $CACHE_BUST"
echo "   Git Commit: $GIT_COMMIT"

# Ensure buildx builder is available
echo "🔧 Setting up buildx builder..."
docker buildx use multiarch-builder 2>/dev/null || {
    echo "Creating new buildx builder..."
    docker buildx create --name multiarch-builder --driver docker-container --bootstrap
    docker buildx use multiarch-builder
}

# Build and push for multiple architectures with cache busting
echo "🚀 Building and pushing multi-architecture image (forcing fresh git clone)..."
echo "🕐 Build time: $GMT_TIME"
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --push \
    --no-cache \
    --build-arg CACHEBUST="$CACHE_BUST" \
    --build-arg BUILD_DATE="$BUILD_DATE" \
    --build-arg GIT_COMMIT="$GIT_COMMIT" \
    --tag "$FULL_IMAGE_NAME" \
    --tag "${FULL_IMAGE_NAME%:*}:$DATE_TAG" \
    --label "org.opencontainers.image.source=https://github.com/aakashthakkar/ebook-reader" \
    --label "org.opencontainers.image.description=PDF to Audio eBook Reader" \
    --label "org.opencontainers.image.licenses=MIT" \
    --label "org.opencontainers.image.created=$BUILD_DATE" \
    --label "org.opencontainers.image.revision=$GIT_COMMIT" \
    --label "build.time.gmt=$GMT_TIME" \
    --label "build.date.tag=$DATE_TAG" \
    .

echo "✅ Successfully built and pushed: $FULL_IMAGE_NAME"
echo "📋 Image also tagged with date: ${FULL_IMAGE_NAME%:*}:$DATE_TAG"
echo "🔗 Built from commit: $GIT_COMMIT"
echo "🕐 Build completed at: $GMT_TIME"

# Show image info
echo "🔍 Image information:"
docker buildx imagetools inspect "$FULL_IMAGE_NAME"

echo ""
echo "🎉 Build and push completed successfully!"
echo "📖 To run the image:"
echo "   docker run -p 8000:8000 $FULL_IMAGE_NAME"
echo "   # Or use the timestamped version:"
echo "   docker run -p 8000:8000 ${FULL_IMAGE_NAME%:*}:$DATE_TAG"
echo ""
echo "💡 Supported platforms: linux/amd64, linux/arm64"
echo "🔄 This build always fetches the latest main branch from GitHub"
echo "⏰ Build timestamp: $DATE_TAG ($GMT_TIME)" 