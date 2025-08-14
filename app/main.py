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

# --- in app/main.py ---

import os
import re
from typing import Optional

from fastapi import FastAPI, Form, File, UploadFile, Header, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

# ----- helpers -----

VOYA_API_KEY = os.getenv("VOYA_API_KEY", "")

def require_api_key(x_api_key: Optional[str]):
    if not x_api_key or x_api_key != VOYA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# naive parser: pulls out paper code, session, year, variant, question like "3(b)(ii)"
PAPER_RE = re.compile(
    r"""
    (?P<board>(?:Cambridge|CAIE|IGCSE|GCSE|AQA|Edexcel))?   # optional board
    .*?
    (?P<code>\b\d{4}\b|\b\d{3,4}\b|\b0620\b)?               # e.g. 0620
    .*?
    (?P<session>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)?
    \s*[,/ ]*\s*
    (?P<year>20\d{2})?                                      # year
    .*?
    (?:Variant[:/ ]*(?P<variant>\d)|\b(?P<variant2>\d)\b)?  # variant
    .*?
    (?:Question[: ]*(?P<qnum>\d+(?:\([a-z]\))?(?:\([ivx]+\))?)|
       \bQ(?P<qnum2>\d+(?:\([a-z]\))?(?:\([ivx]+\))?))?     # e.g. 3(b)(ii)
    """,
    re.IGNORECASE | re.VERBOSE,
)

def parse_question(text: str):
    m = PAPER_RE.search(text or "")
    board = (m.group("board") or "").title() if m else ""
    code = (m.group("code") or "").strip() if m else ""
    session = (m.group("session") or "").title() if m else ""
    year = (m.group("year") or "").strip() if m else ""
    variant = (m.group("variant") or m.group("variant2") or "").strip() if m else ""
    q = (m.group("qnum") or m.group("qnum2") or "").strip() if m else ""

    # Normalize common Cambridge IGCSE Chemistry defaults if missing
    if not board and "0620" in text:
        board = "Cambridge"
    if not code and "0620" in text:
        code = "0620"

    # Build a friendly fallback if something is missing
    return {
        "exam": f"{board} IGCSE Chemistry ({code})".strip(),
        "session": session or "Unknown",
        "year": year or "Unknown",
        "variant": variant or "Unknown",
        "question": q or "Unknown",
    }

def make_template(parsed, message, has_file: bool):
    # This is your MVP “filled” template; replace any chunks later as you wire real data
    return (
        f"**Source**\n"
        f"Exam: {parsed['exam']}\n"
        f"Session: {parsed['session']}, {parsed['year']}\n"
        f"Paper/Variant: {parsed['variant']}\n"
        f"Question: {parsed['question']}\n\n"
        f"**Mark Scheme (verbatim key points)**\n"
        f"(placeholder — wire to your index)\n\n"
        f"**Why this is the answer (tutor explanation)**\n"
        f"(placeholder — reasoning based on syllabus)\n\n"
        f"**Final Answer**\n"
        f"(placeholder — concise)\n\n"
        f"**Check your work**\n"
        f"- Marks available: (placeholder)\n"
        f"- Typical pitfalls: (placeholder)\n\n"
        f"**Request**\n"
        f"type={ 'image' if has_file else 'text' }, message={message[:200]}{'...' if len(message)>200 else ''}"
    )

# ----- routes -----

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}

# keep your existing /ingest if you still use it...

@app.post("/answer")
async def answer(
    type: str = Form(...),                 # "text" or "image"
    message: str = Form(...),              # student prompt
    file: Optional[UploadFile] = File(None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
):
    require_api_key(x_api_key)

    # MVP: if image is sent, we just note it; (you can OCR later)
    has_file = file is not None

    # Parse meta from the student's text
    parsed = parse_question(message or "")

    # Build response
    template = make_template(parsed, message, has_file)

    return JSONResponse(
        {
            "received": {
                "type": type,
                "has_file": bool(has_file),
                "message": message,
            },
            "paper_meta": parsed,
            "template_answer": template,
        }
    )
