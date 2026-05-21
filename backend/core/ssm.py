import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from core.config import settings

logger = logging.getLogger(__name__)

# Maps SSM parameter names to the settings attribute they override.
# Key   = the path in Parameter Store (what was seeded in 01_bootstrap.sh)
# Value = the attribute name on the Settings object in config.py
_PARAMETER_MAP = {
    "/databridge/SECRET_KEY": "secret_key",
    "/databridge/DATABASE_URL": "database_url",
    "/databridge/REDIS_URL": "redis_url",
}


def _make_client() -> Any:
    """Build an SSM boto3 client, pointing at LocalStack if configured."""
    kwargs = {
        "region_name": "us-east-1",
        "config": Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1}),
    }
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
        kwargs["aws_access_key_id"] = "test"
        kwargs["aws_secret_access_key"] = "test"

    return boto3.client("ssm", **kwargs)


def fetch_parameter(name: str) -> str | None:
    """
    Fetch a single SecureString parameter from SSM.
    Returns the decrypted value, or None if anything goes wrong.
    """
    try:
        client = _make_client()
        response = client.get_parameter(Name=name, WithDecryption=True)
        return response["Parameter"]["Value"]
    except (BotoCoreError, ClientError) as e:
        # Log at debug level — a missing parameter is expected in environments
        # that don't use SSM (e.g. someone running without LocalStack).
        logger.debug("SSM parameter %s not available: %s", name, e)
        return None


def load_into_settings() -> None:
    """
    Fetch all known parameters from SSM and override the matching settings values.

    Called once at application startup. If SSM is unreachable or a parameter
    doesn't exist, the existing env-var value is kept — so this is purely additive
    and safe to call in any environment.
    """
    if not settings.aws_endpoint_url:
        # No endpoint configured means we're not pointing at LocalStack or real AWS —
        # skip SSM entirely so startup isn't slowed down by a connection attempt.
        logger.debug("AWS endpoint not configured — skipping SSM parameter load")
        return

    loaded = []
    for parameter_name, settings_attr in _PARAMETER_MAP.items():
        value = fetch_parameter(parameter_name)
        if value is not None:
            # Pydantic settings objects are normally immutable, but we can bypass
            # that with object.__setattr__ to set the value directly on the instance.
            object.__setattr__(settings, settings_attr, value)
            loaded.append(settings_attr)

    if loaded:
        print(f"SSM: loaded {', '.join(loaded)} from Parameter Store", flush=True)
    else:
        print("SSM: no parameters loaded (LocalStack may not be ready)", flush=True)
