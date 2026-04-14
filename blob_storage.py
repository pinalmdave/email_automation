"""
Azure Blob Storage service for resume file management.
Falls back to local filesystem when AZURE_STORAGE_CONNECTION_STRING is not set.
"""

import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

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


def upload_resume_bytes(filename: str, data: bytes) -> str:
    """Upload resume bytes directly to blob storage."""
    if _use_azure():
        container = _get_container_client()
        container.upload_blob(name=filename, data=data, overwrite=True)
        logger.info("Uploaded resume bytes to Azure Blob: %s", filename)
    else:
        out_path = RESUME_OUTPUT_DIR / filename
        out_path.write_bytes(data)
        logger.info("Resume saved locally: %s", out_path)
    return filename


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_resume(filename: str) -> Optional[BytesIO]:
    """
    Download a resume from Azure Blob Storage (or local).
    Returns a BytesIO object, or None if not found.
    """
    if _use_azure():
        try:
            container = _get_container_client()
            blob_client = container.get_blob_client(filename)
            stream = blob_client.download_blob()
            buf = BytesIO(stream.readall())
            buf.seek(0)
            return buf
        except Exception as e:
            logger.warning("Blob download failed for %s: %s", filename, e)
            return None
    else:
        local_path = RESUME_OUTPUT_DIR / filename
        if local_path.exists():
            return BytesIO(local_path.read_bytes())
        return None


def get_resume_local_path(filename: str) -> Optional[Path]:
    """
    Get a local file path for the resume. Downloads from blob if needed.
    Used by email_drafter to attach the file.
    """
    import tempfile

    if _use_azure():
        buf = download_resume(filename)
        if buf is None:
            return None
        tmp = Path(tempfile.gettempdir()) / filename
        tmp.write_bytes(buf.read())
        return tmp
    else:
        path = RESUME_OUTPUT_DIR / filename
        return path if path.exists() else None


# ---------------------------------------------------------------------------
# List / Metadata
# ---------------------------------------------------------------------------

def list_resumes():
    """List all resume filenames with metadata."""
    results = []
    if _use_azure():
        container = _get_container_client()
        for blob in container.list_blobs():
            if blob.name.endswith(".docx"):
                results.append({
                    "filename": blob.name,
                    "size_bytes": blob.size,
                    "created_at": blob.creation_time.isoformat() if blob.creation_time else "",
                })
    else:
        from datetime import datetime, timezone
        if not RESUME_OUTPUT_DIR.exists():
            return results
        for f in sorted(RESUME_OUTPUT_DIR.glob("*.docx")):
            stat = f.stat()
            results.append({
                "filename": f.name,
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            })
    return results


def get_blob_url(filename: str) -> str:
    """Get the public URL for a blob."""
    if _use_azure():
        account_name = _get_blob_service().account_name
        return f"https://{account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{filename}"
    return ""
