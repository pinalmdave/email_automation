"""
train_from_sent_mail.py — One-shot training pass over Pinal's Sent folder.

For the last N days (default 120), scans [Gmail]/Sent Mail for replies to
recruiters, pairs each sent message with the inbound message it was
replying to (matched via In-Reply-To / References headers against
[Gmail]/All Mail), filters out non-recruiter threads, anonymizes
recipient identities, and sends the batch to Claude to extract common
question → reply patterns. Outputs:

  knowledge/reply_templates_learned.md   — proposed additions (user reviews)
  scripts/train_report.md                — expanded report with the
                                            anonymized snippets that
                                            shaped each pattern

USAGE
-----
  # 1. Preview what would be processed — no Claude calls, zero cost.
  python scripts/train_from_sent_mail.py --dry-run

  # 2. Real run — sends pairs to Claude, writes the two files.
  python scripts/train_from_sent_mail.py

  # Optional knobs:
  python scripts/train_from_sent_mail.py --days 90 --max-pairs 150

Requires the same IMAP + ANTHROPIC_API_KEY env vars the app uses
(pick them up from .env). Reads ALL MAIL to resolve parent threads,
which needs the Gmail All-Mail folder enabled for IMAP (it is by default).
"""

import argparse
import email
import imaplib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Windows console is cp1252 by default — subjects often contain UTF-8 BOMs
# and non-latin chars that will crash print(). Reconfigure to UTF-8 with
# replace-on-error so nothing blows up on exotic message headers.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

# Make config.py importable when running from repo root or scripts/.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env", override=True)

