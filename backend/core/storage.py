from typing import Any

import boto3
from botocore.config import Config

from core.config import settings


def _make_client(endpoint_url: str = "") -> Any:
    kwargs: dict = {
        "region_name": "us-east-1",
        "config": Config(signature_version="s3v4"),
    }
    url = endpoint_url or settings.aws_endpoint_url
    if url:
        kwargs["endpoint_url"] = url
        kwargs["aws_access_key_id"] = "test"
        kwargs["aws_secret_access_key"] = "test"

    return boto3.client("s3", **kwargs)


def upload(key: str, data: bytes, content_type: str) -> None:
    client = _make_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def presign(key: str, expiry: int | None = None) -> str:
    # Use the public URL so browsers can reach the link (localhost vs internal Docker hostname)
    client = _make_client(endpoint_url=settings.s3_public_url)
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expiry or settings.s3_export_expiry,
    )
