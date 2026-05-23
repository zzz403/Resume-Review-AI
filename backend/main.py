from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ai import review_resume
from db import save_review, fetch_history
from extractor import extract_text

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReviewRequest(BaseModel):
    resume_text: str

@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    content = await file.read()
    text = extract_text(file.filename or "", content)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")
    return {"text": text}

@app.post("/review")
def review(req: ReviewRequest):
    if not req.resume_text.strip():
        raise HTTPException(status_code=400, detail="resume_text is required")
    result = review_resume(req.resume_text)
    save_review(req.resume_text, result["score"], result["feedback"])
    return result

@app.get("/history")
def history():
    return fetch_history()
