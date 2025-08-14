from fastapi import FastAPI, Form, UploadFile, File, Header, HTTPException
from fastapi.responses import JSONResponse
import os

app = FastAPI()

# health / docs sanity
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}

# --- MVP /ingest (kept here if you still use it) ---
from pydantic import BaseModel

class IngestPayload(BaseModel):
    pdf_url: str
    source: str

@app.post("/ingest")
async def ingest(payload: IngestPayload, x_api_key: str | None = Header(default=None, alias="x-api-key")):
    # simple key check
    expect = os.environ.get("VOYA_API_KEY", "")
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # fake-accept (you can keep your real ingest here)
    return {"status": "accepted", "job_id": "demo", "message": "download + ingestion started"}

# --- NEW: MVP /answer ---
@app.post("/answer")
async def answer(
    # form fields coming from n8n Webhook
    type: str = Form(...),                 # "text" | "image" (for now we’ll handle "text")
    message: str = Form(...),              # the student’s question
    file: UploadFile | None = File(None),  # optional, for later image mode
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    # API key check
    expect = os.environ.get("VOYA_API_KEY", "")
    if not expect or x_api_key != expect:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # --- MVP logic (text only) ---
    # Here you’d call your retrieval/search. For now, return a realistic-shaped payload.
    if type.lower() == "text":
        # TODO: replace this block with your real search over ingested data
        template_answer = (
            "**Source**\n"
            "Exam: Cambridge IGCSE Chemistry (0620)\n"
            "Session: May/Jun, 2021\n"
            "Paper/Variant: 42\n"
            "Question: 3(b)(ii)\n\n"
            "**Mark Scheme (verbatim key points)**\n"
            "• ionic bond is electrostatic attraction between oppositely charged ions\n"
            "• formed by electron transfer from metal to non‑metal\n\n"
            "**Why this is the answer (tutor explanation)**\n"
            "When sodium reacts with chlorine, Na loses an electron (Na⁺) and Cl gains it (Cl⁻), "
            "so the attraction between Na⁺ and Cl⁻ is the ionic bond.\n\n"
            "**Final Answer**\n"
            "Ionic bonding is the electrostatic attraction between positive and negative ions formed by electron transfer.\n\n"
            "**Check your work**\n"
            "Marks available: 3\n"
            "Typical pitfalls: saying 'sharing' (that’s covalent), not mentioning electrostatic attraction."
        )
        return JSONResponse({"received": {"type": "text", "message": message, "has_file": False},
                             "template_answer": template_answer})

    # image branch (placeholder until you wire OCR)
    if file is not None:
        return JSONResponse({"received": {"type": "image", "message": message, "has_file": True},
                             "template_answer": "(image mode placeholder — wire OCR next)"})

    # fallback
    raise HTTPException(status_code=422, detail="Bad form data: need type + message (and optional file).")
# --- Student Q&A endpoint (text MVP) ---

from pydantic import BaseModel  # (you likely already imported this above)
import os
from fastapi import Form, Header, HTTPException
from fastapi.responses import JSONResponse

VOYA_API_KEY = os.getenv("VOYA_API_KEY", "")

@app.post("/answer")
async def answer(
    type: str = Form(...),         # "text" for now
    message: str = Form(...),      # student's question text
    x_api_key: str | None = Header(None, alias="x-api-key"),
):
    # auth
    if not x_api_key or x_api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # TODO: replace this stub with your real search/index logic.
    # For now, return a formatted template so n8n can display it.
    template = (
        "**Source**\n"
        "Exam: Cambridge IGCSE Chemistry (0620)\n"
        "Session: (detected later)\n"
        "Paper/Variant: (detected later)\n"
        "Question: (detected later)\n\n"
        "**Mark Scheme (verbatim key points)**\n(placeholder)\n\n"
        "**Why this is the answer (tutor explanation)**\n(placeholder)\n\n"
        "**Final Answer**\n(placeholder)\n\n"
        "**Check your work**\n- Marks available: (detected later)\n- Typical pitfalls: (placeholder)"
    )

    return JSONResponse(
        {
            "status": "ok",
            "input_type": type,
            "question": message,
            "template_answer": template,
        }
    )