from config import (                              # noqa: E402
    CLAUDE_MODEL,
    EXCLUDED_DOMAINS,
    IMAP_HOST,
    IMAP_PASSWORD,
    IMAP_PORT,
    IMAP_USER,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class EmailMsg:
    uid: str
    folder: str
    message_id: str
    in_reply_to: str
    references: List[str]
    from_email: str
    to_email: str
    subject: str
    date: str
    body: str
    dt: Optional[datetime] = None

    @property
    def from_domain(self) -> str:
        m = re.search(r"@([\w.-]+\.[a-zA-Z]{2,})", self.from_email)
        return (m.group(1).lower() if m else "").lstrip("www.")

    @property
    def to_domain(self) -> str:
        m = re.search(r"@([\w.-]+\.[a-zA-Z]{2,})", self.to_email)
        return (m.group(1).lower() if m else "").lstrip("www.")


@dataclass
class Pair:
    idx: int
    recruiter: EmailMsg
    reply: EmailMsg
    anon_label: str = ""


# ---------------------------------------------------------------------------
# IMAP helpers
# ---------------------------------------------------------------------------

def _connect() -> imaplib.IMAP4_SSL:
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")
    m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    m.login(IMAP_USER, IMAP_PASSWORD)
    return m


def _find_folder(mail: imaplib.IMAP4_SSL, substr: str) -> Optional[str]:
    """Find first mailbox whose name contains substr (case-insensitive)."""
    status, folders = mail.list()
    if status != "OK":
        return None
    needle = substr.lower()
    for f in folders or []:
        line = f.decode() if isinstance(f, bytes) else str(f)
        parts = line.split('"')
        name = parts[-2] if len(parts) >= 2 else ""
        if needle in name.lower():
            return name
    return None


def _decode_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                for enc in ("utf-8", "latin-1"):
                    try: return payload.decode(enc)
                    except Exception: continue
                return payload.decode("utf-8", errors="replace")
        # Fall back to first text/* part
        for part in msg.walk():
            if part.get_content_type().startswith("text/"):
                payload = part.get_payload(decode=True) or b""
                return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode("utf-8", errors="replace")


def _strip_quoted(body: str) -> str:
    """Drop quoted history from a reply body so we compare only the new text."""
    lines = body.splitlines()
    kept: List[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith(">"): break
        if re.match(r"^On .+ wrote:\s*$", s): break
        if s.startswith("-- "): break
        if re.match(r"^From: .+<.+>$", s, re.IGNORECASE): break
        kept.append(line)
    return "\n".join(kept).strip()


def _parse_header_list(raw: str) -> List[str]:
    """Split a header that's a whitespace-separated list of <id> tokens."""
    if not raw:
        return []
    return [m.group(0) for m in re.finditer(r"<[^>]+>", raw)]


def _decode_mime_header(raw: Optional[str]) -> str:
    """Decode RFC 2047 encoded headers (=?UTF-8?Q?...?=) to plain text."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return raw.strip()


def _to_email_msg(raw: bytes, folder: str, uid: str) -> EmailMsg:
    msg = email.message_from_bytes(raw)
    date_str = (msg.get("Date") or "").strip()
    dt: Optional[datetime] = None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return EmailMsg(
        uid=uid,
        folder=folder,
        message_id=(msg.get("Message-ID") or "").strip(),
        in_reply_to=(msg.get("In-Reply-To") or "").strip(),
        references=_parse_header_list(msg.get("References") or ""),
        from_email=_decode_mime_header(msg.get("From")),
        to_email=_decode_mime_header(msg.get("To")),
        subject=_decode_mime_header(msg.get("Subject")),
        date=date_str,
        body=_decode_body(msg),
        dt=dt,
    )


def fetch_sent(mail: imaplib.IMAP4_SSL, days: int) -> List[EmailMsg]:
    folder = _find_folder(mail, "Sent Mail") or _find_folder(mail, "Sent") or "[Gmail]/Sent Mail"
    logger.info("Sent folder: %s", folder)
    status, _ = mail.select(f'"{folder}"', readonly=True)
    if status != "OK":
        logger.error("Could not select sent folder")
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    status, data = mail.search(None, f"(SINCE {since})")
    if status != "OK":
        return []
    uids = data[0].split()
    logger.info("Scanning %d sent message(s) from last %d days", len(uids), days)
    out: List[EmailMsg] = []
    for uid in uids:
        _, d = mail.fetch(uid, "(RFC822)")
        if not d or not d[0]:
            continue
        try:
            raw = d[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            out.append(_to_email_msg(raw, folder, uid.decode()))
        except Exception as exc:
            logger.debug("Parse failed uid=%s: %s", uid, exc)
    return out


def lookup_parent(
    mail: imaplib.IMAP4_SSL,
    all_mail_folder: str,
    candidate_ids: List[str],
) -> Optional[EmailMsg]:
    """Find the inbound message a reply was sent in response to."""
    if not candidate_ids:
        return None
    # Gmail IMAP respects HEADER Message-ID searches on All Mail.
    for mid in candidate_ids:
        if not mid:
            continue
        # Escape quotes in the message-id for IMAP literal.
        quoted = mid.replace('"', '\\"')
        try:
            status, data = mail.search(None, 'HEADER', 'Message-ID', f'"{quoted}"')
        except Exception:
            continue
        if status != "OK":
            continue
        uids = data[0].split() if data and data[0] else []
        if not uids:
            continue
        uid = uids[-1]
        _, d = mail.fetch(uid, "(RFC822)")
        if not d or not d[0]:
            continue
        raw = d[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            continue
        try:
            return _to_email_msg(raw, all_mail_folder, uid.decode())
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Filtering + pairing
# ---------------------------------------------------------------------------

def is_excluded(domain: str) -> bool:
    return domain in EXCLUDED_DOMAINS


def pair_threads(
    mail: imaplib.IMAP4_SSL,
    sent_msgs: List[EmailMsg],
    max_pairs: int = 200,
) -> List[Pair]:
    """For each sent message, find its inbound parent + filter to recruiter threads.

    Two-phase filtering to avoid hammering IMAP:
      1. Header-only pre-filter (no extra IMAP calls): must have In-Reply-To/
         References, recipient domain not excluded, not a reply-to-self.
      2. Sort candidates newest-first and cap to max_pairs BEFORE doing the
         expensive per-message All-Mail parent lookup.
    """
    all_mail = _find_folder(mail, "All Mail") or "[Gmail]/All Mail"
    logger.info("All-Mail folder: %s", all_mail)

    # ── Phase 1: cheap filter on sent-message headers only ─────────────────
    user_local = IMAP_USER.split("@")[0].lower() if IMAP_USER else ""
    candidates: List[Tuple[EmailMsg, List[str]]] = []
    for s in sent_msgs:
        candidate_ids = ([s.in_reply_to] if s.in_reply_to else []) + s.references
        if not candidate_ids or not s.to_email:
            continue
        if is_excluded(s.to_domain):
            continue
        if user_local and user_local in s.to_email.lower():
            continue
        candidates.append((s, candidate_ids))

    logger.info("Pre-filter: %d → %d candidates (have In-Reply-To + recipient passes filter)",
                len(sent_msgs), len(candidates))

    # Cap pre-lookup: keep the most recent N so we don't spend IMAP calls on
    # older threads that will get trimmed by --max-pairs later anyway.
    candidates.sort(key=lambda c: c[0].dt or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True)
    if len(candidates) > max_pairs:
        logger.info("Capping candidates %d → %d (most recent) before parent lookup",
                    len(candidates), max_pairs)
        candidates = candidates[:max_pairs]

    # ── Phase 2: parent lookup against All Mail ────────────────────────────
    mail.select(f'"{all_mail}"', readonly=True)
    pairs: List[Pair] = []
    next_idx = 1
    total = len(candidates)
    t0 = time.time()
    for i, (s, candidate_ids) in enumerate(candidates, start=1):
        if i % 25 == 0 or i == total:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            logger.info("  parent lookup %d/%d (%.1f/s, %d paired so far)",
                        i, total, rate, len(pairs))

        parent = lookup_parent(mail, all_mail, candidate_ids)
        if not parent:
            continue
        if is_excluded(parent.from_domain):
            continue
        if IMAP_USER and IMAP_USER.lower() in parent.from_email.lower():
            continue

        pairs.append(Pair(idx=next_idx, recruiter=parent, reply=s))
        next_idx += 1

    logger.info("Paired %d recruiter reply thread(s) from %d candidates",
                len(pairs), total)
    return pairs


# ---------------------------------------------------------------------------
# Anonymization
# ---------------------------------------------------------------------------

def anonymize(pairs: List[Pair]) -> None:
    """Assign anonymized labels to recruiter identities based on domain."""
    by_domain: Dict[str, List[Pair]] = {}
    for p in pairs:
        d = p.recruiter.from_domain or "unknown"
        by_domain.setdefault(d, []).append(p)

    for d, group in by_domain.items():
        short = d.split(".")[0][:18]
        for i, p in enumerate(group, start=1):
            p.anon_label = f"recruiter #{p.idx} @ {short}"


def _anon_body(body: str) -> str:
    """Strip obvious PII from a body snippet before sending to Claude."""
    # Emails → <email>
    body = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<email>", body)
    # Phone-ish sequences → <phone>
    body = re.sub(r"(?<!\d)(\+?\d[\d\s().-]{7,}\d)(?!\d)", "<phone>", body)
    # URLs → preserve domain only
    body = re.sub(r"https?://([^/\s]+)/[^\s]*", r"https://\1/...", body)
    return body


# ---------------------------------------------------------------------------
# Claude pattern extraction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are analyzing a batch of anonymized recruiter ↔ candidate email exchanges
from Pinal Dave's sent folder. Your task is to extract common patterns in
Pinal's replies and propose additions to a reply-templates knowledge file
that a downstream LLM uses to draft future replies.

The candidate (Pinal) is a senior AI/Cloud architect. His profile is
authoritative — never suggest patterns that would contradict it.

For each pair you receive:
  - recruiter_message:  what the recruiter asked
  - candidate_reply:    how Pinal actually answered
  - pair_id:            integer for cross-reference

Extract:
  1. Intent clusters — group the pairs by the recruiter's underlying ask
     (e.g. salary, availability, visa, job details, scheduling, follow-up,
     technical fit, rejection, off-topic). Use existing intent names from
     the current reply_templates.md when possible.
  2. For each cluster, propose a suggested_template that captures Pinal's
     actual voice and content. Quote representative phrasing. If Pinal's
     replies are inconsistent, flag that rather than averaging.
  3. Tone rules (do / don't) that emerge across the whole batch.
  4. Observations about when Pinal accepts vs politely declines.

Keep the templates tight and action-ready. Don't invent policies Pinal
hasn't demonstrated.

Return ONLY a single JSON object, no markdown fences:

{
  "summary": "one paragraph — what the batch reveals about Pinal's replies",
  "patterns_by_intent": [
    {
      "intent": "SALARY_INQUIRY",
      "count": <int>,
      "example_pair_ids": [<int>, <int>, ...],
      "suggested_template": "proposed addition/refinement to reply_templates.md",
      "rationale": "why this template, what voice it captures"
    }
  ],
  "tone_rules": {
    "do": ["...", "..."],
    "dont": ["...", "..."]
  },
  "notes_for_profile": "optional — factual claims Pinal repeatedly makes that belong in applicant_profile.md rather than templates"
}
"""


def call_claude(pairs: List[Pair], model: str) -> Dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()
    payload = []
    for p in pairs:
        payload.append({
            "pair_id": p.idx,
            "recruiter_sender": p.anon_label,
            "recruiter_subject": p.recruiter.subject[:200],
            "recruiter_message": _anon_body(_strip_quoted(p.recruiter.body))[:3000],
            "candidate_reply": _anon_body(_strip_quoted(p.reply.body))[:3000],
        })

    logger.info("Sending %d pairs to Claude (%s) ...", len(payload), model)
    t0 = time.time()
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{"type": "text", "text": SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": f"Analyze these {len(payload)} anonymized pairs:\n\n"
                              + json.dumps(payload, ensure_ascii=False)}],
    )
    logger.info("Claude returned in %.1fs", time.time() - t0)

    usage = getattr(resp, "usage", None)
    if usage:
        logger.info(
            "Tokens — in:%d out:%d cache_r:%d cache_w:%d",
            getattr(usage, "input_tokens", 0),
            getattr(usage, "output_tokens", 0),
            getattr(usage, "cache_read_input_tokens", 0),
            getattr(usage, "cache_creation_input_tokens", 0),
        )

    text = resp.content[0].text if resp.content else ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            return json.loads(text[s:e + 1])
        raise


# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------

def write_knowledge_file(extracted: Dict[str, Any], out_path: Path) -> None:
    lines: List[str] = []
    lines.append("# Reply Templates — Learned from Sent Mail")
    lines.append("")
    lines.append("Auto-generated by `scripts/train_from_sent_mail.py` on "
                 + datetime.now().strftime("%Y-%m-%d") + ".")
    lines.append("")
    lines.append("Review, edit, and keep (or delete) the sections below as you "
                 "see fit. This file sits alongside `reply_templates.md` — the "
                 "knowledge loader concatenates every `*.md` in `knowledge/`.")
    lines.append("")
    summary = extracted.get("summary", "").strip()
    if summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(summary)
        lines.append("")

    patterns = extracted.get("patterns_by_intent", []) or []
    if patterns:
        lines.append("## Patterns by intent")
        lines.append("")
        for p in patterns:
            intent = p.get("intent", "OTHER")
            count = p.get("count", 0)
            lines.append(f"### {intent} ({count} example(s))")
            lines.append("")
            tpl = (p.get("suggested_template") or "").strip()
            if tpl:
                lines.append(tpl)
                lines.append("")
            rat = (p.get("rationale") or "").strip()
            if rat:
                lines.append(f"_Why:_ {rat}")
                lines.append("")

    tone = extracted.get("tone_rules") or {}
    if tone.get("do") or tone.get("dont"):
        lines.append("## Tone rules")
        lines.append("")
        for d in tone.get("do", []) or []:
            lines.append(f"- ✅ {d}")
        for d in tone.get("dont", []) or []:
            lines.append(f"- ❌ {d}")
        lines.append("")

    notes = (extracted.get("notes_for_profile") or "").strip()
    if notes:
        lines.append("## Notes for applicant_profile.md")
        lines.append("")
        lines.append(notes)
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s", out_path)


