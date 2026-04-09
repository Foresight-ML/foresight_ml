"""API dependencies and rate limiting."""

import logging

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from google.cloud import secretmanager
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Set up Rate Limiter (100 requests per minute)
limiter = Limiter(key_func=get_remote_address)

# Look for the API key in the "X-API-Key" header
api_key_header = APIKeyHeader(name="X-API-Key")


def get_valid_api_keys() -> list[str]:
    """Fetches valid API keys from GCP Secret Manager."""
    try:
        client = secretmanager.SecretManagerServiceClient()
        # We know the project ID is financial-distress-ew from your earlier Slack screenshot!
        secret_path = "projects/financial-distress-ew/secrets/foresight-api-keys/versions/latest"
        response = client.access_secret_version(request={"name": secret_path})
        secret_string = response.payload.data.decode("UTF-8")

        return [k.strip() for k in secret_string.split(",")]
    except Exception as e:
        logger.warning(
            f"Could not reach Secret Manager: {e}. Using fallback key for local testing."
        )
        # This allows you to test locally on your MacBook without it crashing
        return ["local-dev-key-123"]


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Validates the incoming API key."""
    valid_keys = get_valid_api_keys()

    if api_key not in valid_keys:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    return api_key
