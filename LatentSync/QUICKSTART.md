# Quick Start: Deploy to RunPod

**TL;DR version of [DOCKER_BUILD.md](DOCKER_BUILD.md)**

## 5-Minute Setup

### 1. Build & Push Image
```bash
docker build -t latentsync:latest .
docker tag latentsync:latest YOUR_DOCKERHUB_USERNAME/latentsync:latest
docker push YOUR_DOCKERHUB_USERNAME/latentsync:latest
```

### 2. Prepare Checkpoints
- Create RunPod Network Volume
- Upload `checkpoints/` folder to it
- Note the Volume ID

### 3. Deploy to RunPod
In RunPod console:
1. **Serverless** → **Create Endpoint**
2. **Container Image:** `YOUR_USERNAME/latentsync:latest`
3. **Environment Variables:**
   ```
   CKPT_PATH=/runpod-volume/checkpoints/latentsync_unet.pt
   UNET_CONFIG_PATH=/runpod-volume/configs/unet/stage2.yaml
   ```
4. **Network Volume:** Mount at `/runpod-volume`
5. **Create**

### 4. Copy Endpoint ID & API Key
- From RunPod console → your endpoint

### 5. Test
```bash
curl -X POST https://api.runpod.io/v2/$ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "input": {
      "video_url": "https://example.com/video.mp4",
      "audio_url": "https://example.com/audio.wav"
    }
  }'
```

---

## Key Files

- **[handler.py](handler.py)** — RunPod serverless handler
- **[Dockerfile](Dockerfile)** — Container image definition
- **[.dockerignore](.dockerignore)** — Exclude large files from build
- **[DOCKER_BUILD.md](DOCKER_BUILD.md)** — Full deployment guide
- **[RUNPOD_TESTING.md](RUNPOD_TESTING.md)** — Testing & troubleshooting

---

## Job Request Format

```json
{
  "input": {
    "video_url": "https://example.com/video.mp4",
    "audio_url": "https://example.com/audio.wav",
    "inference_steps": 20,
    "guidance_scale": 2.0,
    "seed": 42
  }
}
```

**Response:**
```json
{
  "status": "COMPLETED",
  "output": {
    "video_base64": "iVBORw0KGgo...",
    "seed": 42
  }
}
```

---

## Expected Performance

- **Cold start:** 1-2 min (load model onto GPU)
- **Inference:** 15-30 min (depends on video length & steps)
- **Total:** 16-32 min first job, 15-30 min subsequent jobs

---

See [DOCKER_BUILD.md](DOCKER_BUILD.md) for full details.
