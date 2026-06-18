import os
import boto3
from botocore.config import Config

# Cloudflare R2 (S3-compatible) storage layer for the KeySync worker — mirrors
# the LatentSync worker's utils/s3.py. Account-wide creds; the active bucket is
# selected per request from the job `level` (stag/prod).
#
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY  (RunPod secrets)
#   STAG_R2_BUCKET / PROD_R2_BUCKET  -> resolved into R2_BUCKET by set_bucket_for_level()

_client = None


def set_bucket_for_level(level: str):
    """Pick the active R2 bucket for stag/prod (no-op for test/local)."""
    if level == "stag":
        os.environ["R2_BUCKET"] = os.environ["STAG_R2_BUCKET"]
    elif level == "prod":
        os.environ["R2_BUCKET"] = os.environ["PROD_R2_BUCKET"]


def r2_client():
    global _client
    if _client is None:
        account_id = os.environ["R2_ACCOUNT_ID"]
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
        )
    return _client


def _bucket():
    return os.environ["R2_BUCKET"]


def _to_key(src: str) -> str:
    if src.startswith("s3://"):
        rest = src[len("s3://"):]
        return rest.split("/", 1)[1] if "/" in rest else rest
    return src.lstrip("/")


def download_key(key: str, local_path: str):
    r2_client().download_file(_bucket(), _to_key(key), local_path)


def download_url(url: str, local_path: str):
    """HTTP(S) download — SMOKE-TEST ONLY (level=test). Browser UA + streaming."""
    import requests

    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.get(url, timeout=60, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)


def upload_key(local_path: str, key: str) -> str:
    r2_client().upload_file(local_path, _bucket(), key)
    return key


def presigned_get(key: str, expires: int = 86400) -> str:
    return r2_client().generate_presigned_url(
        "get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=expires
    )
