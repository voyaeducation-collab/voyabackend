from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import JSONResponse
import os
import openai

app = FastAPI()

# Load environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VOYA_API_KEY = os.getenv("VOYA_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set")
if not VOYA_API_KEY:
    raise ValueError("VOYA_API_KEY is not set")

openai.api_key = OPENAI_API_KEY


@app.post("/answer")
async def answer(
    request: Request,
    message: str = Form(...),
    type: str = Form(...)
):
    # Auth check
    api_key = request.headers.get("x-api-key")
    if api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Call OpenAI API
        completion = openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful tutor that explains answers in markdown."},
                {"role": "user", "content": message}
            ]
        )

        ai_answer = completion.choices[0].message.content.strip()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    paper_meta = {
        "exam": "Unknown",
        "session": "Unknown",
        "variant": "Unknown",
        "question": "Unknown"
    }

    return JSONResponse({
        "received": {"type": type, "message": message, "has_file": False},
        "paper_meta": paper_meta,
        "template_answer": ai_answer
    })
