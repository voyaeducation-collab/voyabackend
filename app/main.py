# app/main.py
from __future__ import annotations

import os
import re
from typing import Optional, Dict

from fastapi import FastAPI, Form, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx


# ----------------- Config (from environment) -----------------
VOYA_API_KEY: str = os.environ.get("VOYA_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-5-mini")  # default to gpt-5-mini


# ----------------- FastAPI app -----------------
app = FastAPI(title="voya backend", version="1.1.0")


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
    # strong first
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
    # Paper and optional Variant: e.g., "Paper 42", "Paper 2 Variant 2", "P42", "P2"
    (r"\bPaper\s*(\d{1,2})\s*Variant\s*(\d{1,2})\b", "both"),
    (r"\bPaper\s*(\d{1,2})\b", "paper"),
    (r"\bVariant\s*(\d{1,2})\b", "variant"),
    (r"\bP(?:aper)?\s*(\d{1,2})\b", "paper"),
]

SESSION_PATTERNS = [
    # "May/Jun 2021", "May 2021", "Nov 23"
    (rf"\b{MONTHS}\s*/\s*{MONTHS}\s*{YEAR}\b", "two_months_year"),
    (rf"\b{MONTHS}\s*{YEAR}\b", "month_year"),
    (rf"\b{YEAR}\b", "year_only"),
]


def _norm_year(y: str) -> str:
    """Normalize 2-digit years to 20xx (best-effort)."""
    if len(y) == 2:
        # Simple guess: 20xx for 00–49, otherwise 19xx. (You can tweak.)
        n = int(y)
        return f"20{y}" if n <= 49 else f"19{y}"
    return y


def extract_paper_meta(message: str) -> Dict[str, str]:
    text = message or ""
    exam = "Unknown"
    session = "Unknown"
    paper = "Unknown"
    variant = "Unknown"

    # 1) Exam hints
    for label, pattern in EXAM_HINTS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            exam = label
            break

    # 2) Session (month(s) + year)
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

    # 3) Paper / Variant
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
            # keep searching for variant too (don’t break)
        if kind == "variant":
            variant = m.group(1)
            # don't break; maybe we already found paper elsewhere

    # 4) If paper like "42" and variant still Unknown, try to split into 4 + 2
    if variant == "Unknown" and re.fullmatch(r"\d{2}", paper or ""):
        paper, variant = paper[0], paper[1]

    return {
        "exam": exam,
        "session": session,
        "paper": paper,
        "variant": variant,
    }


# ----------------- main: student Q&A (OpenAI via httpx) -----------------
@app.post("/answer")
async def answer(
    type: str = Form(...),  # "text" | "image" (we handle "text" now)
    message: str = Form(...),  # the student's question
    file: UploadFile | None = File(None),  # optional (future: image mode)
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

    # Build a structured instruction so the model returns the template you want
    prompt = f"""
You are an AI exam tutor. A student asks: {message}

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
""".strip()

    # Call OpenAI via raw HTTP
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,          # default 'gpt-5-mini' unless overridden
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful exam tutor. Reply ONLY in the exact structured "
                    "markdown template requested by the user."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        # Do NOT send temperature — some accounts/models reject non-default values.
        # "max_tokens" is also rejected by some accounts; omit to use model defaults.
    }

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=body,
            )
        if r.status_code != 200:
            # try to bubble helpful detail (without secrets)
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

    return JSONResponse(
        {
            "received": {"type": "text", "message": message, "has_file": False},
            "paper_meta": paper_meta,
            "template_answer": gpt_answer,
        }
    )
