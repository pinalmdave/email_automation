import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env", override=True)

# === IMAP ===
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")

# === Claude / Anthropic ===
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# === Email Filtering ===
EXCLUDED_DOMAINS = tuple(
    d.strip().lower()
    for d in os.getenv("EXCLUDED_DOMAINS", "linkedin.com,dice.com,monster.com,linked.com,gmail.com").split(",")
)
SCAN_FOLDERS = tuple(
    f.strip() for f in os.getenv("SCAN_FOLDERS", "INBOX,UPDATES,JOBS_INBOX").split(",")
)
MAX_EMAIL_AGE_HOURS = int(os.getenv("MAX_EMAIL_AGE_HOURS", "24"))

# === Resume evaluator-optimizer loop ===
# Max times the generator runs per email before we accept whatever we have.
MAX_RESUME_ITERATIONS = int(os.getenv("MAX_RESUME_ITERATIONS", "2"))
# Evaluator's numeric verdict >= threshold is treated as accepted.
RESUME_ACCEPTANCE_THRESHOLD = float(os.getenv("RESUME_ACCEPTANCE_THRESHOLD", "0.80"))

# === LangGraph execution ===
# Max super-steps per graph.invoke(). Heavy recruiter scans with the
# evaluator loop can consume ~11 super-steps per email — raise if needed.
GRAPH_RECURSION_LIMIT = int(os.getenv("GRAPH_RECURSION_LIMIT", "500"))

# === Claude API pricing (USD per 1M tokens) — overridable via .env ===
# Defaults are for claude-sonnet-4 as of this repo's current CLAUDE_MODEL.
CLAUDE_INPUT_COST_PER_MTOK = float(os.getenv("CLAUDE_INPUT_COST_PER_MTOK", "3.00"))
CLAUDE_OUTPUT_COST_PER_MTOK = float(os.getenv("CLAUDE_OUTPUT_COST_PER_MTOK", "15.00"))
CLAUDE_CACHE_WRITE_COST_PER_MTOK = float(os.getenv("CLAUDE_CACHE_WRITE_COST_PER_MTOK", "3.75"))
CLAUDE_CACHE_READ_COST_PER_MTOK = float(os.getenv("CLAUDE_CACHE_READ_COST_PER_MTOK", "0.30"))

# === Paths ===
TEMPLATES_DIR = BASE_DIR / "templates"
RESUME_TEMPLATE_PATH = TEMPLATES_DIR / "resume_template.docx"
PROMPTS_DIR = BASE_DIR / "prompts"
RESUME_PROMPT_PATH = PROMPTS_DIR / "resume_prompt.txt"
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

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
USAGE_TOTALS_PATH = BASE_DIR / "usage_totals.json"
PENDING_REPLIES_PATH = BASE_DIR / "pending_replies.json"
APPLY_PLANS_PATH = BASE_DIR / "apply_plans.json"

# === SMTP (used when user approves a pending reply) ===
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
