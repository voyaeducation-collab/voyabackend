from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
import asyncio, httpx, os, uuid, pathlib

API_KEY = os.getenv("VOYA_API_KEY", "")  # will be set on Render

app = FastAPI(title="Voya Chemistry Backend", version="0.1")

# --- helpers ---
def require_api_key(x_api_key: str | None):
    if not API_KEY:
        return  # allow all if no key set (dev mode)
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

async def download_pdf(pdf_url: str, dest_path: str):
    timeout = httpx.Timeout(60.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", pdf_url) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                async for chunk in r.aiter_bytes():
                    f.write(chunk)

async def process_ingestion(local_path: str):
    """
    STUB: Replace with real OCR + segmentation + DB write.
    """
    size = os.path.getsize(local_path)
    await asyncio.sleep(1.0)
    print(f"[INGEST] saved file: {local_path}, size={size} bytes")
    return {"status": "ok", "bytes": size}

# --- models ---
class IngestByUrl(BaseModel):
    pdf_url: HttpUrl
    source: str | None = None
    syllabus_hint: str | None = None

# --- endpoints ---
@app.post("/ingest")
async def ingest_endpoint(
    body: IngestByUrl | None = None,
    x_api_key: str | None = Header(default=None)
):
    require_api_key(x_api_key)

    if body and body.pdf_url:
        job_id = str(uuid.uuid4())
        temp_dir = pathlib.Path("/tmp/ingest")
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest = temp_dir / f"{job_id}.pdf"

        async def _job():
            try:
                await download_pdf(str(body.pdf_url), str(dest))
                await process_ingestion(str(dest))
                # os.remove(dest)  # optionally delete after processing
            except Exception as e:
                print(f"[INGEST ERROR] {e}")

        asyncio.create_task(_job())
        return JSONResponse({"status": "accepted", "job_id": job_id, "message": "download + ingestion started"})

    raise HTTPException(status_code=400, detail="Send JSON with {'pdf_url': 'https://...'}")

@app.post("/answer")
async def answer_endpoint(
    x_api_key: str | None = Header(default=None),
    type: str = Form(default=None),
    message: str = Form(default=None),
    student_id: str = Form(default=None),
    file: UploadFile = File(default=None),
):
    require_api_key(x_api_key)

    # Simple placeholder response to prove wiring works
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
    return {"template_answer": template, "confidence": 0.5, "fallback_candidates": []}
