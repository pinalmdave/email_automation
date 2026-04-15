import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env", override=True)

# === IMAP / SMTP ===
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", IMAP_USER or "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", IMAP_PASSWORD or "")

# === Claude / Anthropic ===
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# === Email Filtering ===
SUBJECT_KEYWORDS = tuple(
    kw.strip().lower()
    for kw in os.getenv("SUBJECT_KEYWORDS", "developer,architect,engineer,consultant").split(",")
)
EXCLUDED_DOMAINS = tuple(
    d.strip().lower()
    for d in os.getenv("EXCLUDED_DOMAINS", "linkedin.com,dice.com,monster.com,linked.com,gmail.com").split(",")
)
SCAN_FOLDERS = tuple(
    f.strip() for f in os.getenv("SCAN_FOLDERS", "INBOX,UPDATES").split(",")
)
MAX_EMAIL_AGE_HOURS = int(os.getenv("MAX_EMAIL_AGE_HOURS", "24"))

# === Scheduling ===
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "3600"))

# === Paths ===
TEMPLATES_DIR = BASE_DIR / "templates"
RESUME_TEMPLATE_PATH = TEMPLATES_DIR / "resume_template.docx"
PROMPTS_DIR = BASE_DIR / "prompts"
RESUME_PROMPT_PATH = PROMPTS_DIR / "resume_prompt.txt"

RESUME_OUTPUT_DIR = Path(
    os.getenv("RESUME_OUTPUT_DIR", str(Path.home() / "OneDrive" / "Desktop" / "CLAUDE_GENERATED_RESUME"))
)
try:
    RESUME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # In cloud environments the local path may not be writable; blob storage is used instead
    import tempfile
    RESUME_OUTPUT_DIR = Path(tempfile.gettempdir()) / "resumes"
    RESUME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE_PATH = BASE_DIR / "processed_emails.json"
FOLLOWUP_STATE_PATH = BASE_DIR / "followup_state.json"