def write_report(extracted: Dict[str, Any], pairs: List[Pair], out_path: Path) -> None:
    by_id = {p.idx: p for p in pairs}
    lines: List[str] = []
    lines.append("# Sent-Mail Training Report")
    lines.append("")
    lines.append(f"Generated {datetime.now().isoformat(timespec='seconds')}.")
    lines.append(f"Total paired threads analyzed: **{len(pairs)}**")
    lines.append("")

    patterns = extracted.get("patterns_by_intent", []) or []
    if patterns:
        lines.append("## Per-intent evidence")
        lines.append("")
    for p in patterns:
        intent = p.get("intent", "OTHER")
        ids = p.get("example_pair_ids", []) or []
        lines.append(f"### {intent}")
        lines.append("")
        lines.append(f"_Suggested template:_ {(p.get('suggested_template') or '').strip()}")
        lines.append("")
        if ids:
            lines.append("**Example conversations (anonymized):**")
            lines.append("")
            for pid in ids:
                pair = by_id.get(pid)
                if not pair:
                    continue
                lines.append(f"#### Pair {pid} — {pair.anon_label}")
                lines.append("")
                lines.append(f"_Subject:_ {pair.recruiter.subject}")
                lines.append("")
                lines.append("**Recruiter asked:**")
                lines.append("")
                lines.append("```")
                lines.append(_anon_body(_strip_quoted(pair.recruiter.body))[:1000])
                lines.append("```")
                lines.append("")
                lines.append("**Pinal replied:**")
                lines.append("")
                lines.append("```")
                lines.append(_anon_body(_strip_quoted(pair.reply.body))[:1000])
                lines.append("```")
                lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s", out_path)


