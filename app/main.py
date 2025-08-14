# app/main.py
from typing import Optional
import os
from fastapi import FastAPI, Form, Header, HTTPException
from fastapi.responses import JSONResponse
import httpx

# -------- Env --------
VOYA_API_KEY = os.getenv("VOYA_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")  # <-- per your request

if not VOYA_API_KEY:
    raise RuntimeError("VOYA_API_KEY is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

# -------- App --------
app = FastAPI(title="voya backend", version="1.0.0")

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}

# -------- Q&A --------
@app.post("/answer")
async def answer(
    type: str = Form(...),       # "text" for now
    message: str = Form(...),    # user's question
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    # auth
    if x_api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if type.lower() != "text":
        raise HTTPException(status_code=422, detail="Only type='text' is supported in MVP")

    # Structured instruction for the tutor answer
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
- {{clear, concise explanation aligned to the mark scheme}}

**Final Answer**
- {{one short, direct line}}

**Check your work**
- Marks available: {{number if known}}
- Typical pitfalls: {{common mistakes}}
""".strip()

    # Call OpenAI via raw HTTP (no SDK, no proxies)
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,          # gpt-5-mini
        "messages": [
            {"role": "system",
             "content": "You are a helpful exam tutor. Reply ONLY in the structured markdown template requested."},
            {"role": "user", "content": prompt},
        ],
        # NOTE: omit temperature/max_tokens to avoid model-specific errors
    }

    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions",
                                  headers=headers, json=body)
        if r.status_code != 200:
            # Return upstream detail so we can see model/account issues
            return JSONResponse(
                {"error": "openai_api_error", "status": r.status_code, "detail": r.json()},
                status_code=502,
            )
        data = r.json()
        gpt_answer = data["choices"][0]["message"]["content"].strip()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream model timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"server_error: {e}")

    paper_meta = {"exam": "Unknown", "session": "Unknown", "variant": "Unknown", "question": "Unknown"}

    return JSONResponse({
        "received": {"type": "text", "message": message, "has_file": False},
        "paper_meta": paper_meta,
        "template_answer": gpt_answer
    })
