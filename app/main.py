# app/main.py
from typing import Optional
import os
import json

from fastapi import FastAPI, Form, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
import httpx

# ------------- Config (from environment) -------------
VOYA_API_KEY = os.environ.get("VOYA_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")  # switched to available model

# ------------- FastAPI app -------------
app = FastAPI(title="voya backend", version="1.0.0")

# Health/docs sanity
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}

# (optional) simple ingest stub you already had
from pydantic import BaseModel
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

# ------------- main: student Q&A (OpenAI via httpx) -------------
@app.post("/answer")
async def answer(
    type: str = Form(...),         # "text" | "image"
    message: str = Form(...),      # student's question
    file: UploadFile | None = File(None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    # API key check
    expect = VOYA_API_KEY
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if file is not None and type.lower() == "image":
        return JSONResponse(
            {
                "received": {"type": "image", "message": message, "has_file": True},
                "template_answer": "(image mode placeholder — wire OCR next)",
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
            detail="Server missing OPENAI_API_KEY. Set it in Render -> Environment.",
        )

    # Prompt for the model
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

    # Call OpenAI API
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,
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
        "temperature": 0.2,
        "max_completion_tokens": 600,  # ✅ new parameter
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
                {
                    "error": "openai_api_error",
                    "status": r.status_code,
                    "detail": err,
                },
                status_code=502,
            )
        data = r.json()
        gpt_answer = data["choices"][0]["message"]["content"]

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream model timeout")
    except Exception as e:
        return JSONResponse(
            {"error": "server_error", "detail": str(e)}, status_code=500
        )

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
