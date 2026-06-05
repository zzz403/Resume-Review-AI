import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH)

import llm
from application_profile import extract_application_profile
from ai import review_resume
from db import save_review, fetch_history
from excel_store import clear_application_data, excel_file_path, save_application_profile, save_teacher_evaluation_profile
from extractor import extract_text
from teacher_evaluation import extract_teacher_evaluation_profile

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReviewRequest(BaseModel):
    resume_text: str


class LLMSettingsRequest(BaseModel):
    provider: str
    api_key: str


RESUME_REVIEW_DIR = Path(__file__).resolve().parents[2]
TEACHER_EVALUATION_DIR = RESUME_REVIEW_DIR / "teacher_evaluations"

@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    content = await file.read()
    text = extract_text(file.filename or "", content)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")
    return {"text": text}

@app.post("/applications")
async def submit_application(file: UploadFile = File(...)):
    content = await file.read()
    text = extract_text(file.filename or "", content)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")

    profile = extract_application_profile(file.filename or "", text, content)
    saved = save_application_profile(profile)
    return {
        "message": "Application saved to Excel",
        "file_name": saved["file_name"],
        "applicant_name": saved["applicant_name"],
        "excel_path": str(excel_file_path()),
    }

@app.post("/teacher-evaluations")
async def submit_teacher_evaluation(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Teacher evaluation file is empty")

    TEACHER_EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    file_name = _safe_file_name(file.filename or "teacher_evaluation")
    saved_path = _unique_path(TEACHER_EVALUATION_DIR / file_name)
    saved_path.write_bytes(content)
    text = extract_text(file.filename or "", content)
    profile = extract_teacher_evaluation_profile(saved_path.name, text, content)
    saved = save_teacher_evaluation_profile(profile)

    return {
        "message": "Teacher evaluation saved",
        "file_name": saved_path.name,
        "saved_path": str(saved_path),
        "applicant_name": saved.get("applicant_name", ""),
        "teacher_report_rating_5": saved.get("teacher_report_rating_5", ""),
        "academic_ranking": saved.get("academic_ranking", ""),
    }

@app.get("/applications.xlsx")
def download_applications_excel():
    return FileResponse(
        excel_file_path(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="applications.xlsx",
    )

@app.delete("/application-data")
def delete_application_data():
    cleared = clear_application_data()
    removed_teacher_evaluations = _clear_teacher_evaluation_files()
    return {
        "message": "Application data cleared",
        "removed_data_files": cleared["removed_files"],
        "removed_teacher_evaluations": removed_teacher_evaluations,
        "excel_path": cleared["excel_path"],
    }

@app.get("/settings/llm")
def get_llm_settings():
    provider = llm.get_provider()
    return {
        "provider": provider,
        "configured": llm.is_configured(provider),
        "available_providers": llm.available_providers(),
    }


@app.post("/settings/llm")
def save_llm_settings(request: LLMSettingsRequest):
    provider = request.provider.strip().lower()
    if provider not in llm.available_providers():
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}. Choose one of {llm.available_providers()}.")

    api_key = request.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required.")

    try:
        llm.validate_key(api_key, provider=provider)
    except llm.LLMAuthError as exc:
        raise HTTPException(status_code=400, detail=f"The {provider} API key was rejected. Check the key and try again.") from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Could not validate the {provider} API key: {exc}") from exc

    _write_env_value("LLM_PROVIDER", provider)
    _write_env_value(llm.provider_key_env(provider), api_key)
    os.environ["LLM_PROVIDER"] = provider
    os.environ[llm.provider_key_env(provider)] = api_key
    return {
        "provider": provider,
        "configured": True,
        "message": f"{provider} API key is valid and saved.",
        "key_preview": _key_preview(api_key),
    }

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


def _safe_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(file_name).name).strip()
    return cleaned or "teacher_evaluation"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=500, detail="Could not create unique file name")


def _clear_teacher_evaluation_files() -> list[str]:
    if not TEACHER_EVALUATION_DIR.exists():
        return []

    removed = []
    for path in TEACHER_EVALUATION_DIR.iterdir():
        if not path.is_file():
            continue
        path.unlink()
        removed.append(str(path))
    return removed


def _write_env_value(key: str, value: str) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    replacement = f"{key}={value}"
    updated = False
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = replacement
            updated = True
            break
    if not updated:
        lines.append(replacement)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _key_preview(api_key: str) -> str:
    return f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 18 else "saved"
