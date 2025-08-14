# app/main.py

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, Form, File, UploadFile, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------- env & clients ----------
VOYA_API_KEY = os.environ.get("VOYA_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-turbo")

# OpenAI official SDK (no proxies arg)
try:
    from openai import OpenAI  # pip install openai==1.40.0
    oai_client = OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    # If the SDK isn't installed yet, raise a helpful message
    raise RuntimeError(
        "OpenAI SDK failed to import. Make sure requirements.txt includes "
        "openai==1.40.0 and redeploy. Underlying error: %r" % (e,)
    )

# ---------- FastAPI app ----------
app = FastAPI(title="voya backend", version="1.0.0")


# health/docs sanity
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}


# ---- (optional) simple ingest you already had ----
class IngestPayload(BaseModel):
    pdf_url: str
    source: str


@app.post("/ingest")
async def ingest(payload: IngestPayload, x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    # simple key check
    expect = VOYA_API_KEY
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # fake-accept (keep your real ingest here later)
    return {"status": "accepted", "job_id": "demo", "message": "download + ingestion started"}


# ---------- main: student Q&A ----------
@app.post("/answer")
async def answer(
    # form fields coming from n8n Webhook
    type: str = Form(...),            # "text" | "image" (we'll handle "text" for MVP)
    message: str = Form(...),         # the student's question
    file: UploadFile | None = File(None),  # optional, for later image mode
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    # API key check (Render env: VOYA_API_KEY)
    expect = VOYA_API_KEY
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # If an image is sent, just acknowledge for now (MVP focuses on text)
    if file is not None and type.lower() == "image":
        return JSONResponse(
            {
                "received": {"type": "image", "message": message, "has_file": True},
                "template_answer": "(image mode placeholder — wire OCR next)",
            }
        )

    # --- Text mode (MVP) ---
    if type.lower() != "text":
        raise HTTPException(status_code=422, detail="Bad form data: need type='text' + message (and optional file).")

    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server missing OPENAI_API_KEY. Set it in Render → Environment.")

    # Build a structured instruction so the model returns the template you want
    prompt = f"""
You are an AI tutor. A student asks: {message}

Respond ONLY in structured markdown with these sections:

**Source**
Exam: {{exam (or Unknown)}}
Session: {{month/season, year (or Unknown)}}
Paper/Variant: {{paper/variant (or Unknown)}}
Question: {{question number (or Unknown)}}

**Mark Scheme (verbatim key points)**
- {{bullet}}
- {{bullet}}

**Why this is the answer (tutor explanation)**
Explain clearly and concisely based on the syllabus.

**Final Answer**
One short, direct final line.

**Check your work**
- Marks available: {{number if known}}
- Typical pitfalls: {{common mistakes}}
""".strip()

    try:
        comp = oai_client.chat.completions.create(
            model=OPENAI_MODEL,  # e.g., "gpt-5-turbo"
            messages=[
                {"role": "system", "content": "You are a helpful exam tutor. Use the requested sections and no extras."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        gpt_answer = comp.choices[0].message.content
    except Exception as e:
        # Surface a clean error back to the caller and to logs
        raise HTTPException(status_code=500, detail=f"OpenAI call failed: {e}")

    return JSONResponse(
        {
            "received": {"type": "text", "message": message},
            "paper_meta": {
                "exam": "Unknown",
                "session": "Unknown",
                "variant": "Unknown",
                "question": "Unknown",
            },
            "template_answer": gpt_answer,
        }
    )
