import os
import boto3
from botocore.config import Config

# ---------------------------------------------------------------------------
# Cloudflare R2 (S3-compatible) storage layer.
#
# Credentials are account-wide; the active bucket is selected per request by
# load_environment() in utils/utllity.py via the R2_BUCKET env var.
#
#   R2_ACCOUNT_ID         -> endpoint https://<account>.r2.cloudflarestorage.com
#   R2_ACCESS_KEY_ID      (RunPod secret)
#   R2_SECRET_ACCESS_KEY  (RunPod secret)
#   R2_BUCKET             (set by stag/prod routing)
#
# Inputs are R2 object KEYS, never arbitrary URLs. The only URL-download path
# (download_url) is gated to test/local smoke runs by the caller — fetching
# attacker-controlled URLs on the worker would be an SSRF vector in production.
# ---------------------------------------------------------------------------

_client = None


def r2_client():
    """Cached boto3 client pointed at this account's R2 endpoint.

    Safe to reuse across warm RunPod invocations: creds + endpoint are
    account-wide, and the bucket is resolved per call from R2_BUCKET.
    """
    global _client
    if _client is None:
        account_id = os.environ["R2_ACCOUNT_ID"]
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
    return _client


def _bucket():
    return os.environ["R2_BUCKET"]


def _to_key(src: str) -> str:
    """Normalise an input reference to a bare key against the active bucket.

    Tolerates legacy ``s3://bucket/key`` inputs by stripping scheme+bucket.
    """
    if src.startswith("s3://"):
        rest = src[len("s3://"):]
        return rest.split("/", 1)[1] if "/" in rest else rest
    return src.lstrip("/")


def download_key(key: str, local_path: str):
    """Download an R2 object by key to a local path."""
    r2_client().download_file(_bucket(), _to_key(key), local_path)


def download_url(url: str, local_path: str):
    """HTTP(S) download — SMOKE-TEST ONLY (test/local levels).

    Never call this with untrusted input: arbitrary URL fetch on the worker
    is an SSRF vector. Production inputs must be R2 keys (download_key).
    """
    import requests

    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.get(url, timeout=60, headers=headers, stream=True) as r:
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)


def upload_key(local_path: str, key: str) -> str:
    """Upload a local file to the active R2 bucket under ``key``. Returns the key."""
    r2_client().upload_file(local_path, _bucket(), key)
    return key


def presigned_get(key: str, expires: int = 86400) -> str:
    """Presigned GET URL for delivering a result (default 24h TTL)."""
    return r2_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=expires,
    )
