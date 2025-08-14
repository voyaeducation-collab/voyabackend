# app/main.py
import os
from fastapi import FastAPI, Form, Header, HTTPException

app = FastAPI()

# --------- simple demo data (add more rows later) ----------
PAST_PAPERS = [
    {
        "exam": "Cambridge IGCSE Chemistry (0620)",
        "session": "May/Jun, 2021",
        "paper_variant": "42/2",
        "question_number": "3(b)(ii)",
        "question_text": "explain ionic bonding",
        "keywords": ["ionic bond", "ionic bonding", "explain ionic"],
        "mark_scheme": (
            "Ionic bonds form by transfer of electrons from metal to non-metal; "
            "oppositely charged ions are produced and held by strong electrostatic attraction."
        ),
        "explanation": (
            "The MS wants the two parts: electron transfer AND attraction between ions. "
            "Use words like 'electrostatic attraction' and 'oppositely charged ions'."
        ),
        "final_answer": (
            "Electron(s) transfer from the metal to the non‑metal to form ions; "
            "ions are held by strong electrostatic attraction."
        ),
        "marks": 3,
        "pitfalls": "Saying 'share electrons' (that’s covalent) or forgetting to mention ions/attraction."
    },
    # add more items later
]

def find_match(user_q: str):
    q = user_q.lower().strip()
    for row in PAST_PAPERS:
        if any(k in q for k in row["keywords"]):
            return row
    return None

def fill_template(d: dict) -> str:
    if not d:
        return (
            "I couldn't find this question yet. "
            "Try rephrasing or add it to the dataset."
        )
    return f"""**Source**
Exam: {d['exam']}
Session: {d['session']}
Paper/Variant: {d['paper_variant']}
Question: {d['question_number']}

**Mark Scheme (verbatim key points)**
{d['mark_scheme']}

**Why this is the answer (tutor explanation)**
{d['explanation']}

**Final Answer**
{d['final_answer']}

**Check your work**
Marks available: {d['marks']}
Typical pitfalls: {d['pitfalls']}
"""

# --------- security helper ----------
def ensure_api_key(x_api_key: str | None):
    expected = os.getenv("VOYA_API_KEY")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

# --------- endpoints ----------
@app.get("/")
def read_root():
    return {"ok": True}

@app.post("/answer")
async def answer(
    type: str = Form("text"),
    message: str = Form(...),
    x_api_key: str | None = Header(None, convert_underscores=False),
):
    ensure_api_key(x_api_key)
    if type != "text":
        return {"template_answer": "Images not enabled in MVP. Send text only."}

    match = find_match(message)
    return {"template_answer": fill_template(match)}
