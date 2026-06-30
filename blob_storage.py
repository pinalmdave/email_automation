"""
Azure Blob Storage service for resume files and pipeline state.

Resumes → AZURE_BLOB_CONTAINER           (default: "resumes")
State   → AZURE_BLOB_STATE_CONTAINER     (default: "state")

When AZURE_STORAGE_CONNECTION_STRING is unset the module becomes a no-op;
callers fall back to local-disk behavior transparently.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import (
    APPLY_PLANS_PATH,
    EMAIL_ACCOUNTS_PATH,
    FOLLOWUP_STATE_PATH,
    PENDING_REPLIES_PATH,
    STATE_FILE_PATH,
    USAGE_TOTALS_PATH,
)

logger = logging.getLogger(__name__)

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_BLOB_CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "resumes")
AZURE_BLOB_STATE_CONTAINER = os.getenv("AZURE_BLOB_STATE_CONTAINER", "state")

# The three JSON files we mirror between local disk and blob. Keyed by local path
# so a writer can just hand us the path it already has.
_STATE_FILES = {
    STATE_FILE_PATH: "processed_emails.json",
    FOLLOWUP_STATE_PATH: "followup_state.json",
    USAGE_TOTALS_PATH: "usage_totals.json",
    PENDING_REPLIES_PATH: "pending_replies.json",
    APPLY_PLANS_PATH: "apply_plans.json",
    EMAIL_ACCOUNTS_PATH: "email_accounts.json",
}


def _use_azure() -> bool:
    return bool(AZURE_STORAGE_CONNECTION_STRING)


def _get_blob_service():
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)


def _get_container_client(container: str):
    svc = _get_blob_service()
    client = svc.get_container_client(container)
    # Idempotent create — cheap if it already exists.
    try:
        client.create_container()
    except Exception:
        pass
    return client


# ---------------------------------------------------------------------------
# Resume upload + SAS URL
# ---------------------------------------------------------------------------

def upload_resume(local_path: Path) -> str:
    """Upload a resume DOCX to blob (or no-op locally). Returns the blob name."""
    filename = local_path.name
    if _use_azure():
        container = _get_container_client(AZURE_BLOB_CONTAINER)
        with open(local_path, "rb") as f:
            container.upload_blob(name=filename, data=f, overwrite=True)
        logger.info("Uploaded resume to Azure Blob: %s", filename)
    else:
        logger.info("Resume stored locally: %s", local_path)
    return filename


def generate_resume_sas_url(filename: str, minutes_valid: int = 60) -> Optional[str]:
    """Return a time-limited SAS URL for a resume blob, or None if blob is off."""
    if not _use_azure():
        return None
    from azure.storage.blob import BlobSasPermissions, generate_blob_sas

    svc = _get_blob_service()
    account_name = svc.account_name
    account_key = svc.credential.account_key if hasattr(svc.credential, "account_key") else None
    if not account_key:
        logger.warning("No account key available on credential — cannot generate SAS")
        return None

    sas = generate_blob_sas(
        account_name=account_name,
        container_name=AZURE_BLOB_CONTAINER,
        blob_name=filename,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=minutes_valid),
        content_disposition=f'attachment; filename="{filename}"',
    )
    return f"https://{account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{filename}?{sas}"


# ---------------------------------------------------------------------------
# State-file sync (processed_emails, followup_state, usage_totals)
# ---------------------------------------------------------------------------

def _blob_name_for(path: Path) -> Optional[str]:
    for known_path, blob_name in _STATE_FILES.items():
        if Path(path).resolve() == Path(known_path).resolve():
            return blob_name
    return None


def upload_state_file(local_path: Path) -> None:
    """Push a state JSON to its blob counterpart. Silent no-op if blob is off."""
    if not _use_azure():
        return
    blob_name = _blob_name_for(local_path)
    if not blob_name or not local_path.exists():
        return
    try:
        container = _get_container_client(AZURE_BLOB_STATE_CONTAINER)
        with open(local_path, "rb") as f:
            container.upload_blob(name=blob_name, data=f, overwrite=True)
        logger.debug("Synced %s to blob state container", blob_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to sync %s to blob: %s", blob_name, exc)


def download_state_file(local_path: Path) -> bool:
    """Pull a state JSON from blob to local disk. Returns True on successful write."""
    if not _use_azure():
        return False
    blob_name = _blob_name_for(local_path)
    if not blob_name:
        return False
    try:
        container = _get_container_client(AZURE_BLOB_STATE_CONTAINER)
        blob = container.get_blob_client(blob_name)
        if not blob.exists():
            return False
        data = blob.download_blob().readall()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        logger.info("Restored %s from blob state container (%d bytes)", blob_name, len(data))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to restore %s from blob: %s", blob_name, exc)
        return False


def bootstrap_state_from_blob() -> None:
    """Pull all known state files from blob to local disk at process startup.

    Always overwrites local copies so that a stale file bundled in the
    deployment zip never shadows the live production state stored in blob.
    """
    if not _use_azure():
        return
    for local_path in _STATE_FILES:
        # Always download — don't skip just because a (possibly stale) local
        # copy exists from the deployment zip.
        downloaded = download_state_file(local_path)
        if not downloaded:
            logger.debug("No blob copy for %s — using local file (or starting fresh)", local_path.name)
