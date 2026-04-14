"""
FastAPI application entry point for the Claude Smart Email App.
"""

import os
import sys
from pathlib import Path

# Add project root to path so we can import config, main, etc.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from config import WEB_API_PORT

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3001,http://127.0.0.1:3001").split(",")

# redirect_slashes=False prevents 307 redirects from /api/dashboard to /api/dashboard/
# which cause http:// redirect issues behind Azure's HTTPS proxy
app = FastAPI(title="Claude Smart Email App", version="3.0", redirect_slashes=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Include routers
from api.routers import conversations, dashboard, drafts, emails, pipeline, resumes

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(emails.router, prefix="/api/emails", tags=["Emails"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["Resumes"])
app.include_router(drafts.router, prefix="/api/drafts", tags=["Drafts"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["Conversations"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="127.0.0.1", port=WEB_API_PORT, reload=True)
