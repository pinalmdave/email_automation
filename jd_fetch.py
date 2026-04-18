"""
Job-description fetcher — pulls a job posting URL and extracts plain text.

Deliberately simple: `requests.get` with a browser-ish user agent, then
`BeautifulSoup` to strip HTML. Works for public postings from most boards
(Indeed, Dice, Monster, ZipRecruiter, direct company careers pages).
Sites with aggressive bot-blocking or JS-rendered content may return
stubs — when that happens we still create an apply plan but flag it so
the user can paste the JD manually.
"""

import logging
import re
from typing import Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def _detect_source(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().lstrip("www.")
    if "indeed" in host:          return "Indeed"
    if "dice" in host:            return "Dice"
    if "monster" in host:         return "Monster"
    if "ziprecruiter" in host:    return "ZipRecruiter"
    if "linkedin" in host:        return "LinkedIn"
    if "lever.co" in host:        return "Lever"
    if "greenhouse.io" in host:   return "Greenhouse"
    if "workday" in host:         return "Workday"
    if "smartrecruiters" in host: return "SmartRecruiters"
    if "ashbyhq" in host:         return "Ashby"
    return host or "Unknown"


def _clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def _guess_title_company(html: str) -> Dict[str, str]:
    """Best-effort extraction of role title + company from meta tags or H1."""
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    company = ""

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site and og_site.get("content"):
        company = og_site["content"].strip()

    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)[:180]

    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(" ", strip=True)

    # Some boards encode "Role @ Company" in the title.
    if not company and " at " in title.lower():
        parts = re.split(r"\s+at\s+", title, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            title, company = parts[0].strip(), parts[1].strip()

    return {"job_title": title[:200], "company_name": company[:140]}


def fetch_job_posting(url: str, timeout: int = 20) -> Dict[str, str]:
    """
    Fetch a job posting URL and return
        {source, job_title, company_name, jd_text, error}

    jd_text is the cleaned page text (trimmed to ~20 KB). error is set if
    the fetch failed for any reason — the caller can still create an
    apply plan and ask the user to paste the JD manually.
    """
    result = {
        "source":       _detect_source(url),
        "job_title":    "",
        "company_name": "",
        "jd_text":      "",
        "error":        "",
    }
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        result["error"] = f"fetch failed: {exc}"
        return result

    if resp.status_code != 200:
        result["error"] = f"HTTP {resp.status_code}"
        return result

    html = resp.text
    result.update(_guess_title_company(html))
    text = _clean_html(html)
    # Trim overly long pages so the LLM prompt stays sane.
    if len(text) > 20000:
        text = text[:20000]
    result["jd_text"] = text

    if len(text) < 300:
        result["error"] = "page contained very little text — site may block bots or require JavaScript"
    return result