# ---------------------------------------------------------------------------
# Dry-run report (no Claude call)
# ---------------------------------------------------------------------------

def print_dry_run(pairs: List[Pair]) -> None:
    if not pairs:
        print("No pairs matched the filter.")
        return
    by_domain: Dict[str, int] = {}
    for p in pairs:
        d = p.recruiter.from_domain or "unknown"
        by_domain[d] = by_domain.get(d, 0) + 1

    print(f"\nDry run — {len(pairs)} recruiter reply pair(s) would be sent to Claude.\n")
    print("Top recruiter domains in the batch:")
    for d, n in sorted(by_domain.items(), key=lambda x: -x[1])[:15]:
        print(f"  {n:>3}  {d}")
    print("\nFirst 5 pairs:")
    for p in pairs[:5]:
        recruiter_snip = _anon_body(_strip_quoted(p.recruiter.body))[:160].replace("\n", " ")
        reply_snip = _anon_body(_strip_quoted(p.reply.body))[:160].replace("\n", " ")
        print(f"\n[{p.idx}] {p.anon_label}")
        print(f"    subject: {p.recruiter.subject[:120]}")
        print(f"    recruiter: {recruiter_snip}…")
        print(f"    reply:     {reply_snip}…")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Train reply templates from Sent folder")
    parser.add_argument("--days", type=int, default=120, help="Lookback window (default 120)")
    parser.add_argument("--max-pairs", type=int, default=200,
                        help="Cap pairs sent to Claude (default 200)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan + pair + filter, but do not call Claude")
    parser.add_argument("--model", default=CLAUDE_MODEL,
                        help=f"Claude model id (default {CLAUDE_MODEL})")
    parser.add_argument("--out-knowledge",
                        default=str(REPO_ROOT / "knowledge" / "reply_templates_learned.md"))
    parser.add_argument("--out-report",
                        default=str(REPO_ROOT / "scripts" / "train_report.md"))
    args = parser.parse_args()

    mail = _connect()
    try:
        sent = fetch_sent(mail, args.days)
        pairs = pair_threads(mail, sent, max_pairs=args.max_pairs)
    finally:
        try: mail.logout()
        except Exception: pass

    anonymize(pairs)

    if args.dry_run:
        print_dry_run(pairs)
        return 0

    if not pairs:
        logger.warning("No pairs to analyze; exiting.")
        return 0

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set; aborting")
        return 2

    extracted = call_claude(pairs, args.model)
    write_knowledge_file(extracted, Path(args.out_knowledge))
    write_report(extracted, pairs, Path(args.out_report))
    print("\nDone. Review:")
    print(f"  {args.out_knowledge}")
    print(f"  {args.out_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
