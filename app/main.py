import os
from typing import Optional
from fastapi import FastAPI, Form, File, UploadFile, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI

# --- App instance ---
app = FastAPI()

# --- API Keys ---
VOYA_API_KEY = os.getenv("VOYA_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-turbo")


# Example ingest endpoint (if you have it already)
class IngestPayload(BaseModel):
    data: dict


@app.post("/ingest")
async def ingest(payload: IngestPayload, x_api_key: Optional[str] = Header(default=None, alias="x-api-key")):
    # Simple auth check
    if x_api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"status": "ok", "received": payload.dict()}


# --- GPT-5 Answer Endpoint ---
@app.post("/answer")
async def answer(
    type: str = Form(...),
    message: str = Form(...),
    file: UploadFile | None = File(None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    # API key check
    if x_api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # If image file uploaded (future handling)
    if file is not None and type.lower() == "image":
        return JSONResponse({
            "received": {"type": "image", "message": message, "has_file": True},
            "template_answer": "(image mode placeholder — OCR to be added)"
        })

    # Text mode — Call GPT-5
    if type.lower() == "text":
        client = OpenAI(api_key=OPENAI_API_KEY)

        prompt = f"""
        You are an AI tutor. The student asks: {message}.
        Respond in structured markdown with:
        **Source** (exam info if available)
        **Mark Scheme** (verbatim key points)
        **Why this is the answer** (explanation)
        """

        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful exam tutor."},
                {"role": "user", "content": prompt},
            ],
        )

        gpt_answer = completion.choices[0].message.content

        return JSONResponse({
            "received": {"type": "text", "message": message},
            "template_answer": gpt_answer
        })

    # If type is neither text nor image
    raise HTTPException(status_code=422, detail="Bad form data: need type + message (and optional file).")
