# Unraid GPU Setup Guide

This guide explains how to run the eBook Reader with GPU acceleration on Unraid.

## Prerequisites

1. **NVIDIA Driver Plugin**: Install the NVIDIA Driver plugin from Unraid's Community Apps
2. **Compatible GPU**: NVIDIA GPU with CUDA Compute Capability 3.5 or higher
3. **Docker with GPU Support**: Ensure your Unraid server has GPU passthrough enabled

## Installation Steps

### 1. Install NVIDIA Driver Plugin

1. Navigate to **Apps** tab in Unraid web interface
2. Search for "NVIDIA Driver"
3. Install the plugin (usually called "Nvidia-Driver" by ich777)
4. Wait for installation to complete and reboot if prompted

### 2. Verify GPU Detection

Open a terminal/SSH session on your Unraid server and run:

```bash
nvidia-smi
```

You should see your GPU information displayed. If not, check the NVIDIA Driver plugin settings.

## Docker Deployment

### Option A: Docker Run Command

Use the following command to deploy with GPU support:

```bash
docker run -d \
  --name=ebook-reader \
  --gpus all \
  -p 8000:8000 \
  -v /mnt/user/appdata/ebook-reader/pdf_storage:/app/pdf_storage \
  -v /mnt/user/appdata/ebook-reader/music_storage:/app/music_storage \
  -e SUPABASE_URL=your_supabase_url \
  -e SUPABASE_ANON_KEY=your_anon_key \
  -e SUPABASE_SERVICE_ROLE_KEY=your_service_role_key \
  --restart unless-stopped \
  thakkaraakash/ebook-reader:latest
```

**Key flags:**
- `--gpus all`: Gives the container access to all GPUs
- `--gpus '"device=0"'`: To use only GPU 0 (if you have multiple GPUs)

### Option B: Docker Compose

Create a `docker-compose.yml` file:

```yaml
version: '3.8'
services:
  ebook-reader:
    image: thakkaraakash/ebook-reader:latest
    container_name: ebook-reader
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    ports:
      - "8000:8000"
    volumes:
      - /mnt/user/appdata/ebook-reader/pdf_storage:/app/pdf_storage
      - /mnt/user/appdata/ebook-reader/music_storage:/app/music_storage
    environment:
      - SUPABASE_URL=your_supabase_url
      - SUPABASE_ANON_KEY=your_anon_key
      - SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
    restart: unless-stopped
```

Then run:

```bash
docker-compose up -d
```

### Option C: Unraid Template

1. Go to **Docker** tab in Unraid
2. Click **Add Container**
3. Fill in the following:
   - **Name**: `ebook-reader`
   - **Repository**: `thakkaraakash/ebook-reader:latest`
   - **Network Type**: `Bridge`
   - **Port**: `8000` → `8000`
   - **Extra Parameters**: `--gpus all`
   - **Path 1**: Container: `/app/pdf_storage` → Host: `/mnt/user/appdata/ebook-reader/pdf_storage`
   - **Path 2**: Container: `/app/music_storage` → Host: `/mnt/user/appdata/ebook-reader/music_storage`
   - **Variable 1**: `SUPABASE_URL` (optional)
   - **Variable 2**: `SUPABASE_ANON_KEY` (optional)
   - **Variable 3**: `SUPABASE_SERVICE_ROLE_KEY` (optional)

**Important**: Add `--gpus all` to the **Extra Parameters** field!

## Verify GPU Usage

### Check if GPU is Accessible in Container

```bash
docker exec -it ebook-reader nvidia-smi
```

This should show your GPU information from inside the container.

### Check PyTorch GPU Detection

```bash
docker exec -it ebook-reader python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU count: {torch.cuda.device_count()}'); print(f'GPU name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

Expected output:
```
CUDA available: True
GPU count: 1
GPU name: NVIDIA GeForce RTX 3080
```

## Performance Benefits

With GPU acceleration:
- **Text-to-Speech (TTS)**: Up to 5-10x faster audio generation
- **Neural voice synthesis**: Real-time or faster-than-real-time processing
- **Lower CPU usage**: Offloads heavy computations to GPU

Without GPU (CPU fallback):
- Still functional, but slower TTS generation
- Higher CPU usage during audio generation

## Troubleshooting

### GPU Not Detected

1. **Check NVIDIA Driver Plugin**: Ensure it's installed and running
   ```bash
   nvidia-smi
   ```

2. **Verify Docker Runtime**: Check if NVIDIA runtime is available
   ```bash
   docker info | grep -i runtime
   ```
   Should show `nvidia` in the list.

3. **Check Container Logs**:
   ```bash
   docker logs ebook-reader
   ```
   Look for CUDA-related errors.

### CUDA Version Mismatch

If you see CUDA version errors:
- The image uses CUDA 11.8, which is compatible with most modern NVIDIA drivers
- Ensure your NVIDIA driver version is 450.80.02 or higher
- Check driver version: `nvidia-smi | grep "Driver Version"`

### Container Won't Start with --gpus Flag

If the container fails with the GPU flag:
1. The application will work without GPU (CPU fallback)
2. Remove `--gpus all` flag and run with CPU-only mode
3. Check NVIDIA Container Toolkit installation

### Limited GPU Memory

If you have limited GPU memory:
- The TTS model is relatively small (~200-500MB)
- Close other GPU-intensive applications
- Monitor GPU memory: `nvidia-smi -l 1`

## Architecture-Specific Notes

### AMD64 (x86_64) - Unraid Server
- **Full CUDA support enabled** ✅
- PyTorch with CUDA 11.8
- GPU acceleration for TTS
- Recommended for maximum performance
- **This is what you'll use on Unraid**

### ARM64 (e.g., Raspberry Pi)
- CPU-only PyTorch automatically installed
- No CUDA support (ARM doesn't support NVIDIA CUDA)
- Still functional, just slower
- Useful for testing or low-power deployments

**Note**: The Dockerfile automatically detects your architecture and installs the correct PyTorch version:
- `x86_64` → CUDA-enabled PyTorch (for GPU acceleration)
- `aarch64`/`arm64` → CPU-only PyTorch

## Additional Resources

- [NVIDIA Docker Documentation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- [Unraid NVIDIA Plugin Forum](https://forums.unraid.net/topic/98978-plugin-nvidia-driver/)
- [PyTorch CUDA Requirements](https://pytorch.org/get-started/locally/)

## Questions?

- Check the main [README.md](README.md) for general setup
- Review [DEPLOYMENT.md](DEPLOYMENT.md) for deployment options
- Open an issue on GitHub for GPU-specific problems

