# Building and Deploying to RunPod with Docker

## Prerequisites

- Docker installed on your machine
- Docker Hub account (or other registry: ECR, GCR, etc.)
- RunPod account with API key
- Model checkpoints (`latentsync_unet.pt`, `vgg16-397923af.pth`)

## Step 1: Build Docker Image Locally

```bash
cd ~/path/to/LatentSync

# Build image (takes 5-15 min depending on internet speed)
docker build -t latentsync:latest .

# Verify it built successfully
docker images | grep latentsync
```

**Output should show:**
```
latentsync    latest    abc123def456    5 minutes ago    12GB
```

## Step 2: Push to Docker Hub

```bash
# Log in to Docker Hub
docker login

# Tag image for your account
docker tag latentsync:latest YOUR_DOCKERHUB_USERNAME/latentsync:latest

# Push to registry
docker push YOUR_DOCKERHUB_USERNAME/latentsync:latest

# Verify it's uploaded
# Visit: https://hub.docker.com/r/YOUR_USERNAME/latentsync
```

Replace `YOUR_DOCKERHUB_USERNAME` with your actual Docker Hub username.

## Step 3: Prepare RunPod Network Volume

1. **In RunPod console** → Network Volumes → Create New
   - **Name:** `LatentSync-Models`
   - **Size:** 50 GB (or larger if you have multiple models)

2. **Upload checkpoints** (from your local machine):
   ```bash
   # RunPod provides an upload URL in the console
   # Or use rsync/scp if they support it
   # Or manually upload via the web UI
   ```

   **Files to upload:**
   - `checkpoints/latentsync_unet.pt` (~2-3 GB)
   - `checkpoints/auxiliary/vgg16-397923af.pth` (~500 MB)
   - `configs/` (optional, ~10 MB)

3. **Note the Volume ID** (you'll need it in the template)

## Step 4: Create RunPod Serverless Endpoint

1. **In RunPod console** → Serverless → Create New Endpoint

2. **Basic Settings:**
   - **Endpoint Name:** `LatentSync-Inference`
   - **Select GPU:** A40 / RTX 4090 / L40S (recommended for CUDA 12.1)

3. **Container Settings:**
   - **Container Image:** `YOUR_DOCKERHUB_USERNAME/latentsync:latest`
   - **Container Disk:** 20 GB
   - **Port Mapping:** Leave default

4. **Environment Variables:**
   ```
   CKPT_PATH=/runpod-volume/checkpoints/latentsync_unet.pt
   UNET_CONFIG_PATH=/runpod-volume/configs/unet/stage2.yaml
   ```

5. **Network Volume:**
   - **Select Volume:** `LatentSync-Models` (or whatever you named it)
   - **Mount Path:** `/runpod-volume`

6. **Advanced (optional):**
   - **Max Timeout:** 3600 (seconds; allows long inference)
   - **Idle Timeout:** 5 (auto-stop after 5 min of no jobs)

7. **Review and Deploy** → Click "Create Endpoint"

## Step 5: Get Your Endpoint Details

After deployment:
1. Go to your endpoint in RunPod console
2. Copy:
   - **Endpoint ID** (looks like `abc123def456`)
   - **API Key** (in Settings)

## Step 6: Test the Endpoint

### Using curl:

```bash
export ENDPOINT_ID="your-endpoint-id"
export API_KEY="your-api-key"

# Convert Google Drive URLs or use direct links
curl -X POST https://api.runpod.io/v2/$ENDPOINT_ID/runsync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "input": {
      "video_url": "https://drive.google.com/uc?id=1r1WKLuNyQDB86yXIIK_5dcbO1FKzopy6&export=download",
      "audio_url": "https://drive.google.com/uc?id=1QGFELgvKJKzIKRLB5sKCVRttQur0AWYO&export=download",
      "inference_steps": 20,
      "guidance_scale": 2
    }
  }' \
  --max-time 3600
```

### Using Python:

```python
import requests
import json
import base64

endpoint_id = "your-endpoint-id"
api_key = "your-api-key"

payload = {
    "input": {
        "video_url": "https://drive.google.com/uc?id=YOUR_FILE_ID&export=download",
        "audio_url": "https://drive.google.com/uc?id=YOUR_FILE_ID&export=download",
        "inference_steps": 20,
        "guidance_scale": 2,
        "seed": 42
    }
}

response = requests.post(
    f"https://api.runpod.io/v2/{endpoint_id}/runsync",
    json=payload,
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=3600
)

result = response.json()
print(json.dumps(result, indent=2))

# Save output video
if "output" in result and "video_base64" in result["output"]:
    video_data = base64.b64decode(result["output"]["video_base64"])
    with open("output.mp4", "wb") as f:
        f.write(video_data)
    print("✓ Video saved to output.mp4")
else:
    print("✗ Job failed:", result.get("output", {}).get("error"))
```

## Troubleshooting

### Docker Build Fails
- Check internet connection (large downloads)
- Try: `docker build --no-cache -t latentsync:latest .`
- Check disk space (need ~50 GB free)

### Docker Push Fails
- Verify logged in: `docker login`
- Check image name: `docker images`

### Endpoint Won't Start
- Check logs in RunPod console → Logs
- Common issues:
  - Checkpoint path wrong (verify `CKPT_PATH`)
  - Network Volume not mounted (check mount path)
  - Wrong GPU type (use A40 or better)

### Job Fails with "Checkpoint not found"
- Verify files are on the Network Volume
- Check `CKPT_PATH` env var matches actual file location
- Verify file permissions (readable by container)

### Job Timeout
- Inference can take 15-30 min for long videos
- Increase `Max Timeout` in endpoint template
- Use smaller `inference_steps` (10-15 instead of 20)

## Updating the Endpoint

After making code changes:

1. Rebuild image:
   ```bash
   docker build -t latentsync:latest .
   docker tag latentsync:latest YOUR_USERNAME/latentsync:latest
   docker push YOUR_USERNAME/latentsync:latest
   ```

2. Restart endpoint in RunPod console → Endpoint → Stop → Start

Or create a new endpoint with the updated image tag (e.g., `latest`, `v2`, etc.)

## Cost Estimation

**RunPod pricing (examples):**
- A40 GPU: ~$0.14/hour
- Inference time: 15-30 min per job
- Cost per job: ~$0.04-$0.07
- Network Volume: ~$0.05/GB/month (cheap storage)

Monitor usage in RunPod console → Billing.

---

## Next Steps

1. Commit these files to git:
   ```bash
   git add handler.py Dockerfile .dockerignore DOCKER_BUILD.md RUNPOD_TESTING.md
   git commit -m "add: RunPod serverless deployment support"
   git push origin main
   ```

2. Follow the steps above to build, push, and deploy

3. Test with the endpoint and monitor logs

4. Share your endpoint ID with others to run jobs
