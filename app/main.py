# app/main.py

from typing import Optional
import os

from fastapi import FastAPI, Form, File, UploadFile, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# -------- env & config --------
VOYA_API_KEY: str = os.environ.get("VOYA_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-5-turbo")

app = FastAPI(title="voya backend", version="1.0.0")


# -------- health/docs --------
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}


# -------- optional: simple ingest stub you had before --------
class IngestPayload(BaseModel):
    pdf_url: str
    source: str


@app.post("/ingest")
async def ingest(
    payload: IngestPayload,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    # simple key check
    expect = VOYA_API_KEY
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # TODO: your real ingestion/index job here
    return {"status": "accepted", "job_id": "demo", "message": "download + ingestion started"}


# -------- main: student Q&A (GPT-powered) --------
@app.post("/answer")
async def answer(
    # form fields coming from n8n Webhook
    type: str = Form(...),            # "text" | "image" (we'll handle "text" now)
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

    # Text mode (MVP)
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
- {{bullet key point 1}}
- {{bullet key point 2}}
- {{bullet key point 3}}

**Why this is the answer (tutor explanation)**
- {{clear, concise explanation aligned to mark scheme}}
- Explain clearly and concisely based on the syllabus.

**Final Answer**
- One short, direct final line.

**Check your work**
- Marks available: {{number if known}}
- Typical pitfalls: {{common mistakes}}
""".strip()

    # --- Call OpenAI (official SDK, no proxies) ---
    try:
        from openai import OpenAI  # requires openai==1.40.0
    except Exception as e:
        # Helpful import error for missing dependency
        raise RuntimeError(
            "OpenAI SDK failed to import. Ensure requirements.txt includes "
            "'openai==1.40.0' and redeploy. Underlying error: %r" % (e,)
        )

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Prefer chat.completions for broad compatibility
    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful exam tutor. Be accurate and concise."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        gpt_answer = completion.choices[0].message.content
    except Exception as e:
        # Bubble up model/auth errors clearly
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e!r}")

    # Optional: lightweight metadata placeholder (fills your n8n UI nicely)
    paper_meta = {
        "exam": "Unknown",
        "session": "Unknown",
        "variant": "Unknown",
        "question": "Unknown",
    }

    return JSONResponse(
        {
            "received": {"type": "text", "message": message, "has_file": False},
            "paper_meta": paper_meta,
            "template_answer": gpt_answer,
        }
    )

# (No __main__ block for Render; Uvicorn is run by the platform)
