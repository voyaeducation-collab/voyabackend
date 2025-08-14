# app/main.py
from __future__ import annotations

import os
import re
from typing import Optional, Dict, List, Tuple

from fastapi import FastAPI, Form, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

# Optional deps for local PDF search (safe if not present at runtime)
try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None  # graceful fallback

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover
    fuzz = None  # graceful fallback


# ----------------- Config (from environment) -----------------
VOYA_API_KEY: str = os.environ.get("VOYA_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-5-mini")  # keep default


# ----------------- FastAPI app -----------------
app = FastAPI(title="voya backend", version="1.2.0")


# ----------------- Health/docs sanity -----------------
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}


# ----------------- (optional) ingest stub you already had -----------------
class IngestPayload(BaseModel):
    pdf_url: str
    source: str


@app.post("/ingest")
async def ingest(
    payload: IngestPayload,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    # simple key check
    if not VOYA_API_KEY or x_api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # fake-accept (keep your real ingest here later)
    return {"status": "accepted", "job_id": "demo", "message": "download + ingestion started"}


# ----------------- Utilities: light meta extraction from message -----------------
MONTHS = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
YEAR = r"(20\d{2}|19\d{2}|\d{2})"  # allow 2-digit too (e.g., '21')

EXAM_HINTS = [
    ("Cambridge IGCSE", r"\b(Cambridge\s+IGCSE|CIE\s+IGCSE)\b"),
    ("IGCSE", r"\bIGCSE\b"),
    ("GCSE", r"\bGCSE\b"),
    ("AQA", r"\bAQA\b"),
    ("Edexcel", r"\bEdexcel\b"),
    ("IB", r"\bInternational\s+Baccalaureate\b|\bIB\b"),
    ("Cambridge", r"\bCIE\b|\bCambridge\b"),
    ("SAT", r"\bSAT\b"),
    ("ACT", r"\bACT\b"),
]

PAPER_PATTERNS = [
    (r"\bPaper\s*(\d{1,2})\s*Variant\s*(\d{1,2})\b", "both"),
    (r"\bPaper\s*(\d{1,2})\b", "paper"),
    (r"\bVariant\s*(\d{1,2})\b", "variant"),
    (r"\bP(?:aper)?\s*(\d{1,2})\b", "paper"),
]

SESSION_PATTERNS = [
    (rf"\b{MONTHS}\s*/\s*{MONTHS}\s*{YEAR}\b", "two_months_year"),
    (rf"\b{MONTHS}\s*{YEAR}\b", "month_year"),
    (rf"\b{YEAR}\b", "year_only"),
]


def _norm_year(y: str) -> str:
    if len(y) == 2:
        n = int(y)
        return f"20{y}" if n <= 49 else f"19{y}"
    return y


def extract_paper_meta(message: str) -> Dict[str, str]:
    text = message or ""
    exam = "Unknown"
    session = "Unknown"
    paper = "Unknown"
    variant = "Unknown"

    for label, pattern in EXAM_HINTS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            exam = label
            break

    for pattern, kind in SESSION_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        if kind == "two_months_year":
            m1, m2, y = m.group(1), m.group(2), _norm_year(m.group(3))
            session = f"{m1}/{m2} {y}"
            break
        if kind == "month_year":
            m1, y = m.group(1), _norm_year(m.group(2))
            session = f"{m1} {y}"
            break
        if kind == "year_only":
            y = _norm_year(m.group(1))
            session = y
            break

    for patt, kind in PAPER_PATTERNS:
        m = re.search(patt, text, flags=re.IGNORECASE)
        if not m:
            continue
        if kind == "both":
            paper = m.group(1)
            variant = m.group(2)
            break
        if kind == "paper":
            paper = m.group(1)
        if kind == "variant":
            variant = m.group(1)

    if variant == "Unknown" and re.fullmatch(r"\d{2}", paper or ""):
        paper, variant = paper[0], paper[1]

    return {"exam": exam, "session": session, "paper": paper, "variant": variant}


# ----------------- Lightweight PDF index (optional) -----------------
class PageChunk(BaseModel):
    doc: str
    page: int
    text: str


PDF_INDEX: List[PageChunk] = []  # populated at startup


def _load_pdfs(paths: List[str]) -> None:
    """Populate PDF_INDEX with per-page text. Safe if PyPDF not present."""
    if PdfReader is None:
        return
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            reader = PdfReader(p)
            for i, page in enumerate(reader.pages):
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
                if t.strip():
                    PDF_INDEX.append(PageChunk(doc=os.path.basename(p), page=i + 1, text=t))
        except Exception:
            # keep going if a single file is bad
            continue


def _best_page_match(query: str) -> Tuple[Optional[PageChunk], int]:
    """Return best page and score using rapidfuzz.ratio. Safe fallback if RF not present."""
    if not PDF_INDEX or not query.strip() or fuzz is None:
        return (None, 0)
    best: Optional[PageChunk] = None
    best_score = -1
    q = query.strip()
    for chunk in PDF_INDEX:
        # simple similarity; fast and ok as a first cut
        s = fuzz.token_set_ratio(q, chunk.text)
        if s > best_score:
            best_score = s
            best = chunk
    return best, best_score


# Load your uploaded files if present (root folder)
_load_pdfs(["QB1.pdf", "QB2.pdf", "QB3.pdf", "QB4.pdf", "QB5.pdf"])


# ----------------- main: student Q&A -----------------
@app.post("/answer")
async def answer(
    type: str = Form(...),             # "text" | "image"
    message: str = Form(...),          # student question
    file: UploadFile | None = File(None),  # future image mode
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    # API key check
    if not VOYA_API_KEY or x_api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Image placeholder for now
    if file is not None and type.lower() == "image":
        return JSONResponse(
            {
                "received": {"type": "image", "message": message, "has_file": True},
                "template_answer": "(image mode placeholder — OCR to be added)",
            }
        )

    if type.lower() != "text":
        raise HTTPException(
            status_code=422,
            detail="Bad form data: need type='text' + message (and optional file).",
        )

    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server missing OPENAI_API_KEY. Set it in Render → Environment.",
        )

    # Auto-detect paper meta from user message
    paper_meta = extract_paper_meta(message)

    # Try to find a close match in your PDFs
    context_note = ""
    matched_doc = None
    matched_page = None
    matched_text = None

    best_chunk, score = _best_page_match(message)
    if best_chunk and score >= 60:  # threshold you can tweak
        matched_doc = best_chunk.doc
        matched_page = best_chunk.page
        # keep it short to avoid long prompts; send ~1.2k chars around best page
        snippet = best_chunk.text
        if len(snippet) > 1200:
            snippet = snippet[:1200]
        matched_text = snippet
        context_note = f"(Found similar question in {matched_doc}, page {matched_page}, score {score})"

    # Build a structured instruction so the model returns the template you want
    base_instructions = f"""
You are an AI exam tutor. A student asks: {message}

{"Context (from past papers):\n" + matched_text if matched_text else ""}

Respond ONLY in structured markdown with these sections:

**Source**
Exam: {paper_meta['exam']}
Session: {paper_meta['session']}
Paper/Variant: {paper_meta['paper']}/{paper_meta['variant']}
Question: {{question number (or Unknown)}}

**Mark Scheme (verbatim key points)**
- {{bullet key point 1}}
- {{bullet key point 2}}
- {{bullet key point 3}}
- {{bullet}}
- {{bullet}}

**Why this is the answer (tutor explanation)**
- Explain clearly and concisely based on the syllabus.

**Final Answer**
- One short, direct final line.

**Check your work**
- Marks available: {{number if known}}
- Typical pitfalls: {{common mistakes}}

If you used the provided Context, fill metadata consistently with it and stay faithful to the mark scheme language.
""".strip()

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,  # 'gpt-5-mini' by default
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful exam tutor. Reply ONLY in the exact structured "
                    "markdown template requested by the user."
                ),
            },
            {"role": "user", "content": base_instructions},
        ],
        # Do not set temperature/max tokens to avoid account/model param issues
    }

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=body,
            )
        if r.status_code != 200:
            try:
                err = r.json()
            except Exception:
                err = {"message": r.text}
            return JSONResponse(
                {"error": "openai_api_error", "status": r.status_code, "detail": err},
                status_code=502,
            )
        data = r.json()
        gpt_answer = data["choices"][0]["message"]["content"]

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream model timeout")
    except Exception as e:
        return JSONResponse({"error": "server_error", "detail": str(e)}, status_code=500)

    response = {
        "received": {"type": "text", "message": message, "has_file": False},
        "paper_meta": paper_meta,
        "template_answer": gpt_answer,
    }
    if matched_doc and matched_page:
        response["retrieval"] = {
            "note": context_note,
            "doc": matched_doc,
            "page": matched_page,
        }
    return JSONResponse(response)
