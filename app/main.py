# app/main.py

from fastapi import FastAPI, Form, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os

# ---------- FastAPI app ----------
app = FastAPI()


# ---------- Sanity/health ----------
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}


# ---------- Simple ingest (stub you already had) ----------
class IngestPayload(BaseModel):
    pdf_url: str
    source: str

@app.post("/ingest")
async def ingest(payload: IngestPayload, x_api_key: str | None = Header(default=None, alias="x-api-key")):
    expect = os.environ.get("VOYA_API_KEY", "")
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # TODO: your real ingestion/indexing job
    return {"status": "accepted", "job_id": "demo", "message": "download + ingestion started"}


# ---------- Answer (GPT-powered) ----------
@app.post("/answer")
async def answer(
    # form fields coming from n8n Webhook
    type: str = Form(...),            # "text" | "image"  (we’ll handle "text" now)
    message: str = Form(...),         # student question
    file: UploadFile | None = File(None),  # optional: future image mode
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    # API key check (Render env: VOYA_API_KEY)
    expect = os.environ.get("VOYA_API_KEY", "")
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # If an image is sent, just acknowledge for now (MVP focuses on text)
    if file is not None and type.lower() == "image":
        return JSONResponse({
            "received": {"type": "image", "message": message, "has_file": True},
            "template_answer": "(image mode placeholder — wire OCR next)"
        })

    # ---- Text mode (MVP) ----
    # Build a structured instruction so the model returns the template you want
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-5-turbo")
    from openai import OpenAI  # official SDK
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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

**Final Answer**
- {{1–2 line final answer}}

**Check your work**
- Marks available: {{n}}
- Typical pitfalls: {{brief pitfalls}}
""".strip()

    # Call the Responses API (preferred)
    # Doc: https://platform.openai.com/docs/overview?lang=python
    resp = client.responses.create(
        model=openai_model,
        input=[
            {"role": "system", "content": "You are a helpful exam tutor. Be accurate and concise."},
            {"role": "user", "content": prompt},
        ],
    )

    # Best-effort text extraction
    answer_text = getattr(resp, "output_text", None) or str(resp)

    return JSONResponse({
        "received": {"type": "text", "message": message, "has_file": False},
        "template_answer": answer_text,
    })


# ---------- Local dev helper ----------
if __name__ == "__main__":
    # Local test:  uvicorn app.main:app --reload
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
