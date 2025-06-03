# Deployment Guide

This document explains how to set up automated Docker image builds and deployments using GitHub Actions.

## 🔧 Setup Instructions

### 1. Configure GitHub Secrets

You need to add your Docker Hub credentials as GitHub secrets:

1. **Go to your GitHub repository**
   - Navigate to: `https://github.com/aakashthakkar/ebook-reader`

2. **Access Repository Settings**
   - Click on "Settings" tab
   - Click on "Secrets and variables" → "Actions"

3. **Add Required Secrets**
   Click "New repository secret" and add these two secrets:

   | Secret Name | Value | Description |
   |-------------|-------|-------------|
   | `DOCKER_USERNAME` | `thakkaraakash` | Your Docker Hub username |
   | `DOCKER_PASSWORD` | `your-docker-hub-password-or-token` | Your Docker Hub password or access token |

   **💡 Recommendation**: Use a Docker Hub Access Token instead of your password:
   - Go to [Docker Hub Account Settings](https://hub.docker.com/settings/security)
   - Click "New Access Token"
   - Give it a name like "GitHub Actions"
   - Copy the token and use it as `DOCKER_PASSWORD`

### 2. Verify Setup

Once the secrets are configured, any push to the `main` branch will automatically:

1. ✅ Build the Docker image for both `linux/amd64` and `linux/arm64`
2. ✅ Push to Docker Hub as `thakkaraakash/ebook-reader:latest`
3. ✅ Tag with today's date (e.g., `thakkaraakash/ebook-reader:20250603`)
4. ✅ Run security vulnerability scans
5. ✅ Provide build reports in GitHub Actions

## 🚀 Automated Triggers

The workflow runs automatically when:

- **Push to main branch** - Builds and pushes to Docker Hub
- **Pull Request** - Builds only (doesn't push) for testing
- **Manual trigger** - Can be triggered manually from GitHub Actions tab

### Excluded from triggers:
- Changes to `.md` files (like README)
- Changes to `.gitignore`
- Changes to `LICENSE`

## 📦 Generated Images

After each successful build, you'll get:

### Docker Hub Images
- `thakkaraakash/ebook-reader:latest` - Always the latest build
- `thakkaraakash/ebook-reader:YYYYMMDD` - Date-tagged version
- `thakkaraakash/ebook-reader:main-abc123` - Git SHA tagged version

### Multi-Architecture Support
All images support:
- **linux/amd64** - Intel/AMD processors
- **linux/arm64** - ARM processors (Apple Silicon, ARM servers)

## 🔍 Monitoring Builds

### GitHub Actions Dashboard
1. Go to your repository
2. Click "Actions" tab
3. View build status and logs

### Docker Hub Repository
Visit: `https://hub.docker.com/r/thakkaraakash/ebook-reader`

## 📋 Manual Build and Push

If you prefer to build locally:

```bash
# Using the provided script
./build-and-push.sh latest docker.io

# Manual buildx command
docker buildx build --platform linux/amd64,linux/arm64 --push --tag thakkaraakash/ebook-reader:latest .
```

## 🐛 Troubleshooting

### Build Fails
- Check GitHub Actions logs for detailed error messages
- Verify Docker Hub credentials in GitHub secrets
- Ensure Docker Hub repository exists: `thakkaraakash/ebook-reader`

### Authentication Issues
- Regenerate Docker Hub access token
- Update `DOCKER_PASSWORD` secret in GitHub
- Verify `DOCKER_USERNAME` is exactly `thakkaraakash`

### Permission Issues
- Ensure your Docker Hub account has push permissions
- Check if the repository is private and you have access

## 🎯 Usage

Once deployed, users can run your application:

```bash
# Pull and run the latest version
docker run -p 8000:8000 thakkaraakash/ebook-reader:latest

# Or using docker-compose
version: '3.8'
services:
  ebook-reader:
    image: thakkaraakash/ebook-reader:latest
    ports:
      - "8000:8000"
```

## 🔄 Workflow Features

- **✅ Multi-architecture builds** (AMD64 + ARM64)
- **✅ Automated testing** on pull requests
- **✅ Security scanning** with Trivy
- **✅ Build caching** for faster builds
- **✅ Metadata labeling** for better image management
- **✅ Date and SHA tagging** for version tracking

## 📈 Next Steps

Consider adding:
- **Staging deployments** for testing
- **Release workflows** with semantic versioning
- **Integration tests** before deployment
- **Slack/Discord notifications** for build status

## Docker Image Tags 🏷️

The Docker images are automatically tagged with multiple formats for flexibility:

- `latest` - Always points to the most recent successful build from main branch
- `YYYYMMDD-HHMM` - **NEW**: Timestamped builds with GMT time (hour:minute precision)
  - Example: `20250603-1910` = June 3rd, 2025 at 19:10 GMT
  - Allows multiple builds per day to be distinguished
- `YYYYMMDD` - **Legacy**: Date-only tags (deprecated in favor of time-specific tags)

### Examples:
```bash
# Latest version
docker run -p 8000:8000 thakkaraakash/ebook-reader:latest

# Specific timestamped build (with GMT time)
docker run -p 8000:8000 thakkaraakash/ebook-reader:20250603-1910

# All images include these labels for tracking:
# - build.time.gmt: "19:10:11 GMT"
# - build.date.tag: "20250603-1910"
# - org.opencontainers.image.created: "2025-06-03T19:10:11Z"
# - org.opencontainers.image.revision: <git-commit-hash>
```

## Build Process 🔄

### Cache Busting for Latest Code
The build process includes several mechanisms to ensure you **always get the latest code** from GitHub:

1. **`--no-cache` flag**: Disables Docker layer caching
2. **Dynamic build arguments**: Each build gets unique timestamps
3. **Fresh git clone**: Always clones latest main branch from GitHub
4. **GitHub API integration**: Fetches latest commit hash for verification

### Build Arguments:
- `CACHEBUST`: Unix timestamp ensuring no cache reuse
- `BUILD_DATE`: ISO 8601 formatted build timestamp  
- `GIT_COMMIT`: Latest commit hash from GitHub main branch 