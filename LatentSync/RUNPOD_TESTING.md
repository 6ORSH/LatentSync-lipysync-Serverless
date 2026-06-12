# Testing the RunPod Endpoint

## Pre-Deployment Setup: Model Checkpoints

The Docker image does **not** include model checkpoints (too large). You must provide them at runtime:

**Required files:**
- `latentsync_unet.pt` — main lip-sync model (~2-3 GB)
- `auxiliary/vgg16-397923af.pth` — LPIPS perceptual loss weights

**Setup options:**

### Option A: RunPod Network Volume (Recommended)
1. Create a Network Volume in RunPod console
2. Upload your `checkpoints/` folder to it
3. In your Serverless endpoint template, mount at `/runpod-volume`
4. Set environment variables in the template:
   ```
   CKPT_PATH=/runpod-volume/checkpoints/latentsync_unet.pt
   UNET_CONFIG_PATH=/runpod-volume/configs/unet/stage2.yaml
   ```

### Option B: Custom Mount Point
- Mount your volume at any path (e.g., `/mnt/models`)
- Set env var: `CKPT_PATH=/mnt/models/latentsync_unet.pt`

---

## Local Testing (Before Deployment)

If you have sample video and audio files locally:

```bash
python test_handler.py path/to/video.mp4 path/to/audio.wav
```

This tests the full pipeline without needing a RunPod account or deployment.

---

## RunPod API Testing (After Deployment)

Once deployed to RunPod, test via the RunPod API:

### 1. Get Your Endpoint URL and API Key

In the RunPod dashboard:
- Go to your serverless endpoint
- Copy the **Endpoint ID** and **API Key**

### 2. Verify Checkpoints Are Mounted

Before testing, ensure the model checkpoints are available:
- If you mounted a Network Volume, the files should be accessible at the path you set in `CKPT_PATH`
- Jobs will fail with a clear error if checkpoints are missing

### 3. Upload Test Files

Upload your video and audio files to a cloud storage with public/signed URLs:
- AWS S3 (pre-signed URL)
- Google Cloud Storage
- Hugging Face Hub
- Any HTTP-accessible location

### 4. Run a Test Job

**Using curl:**

```bash
ENDPOINT_ID="your-endpoint-id"
API_KEY="your-api-key"

curl -X POST https://api.runpod.io/v2/$ENDPOINT_ID/runsync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "input": {
      "video_url": "https://example.com/video.mp4",
      "audio_url": "https://example.com/audio.wav",
      "guidance_scale": 2.0,
      "inference_steps": 20,
      "seed": 42
    }
  }'
```

**Using Python:**

```python
import requests
import json
import base64

endpoint_id = "your-endpoint-id"
api_key = "your-api-key"

payload = {
    "input": {
        "video_url": "https://example.com/video.mp4",
        "audio_url": "https://example.com/audio.wav",
        "guidance_scale": 2.0,
        "inference_steps": 20,
        "seed": 42,
    }
}

response = requests.post(
    f"https://api.runpod.io/v2/{endpoint_id}/runsync",
    json=payload,
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=600,  # 10 minute timeout (jobs can be slow)
)

result = response.json()
print(json.dumps(result, indent=2))

# If successful, extract the video
if "output" in result and "video_base64" in result["output"]:
    video_data = base64.b64decode(result["output"]["video_base64"])
    with open("output.mp4", "wb") as f:
        f.write(video_data)
    print("Video saved to output.mp4")
```

### 5. Response Format

**Success (200 OK):**
```json
{
  "delayTime": 5000,
  "executionTime": 245000,
  "id": "job-uuid",
  "output": {
    "video_base64": "iVBORw0KGgoAAAANSUhEU...",
    "seed": 42
  },
  "status": "COMPLETED"
}
```

**Error:**
```json
{
  "delayTime": 500,
  "executionTime": 1000,
  "id": "job-uuid",
  "output": {
    "error": "video_url and audio_url are required"
  },
  "status": "FAILED"
}
```

### 6. Async Jobs (For Longer Runs)

If inference takes longer than your timeout, use async jobs:

```bash
# Start job
curl -X POST https://api.runpod.io/v2/$ENDPOINT_ID/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "input": {
      "video_url": "...",
      "audio_url": "..."
    }
  }'
# Returns: {"id": "job-uuid", "status": "IN_QUEUE"}

# Check status
curl https://api.runpod.io/v2/$ENDPOINT_ID/status/job-uuid \
  -H "Authorization: Bearer $API_KEY"
```

---

## Expected Performance

- **Cold start** (~30-60s): First request loads the model
- **Inference**: 15-30min depending on video length and `inference_steps`
- **Total** (first run): 15.5-30+ minutes

---

## Debugging

### Handler Logs

View logs in the RunPod dashboard under your endpoint → **Logs**.

### Common Issues

| Issue | Fix |
|-------|-----|
| `"error": "video_url and audio_url are required"` | Ensure both URLs are in `input` object |
| Download timeout | Increase `--default-timeout` in Dockerfile |
| OOM (out of memory) | Reduce `inference_steps` or use a smaller model |
| CUDA out of memory | Same as above, or use a GPU with more VRAM |

### Missing Checkpoints Error

If you see:
```
"error": "Checkpoint not found at /runpod-volume/checkpoints/latentsync_unet.pt. 
Mount it via RunPod Network Volume or set CKPT_PATH env var to the absolute path."
```

**Fix:**
1. Verify the Network Volume is mounted and contains the checkpoints
2. Verify `CKPT_PATH` env var is set correctly (absolute path)
3. Check file permissions (should be readable by the container)

### Test with Async to See Full Logs

Async jobs show more detailed logs in the RunPod dashboard, which helps debugging.
