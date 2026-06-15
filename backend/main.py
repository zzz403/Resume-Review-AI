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
from excel_store import (
    clear_application_data,
    create_student,
    delete_student,
    excel_file_path,
    find_duplicate_student,
    get_student,
    list_students,
    save_application_profile,
    save_teacher_evaluation_profile,
    update_student_fields,
)
from extractor import extract_text
from teacher_evaluation import extract_teacher_evaluation_profile

app = FastAPI()

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
]
# Extra origins (e.g. a non-default local dev port) come from the environment so
# the repo ships the default 3000-3002 set and each machine adds its own via .env.
_extra_cors_origins = [origin.strip() for origin in os.getenv("EXTRA_CORS_ORIGINS", "").split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_CORS_ORIGINS + _extra_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReviewRequest(BaseModel):
    resume_text: str


class LLMSettingsRequest(BaseModel):
    provider: str
    api_key: str
    role: str = "text"


class StudentCreateRequest(BaseModel):
    name: str
    email: str = ""


class StudentUpdateRequest(BaseModel):
    updates: dict[str, str | int | float | bool | None]


RESUME_REVIEW_DIR = Path(__file__).resolve().parents[2]
TEACHER_EVALUATION_DIR = RESUME_REVIEW_DIR / "teacher_evaluations"
APPLICATION_DIR = RESUME_REVIEW_DIR / "applications"

INLINE_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    content = await file.read()
    text = extract_text(file.filename or "", content)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")
    return {"text": text}

@app.get("/students")
def get_students():
    return list_students()


@app.post("/students")
def add_student(request: StudentCreateRequest):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Student name is required.")
    return create_student(name, request.email)


@app.post("/students/import-file")
@app.post("/students/import-application")
async def import_file(file: UploadFile = File(...)):
    content = await file.read()
    text = extract_text(file.filename or "", content)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")

    fallback_name = Path(file.filename or "application").stem.replace("_", " ").replace("-", " ").strip()
    document_type = _classify_import_document(file.filename or "", text)
    if document_type == "":
        raise HTTPException(
            status_code=422,
            detail=f"Could not tell whether {file.filename or 'this file'} is an application or teacher evaluation.",
        )

    if document_type == "teacher_evaluation":
        profile = extract_teacher_evaluation_profile(file.filename or "", text, content)
        student_name = str(profile.get("applicant_name") or "").strip() or fallback_name or "Unnamed applicant"
        duplicate = find_duplicate_student(student_name, "")
        if duplicate is not None:
            existing = duplicate["student"]
            if _row_has_teacher_evaluation(existing):
                raise _duplicate_import_error(file.filename or "teacher evaluation", "teacher evaluation", duplicate)
            student_id = existing["student_id"]
        else:
            student_id = create_student(student_name)["student_id"]

        TEACHER_EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
        file_name = _safe_file_name(file.filename or "teacher_evaluation")
        saved_path = _unique_path(TEACHER_EVALUATION_DIR / file_name)
        saved_path.write_bytes(content)
        profile["teacher_evaluation_file_name"] = saved_path.name
        return save_teacher_evaluation_profile(profile, student_id)

    profile = extract_application_profile(file.filename or "", text, content)
    student_name = str(profile.get("applicant_name") or "").strip() or fallback_name or "Unnamed applicant"
    student_email = str(profile.get("email") or "")
    duplicate = find_duplicate_student(student_name, student_email)
    if duplicate is not None:
        existing = duplicate["student"]
        if _row_has_application(existing):
            raise _duplicate_import_error(file.filename or "application", "application", duplicate)
        student_id = existing["student_id"]
    else:
        student_id = create_student(student_name, student_email)["student_id"]

    APPLICATION_DIR.mkdir(parents=True, exist_ok=True)
    file_name = _safe_file_name(file.filename or "application")
    saved_path = _unique_path(APPLICATION_DIR / file_name)
    saved_path.write_bytes(content)

    profile["file_name"] = saved_path.name
    return save_application_profile(profile, student_id)


@app.get("/students/{student_id}")
def read_student(student_id: str):
    student = get_student(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return student


@app.delete("/students/{student_id}")
def remove_student(student_id: str):
    removed = delete_student(student_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return {"message": "Student deleted", "student_id": student_id}


@app.post("/students/{student_id}/application")
async def submit_application(student_id: str, file: UploadFile = File(...)):
    if get_student(student_id) is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    content = await file.read()
    text = extract_text(file.filename or "", content)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from this file")

    # Persist the original file so the reviewer can read it side-by-side with the
    # AI's fields and correct them against the source.
    APPLICATION_DIR.mkdir(parents=True, exist_ok=True)
    file_name = _safe_file_name(file.filename or "application")
    saved_path = _unique_path(APPLICATION_DIR / file_name)
    saved_path.write_bytes(content)

    profile = extract_application_profile(file.filename or "", text, content)
    profile["file_name"] = saved_path.name
    saved = save_application_profile(profile, student_id)
    return saved


@app.post("/students/{student_id}/teacher-evaluation")
async def submit_teacher_evaluation(student_id: str, file: UploadFile = File(...)):
    if get_student(student_id) is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Teacher evaluation file is empty")

    TEACHER_EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    file_name = _safe_file_name(file.filename or "teacher_evaluation")
    saved_path = _unique_path(TEACHER_EVALUATION_DIR / file_name)
    saved_path.write_bytes(content)
    text = extract_text(file.filename or "", content)
    profile = extract_teacher_evaluation_profile(saved_path.name, text, content)
    saved = save_teacher_evaluation_profile(profile, student_id)
    return saved

@app.patch("/students/{student_id}")
def edit_student(student_id: str, request: StudentUpdateRequest):
    if get_student(student_id) is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    try:
        return update_student_fields(student_id, request.updates)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Student not found.") from exc


@app.get("/students/{student_id}/files/application")
def get_application_file(student_id: str):
    student = get_student(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return _serve_stored_file(APPLICATION_DIR, student.get("file_name"), "application")


@app.get("/students/{student_id}/files/teacher-evaluation")
def get_teacher_evaluation_file(student_id: str):
    student = get_student(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found.")
    return _serve_stored_file(
        TEACHER_EVALUATION_DIR, student.get("teacher_evaluation_file_name"), "teacher evaluation"
    )


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
    removed_teacher_evaluations = _clear_dir_files(TEACHER_EVALUATION_DIR)
    removed_applications = _clear_dir_files(APPLICATION_DIR)
    return {
        "message": "Application data cleared",
        "removed_data_files": cleared["removed_files"],
        "removed_teacher_evaluations": removed_teacher_evaluations,
        "removed_applications": removed_applications,
        "excel_path": cleared["excel_path"],
    }

@app.get("/settings/llm")
def get_llm_settings():
    text_provider = llm.get_text_provider()
    vision_provider = llm.get_vision_provider()
    return {
        "provider": text_provider,
        "configured": llm.is_configured(text_provider),
        "text_provider": text_provider,
        "text_configured": llm.is_configured(text_provider),
        "vision_provider": vision_provider,
        "vision_configured": llm.is_configured(vision_provider),
        "available_providers": llm.available_providers(),
        "available_vision_providers": llm.available_vision_providers(),
    }


@app.post("/settings/llm")
def save_llm_settings(request: LLMSettingsRequest):
    provider = request.provider.strip().lower()
    if provider not in llm.available_providers():
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}. Choose one of {llm.available_providers()}.")
    role = request.role.strip().lower()
    if role not in {"text", "vision"}:
        raise HTTPException(status_code=400, detail="Role must be text or vision.")
    if role == "vision" and provider not in llm.available_vision_providers():
        raise HTTPException(status_code=400, detail=f"{provider} does not support image reading. Choose one of {llm.available_vision_providers()}.")

    api_key = request.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required.")

    try:
        llm.validate_key(api_key, provider=provider)
    except llm.LLMAuthError as exc:
        raise HTTPException(status_code=400, detail=f"The {provider} API key was rejected. Check the key and try again.") from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Could not validate the {provider} API key: {exc}") from exc

    provider_env = "VISION_LLM_PROVIDER" if role == "vision" else "TEXT_LLM_PROVIDER"
    _write_env_value(provider_env, provider)
    _write_env_value(llm.provider_key_env(provider), api_key)
    os.environ[provider_env] = provider
    os.environ[llm.provider_key_env(provider)] = api_key
    return {
        "provider": provider,
        "role": role,
        "configured": True,
        "message": f"{provider} {role} API key is valid and saved.",
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


def _serve_stored_file(directory: Path, file_name: object, label: str) -> FileResponse:
    if not file_name:
        raise HTTPException(status_code=404, detail=f"No {label} file on record.")
    path = directory / str(file_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"The stored {label} file is missing.")
    media_type = INLINE_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    # inline so the browser previews PDFs/images in the viewer rather than downloading.
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="inline",
    )


def _classify_import_document(filename: str, text: str) -> str:
    teacher_score = _teacher_evaluation_score(filename, text)
    application_score = _application_score(filename, text)
    if teacher_score >= 2 and teacher_score >= application_score:
        return "teacher_evaluation"
    if application_score >= 2 and application_score > teacher_score:
        return "application"
    if _looks_like_teacher_filename(filename):
        return "teacher_evaluation"
    return ""


def _teacher_evaluation_score(filename: str, text: str) -> int:
    haystack = f"{filename}\n{text[:5000]}".lower()
    teacher_markers = [
        "teacher evaluation",
        "teacher reference",
        "teacher recommendation",
        "teacher's report",
        "student's full name",
        "students full name",
        "academic ranking",
        "further comments",
        "total score",
    ]
    return sum(1 for marker in teacher_markers if marker in haystack)


def _application_score(filename: str, text: str) -> int:
    haystack = f"{filename}\n{text[:8000]}".lower()
    application_markers = [
        "fus hs program",
        "focused ultrasound lab",
        "sunnybrook",
        "application form",
        "cover letter",
        "resume",
        "curriculum vitae",
        "transcript",
        "stem statement",
        "project preference",
        "current grade",
        "engineering and technology development",
        "experimental work",
        "programming",
    ]
    return sum(1 for marker in application_markers if marker in haystack)


def _row_has_application(row: dict) -> bool:
    file_name = str(row.get("file_name") or "")
    if file_name and _looks_like_teacher_filename(file_name):
        return False
    return any(row.get(field) not in ("", None) for field in [
        "file_name",
        "resume_rating_10",
        "cover_letter_rating_10",
        "stem_statement_rating_10",
    ])


def _row_has_teacher_evaluation(row: dict) -> bool:
    return any(row.get(field) not in ("", None) for field in [
        "teacher_evaluation_file_name",
        "teacher_report_rating_5",
        "teacher_evaluation_total_score",
        "teacher_evaluation_note",
        "teacher_comments",
        "academic_ranking",
    ])


def _looks_like_teacher_filename(filename: str) -> bool:
    lowered = filename.lower()
    return "teacher" in lowered or "reference" in lowered or "recommendation" in lowered


def _duplicate_import_error(filename: str, doc_type: str, duplicate: dict) -> HTTPException:
    existing = duplicate["student"]
    duplicate_name = existing.get("applicant_name") or "existing applicant"
    return HTTPException(
        status_code=409,
        detail={
            "message": f"Duplicate {doc_type} skipped: {duplicate_name} already has a {doc_type}.",
            "filename": filename,
            "doc_type": doc_type,
            "matched_applicant_name": duplicate_name,
            "matched_email": existing.get("email", ""),
            "reason": duplicate["reason"],
        },
    )


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


def _clear_dir_files(directory: Path) -> list[str]:
    if not directory.exists():
        return []

    removed = []
    for path in directory.iterdir():
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
