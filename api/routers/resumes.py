"""Resumes router — list, download, and preview generated resumes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.data_service import get_resume_path, list_resumes

router = APIRouter()


@router.get("/")
def list_all_resumes():
    """Return metadata for all generated DOCX resumes."""
    return list_resumes()


@router.get("/{filename}/download")
def download_resume(filename: str):
    """Serve a resume DOCX file for download."""
    path = get_resume_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{filename}/preview")
def preview_resume(filename: str):
    """Extract and return plain text from a resume DOCX."""
    path = get_resume_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Resume not found")

    try:
        from docx import Document

        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return {"filename": filename, "text": "\n".join(paragraphs)}
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="python-docx is not installed; cannot preview DOCX files",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading DOCX: {e}")
