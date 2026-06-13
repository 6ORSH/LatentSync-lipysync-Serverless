import boto3
import os
# from utils.utllity import (
#     AWS_ACCESS_KEY_ID,
#     AWS_SECRET_ACCESS_KEY,
#     AWS_REGION,
#     S3_BUCKET,
# )

def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ["AWS_REGION"],
    )

def download_file(s3_uri, local_path):
    if s3_uri.startswith("http"):
        import requests
        # Browser UA: hosts like catbox/Cloudflare drop bare python-requests
        # connections. Stream to disk to handle large files.
        headers = {"User-Agent": "Mozilla/5.0"}
        with requests.get(s3_uri, timeout=60, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
        return

    # s3://bucket/key
    _, _, bucket, *key = s3_uri.split("/")
    key = "/".join(key)

    s3 = get_s3_client()
    s3.download_file(bucket, key, local_path)

def upload_file(local_path, key):
    s3 = get_s3_client()
    bucket = os.environ["LAMBDA_BUCKET"]
    s3.upload_file(local_path, bucket, key)
    return f"s3://{bucket}/{key}"
