from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
import os, uuid, pathlib, asyncio, httpx

app = FastAPI()

# ---- API key (set in Render Environment as VOYA_API_KEY) ----
API_KEY = os.getenv("VOYA_API_KEY", "")

def require_api_key(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ---- Model for JSON body ----
class IngestByUrl(BaseModel):
    pdf_url: HttpUrl
    source: str | None = None

# ---- Helpers ----
async def download_pdf(pdf_url: str, dest_path: str):
    timeout = httpx.Timeout(60.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", pdf_url) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                async for chunk in r.aiter_bytes():
                    f.write(chunk)

async def process_ingestion(local_path: str):
    # Stub: replace with OCR + segmentation later
    await asyncio.sleep(1.0)
    size = os.path.getsize(local_path)
    print(f"[INGEST] saved file: {local_path}, bytes={size}")
    return {"status": "ok", "bytes": size}

# ---- Routes ----
@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI on Render!"}

@app.post("/ingest")
async def ingest(body: IngestByUrl, x_api_key: str | None = Header(default=None)):
    require_api_key(x_api_key)

    job_id = str(uuid.uuid4())
    temp_dir = pathlib.Path("/tmp/ingest")
    temp_dir.mkdir(parents=True, exist_ok=True)
    dest = temp_dir / f"{job_id}.pdf"

    async def _job():
        try:
            await download_pdf(str(body.pdf_url), str(dest))
            await process_ingestion(str(dest))
            # os.remove(dest)  # optional
        except Exception as e:
            print(f"[INGEST ERROR] {e}")

    asyncio.create_task(_job())
    return JSONResponse({"status": "accepted", "job_id": job_id, "message": "download + ingestion started"})

from fastapi import UploadFile, File, Form

@app.post("/answer")
async def answer(
    x_api_key: str | None = Header(default=None),
    type: str = Form(...),                    # "text" or "image"
    message: str = Form(""),                  # the student's question (for text); optional with image
    student_id: str = Form(default=""),
    file: UploadFile = File(default=None),    # image if provided
):
    require_api_key(x_api_key)

    # --- TODO: replace with real retrieval over your ingested data ---
    # For now, return a fixed, correctly formatted template so wiring works.
    template = (
        "1) **Source**\n"
        "- Exam: Cambridge IGCSE Chemistry (0620)\n"
        "- Session: May/Jun, 2021\n"
        "- Paper/Variant: 42/2\n"
        "- Question: 3(b)(ii)\n\n"
        "2) **Mark Scheme (verbatim key points)**\n"
        "- (placeholder)\n\n"
        "3) **Why this is the answer (tutor explanation)**\n"
        "- (placeholder)\n\n"
        "4) **Final Answer**\n"
        "- (placeholder)\n\n"
        "5) **Check your work**\n"
        "- Marks available: 3\n"
        "- Typical pitfalls: (placeholder)\n"
    )
    return {"template_answer": template, "received": {"type": type, "has_file": bool(file), "message": message}}

