"""System health endpoint router."""

import json
import logging
from typing import Any, cast

import gcsfs
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
async def get_health() -> dict[str, str]:
    """Basic health check (exempt from rate limits and auth)."""
    return {"status": "healthy"}


@router.get("/model/info")
async def get_model_info() -> dict[str, Any]:
    """Reads the latest manifest.json to show current model metadata."""
    try:
        fs = gcsfs.GCSFileSystem()
        manifest_path = "gs://financial-distress-data/inference/scores_v1.0/manifest.json"

        with fs.open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        return cast(dict[str, Any], manifest_data)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Manifest file not found.") from None
    except Exception as e:
        logger.error(f"Error reading manifest: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
