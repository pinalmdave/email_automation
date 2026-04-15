"""
Azure Blob Storage service for resume file management.
Falls back to local filesystem when AZURE_STORAGE_CONNECTION_STRING is not set.
"""

import logging
import os
from pathlib import Path

from config import RESUME_OUTPUT_DIR

logger = logging.getLogger(__name__)

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_BLOB_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "resumes")


def _use_azure() -> bool:
    return bool(AZURE_STORAGE_CONNECTION_STRING)


def _get_blob_service():
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)


def _get_container_client():
    return _get_blob_service().get_container_client(AZURE_BLOB_CONTAINER)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_resume(local_path: Path) -> str:
    """
    Upload a resume DOCX to Azure Blob Storage (or keep local).
    Returns the blob name (filename) that can be used to retrieve it later.
    """
    filename = local_path.name

    if _use_azure():
        container = _get_container_client()
        with open(local_path, "rb") as f:
            container.upload_blob(name=filename, data=f, overwrite=True)
        logger.info("Uploaded resume to Azure Blob: %s", filename)
    else:
        # Local mode — file is already saved by resume_generator
        logger.info("Resume stored locally: %s", local_path)

    return filename
