"""LLM structured-output extraction — the primary path for application and
teacher-evaluation parsing.

Both public functions return the exact same dict shape the legacy regex
extractors produce (see application_profile.extract_application_profile and
teacher_evaluation.extract_teacher_evaluation_profile), so excel_store and the
rest of the pipeline are unaffected by which path produced the row.

One vision LLM call per document does the work the old ~2500 lines of regex
did: it reads the flattened Sunnybrook form (rank numbers, grade marks,
checkboxes) from page images, where the text layer loses spatial position, and
also rates/summarizes the cover letter, resume, and STEM statement. Routing
goes through llm.complete_structured, so the provider stays configurable
(VISION_LLM_PROVIDER / TEXT_LLM_PROVIDER).
"""

import logging
import re

import llm

logger = logging.getLogger(__name__)

# Render at most this many form pages, to bound tokens/cost.
MAX_FORM_PAGES = 4
RENDER_DPI = 200


# ── JSON schemas ─────────────────────────────────────────────────────────────

APPLICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "applicant_name": {"type": ["string", "null"]},
        "email": {"type": ["string", "null"]},
        "school": {"type": ["string", "null"]},
        "city": {"type": ["string", "null"]},
        "current_grade": {"type": ["integer", "null"]},
        "project_ranks": {
            "type": "object",
            "properties": {
                "experimental_work": {"type": ["integer", "null"]},
                "engineering_technology_development": {"type": ["integer", "null"]},
                "programming": {"type": ["integer", "null"]},
            },
            "required": ["experimental_work", "engineering_technology_development", "programming"],
            "additionalProperties": False,
        },
        "courses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "course_code": {"type": ["string", "null"]},
                    "course_title": {"type": ["string", "null"]},
                    "grade_level": {"type": ["integer", "null"]},
                    "percentage": {"type": ["number", "null"]},
                },
                "required": ["course_code", "course_title", "grade_level", "percentage"],
                "additionalProperties": False,
            },
        },
        "cover_letter_rating_10": {"type": ["integer", "null"]},
        "cover_letter_notes": {"type": ["string", "null"]},
        "resume_rating_10": {"type": ["integer", "null"]},
        "resume_notes": {"type": ["string", "null"]},
        "technical_experience": {"type": ["string", "null"]},
        "technical_skills": {"type": ["string", "null"]},
        "volunteer_experience": {"type": "boolean"},
        "previous_research_experience": {"type": "boolean"},
        "career_goals": {"type": ["string", "null"]},
        "stem_statement_rating_10": {"type": ["integer", "null"]},
        "stem_statement_notes": {"type": ["string", "null"]},
        "commitment_to_stem": {"type": ["string", "null"]},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["field", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "applicant_name", "email", "school", "city", "current_grade",
        "project_ranks", "courses", "cover_letter_rating_10", "cover_letter_notes",
        "resume_rating_10", "resume_notes", "technical_experience", "technical_skills",
        "volunteer_experience", "previous_research_experience", "career_goals",
        "stem_statement_rating_10", "stem_statement_notes", "commitment_to_stem",
        "evidence",
    ],
    "additionalProperties": False,
}

TEACHER_EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "student_name": {"type": ["string", "null"]},
        "teacher_name": {"type": ["string", "null"]},
        "gender": {"type": ["string", "null"], "enum": ["Male", "Female", None]},
        "academic_ranking": {
            "type": ["string", "null"],
            "enum": ["Top 5%", "Top 10%", "Top 15%", "Top 20%", "Top 25%", None],
        },
        "criterion_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "score": {"type": ["number", "null"]},
                },
                "required": ["criterion", "score"],
                "additionalProperties": False,
            },
        },
        "total_score": {"type": ["number", "null"]},
        "total_max": {"type": ["number", "null"]},
        "teacher_comments": {"type": ["string", "null"]},
    },
    "required": [
        "student_name", "teacher_name", "gender", "academic_ranking",
        "criterion_scores", "total_score", "total_max", "teacher_comments",
    ],
    "additionalProperties": False,
}


_RULES = """\
Rules:
- Return null for any field you cannot find. Never guess or infer a value that is not present.
- The page images are the source of truth for form fields (checkboxes, rank numbers, grade
  marks): the flat text layer loses the position of filled-in values, so map each number to its
  field by its visual position in the image, not by its order in the text.
- Project ranks: a number written next to a project type is its rank (1 = first choice, 2 = second
  choice). A project row left blank is null.
- For each non-null factual field, add an evidence entry quoting the exact text you read it from.
"""

# Rubric text ported verbatim from the legacy _ai_evaluate_cover_letter /
# _ai_evaluate_stem_statement / _resume_scorecard logic, so the LLM applies the
# same scoring rules (including the FUS caps) the old pipeline used. The FUS
# understanding rating and the transcript rating are NOT scored here — they are
# computed deterministically in Python (see _map_application).
_RUBRIC = """\
Scoring (use the whole application package text below, not just the form). Each rating is an
integer; null only if that document is entirely absent. Ignore form template/instruction text and
evaluate only the applicant's own writing.

cover_letter_rating_10 (0-10): Judge against strong opening explaining why they want the role;
relevant skills/experience; concrete accomplishments; quantified impact; call to action; formal
closing; professional brief format with contact information; addressed to a named person;
personalization to the program; and FUS lab relevance. STRICT caps:
- Merely naming Sunnybrook / FUS / Focused Ultrasound / the program is NOT enough for a high score.
- To score 8-10 the letter must show some understanding of what the FUS lab does (focused ultrasound
  research, non-invasive therapy/treatment, biomedical imaging, device/technology development, brain
  or cancer applications, experimental work, or other specific lab-relevant work).
- If it mentions the program but does NOT show what the FUS lab does, the maximum score is 7.
- If it does NOT reference the FUS lab/program at all, the maximum score is 6.
cover_letter_notes: one concise sentence explaining the score and whether FUS understanding is present.

stem_statement_rating_10 (0-10), from two sub-scores:
- General statement quality (0-5): does it answer what they aspire to be/do, what motivates them to
  get involved in STEM, and why they are a valuable candidate? High marks only when specific,
  evidenced, and clearly written.
- FUS/lab relevance and passion (0-5): high marks only when the applicant shows strong interest in
  focused ultrasound/FUS and/or clear understanding of what the FUS lab does.
Bands: 0 no usable statement; 1-4 weak/generic with little to no FUS relevance; 5 answers the general
questions well but interests/experience are too general or not FUS-relevant; 6-8 answers them and has
some FUS relevance or passion but limited specificity; 9-10 answers them very well and shows strong
FUS passion/understanding with specific evidence. Caps: no clear FUS relevance -> max 5; FUS merely
named without explaining interest/understanding -> max 6; any one of the three general questions
missing -> max 7; no concrete examples -> max 6; mostly a generic trait list without evidence -> max 6.
stem_statement_notes: one concise sentence explaining the score.

resume_rating_10 (0-10) = sum of these components (then cap at 10):
- Experience (0-3): +1 if work/volunteering/tutoring/internship experience is present; +1 more if it
  uses quality action verbs (developed, organized, collaborated...) or quantified impact; +1 more if
  it has FUS/lab relevance (ultrasound, biomedical imaging, medical device, non-invasive, acoustics).
- Education (0-1): +1 if education is clearly listed.
- Skills (0-2): 2 if relevant and clearly listed; 1 if present but generic or weakly connected.
- Awards (0-1): +1 if relevant awards, accomplishments, or certifications are listed.
- Format (0-3): 3 if plain, simple, and concise; 2 if acceptable but could be cleaner; 1 if weak or
  too long.
resume_notes: "Strengths: <...>. Gaps: <...>." naming which components scored and which did not.

technical_experience: concise prose listing hands-on technical/research experience (no commas as
separators). technical_skills: comma-separated concrete skills (languages, lab techniques, tools).
volunteer_experience / previous_research_experience: booleans. career_goals: one sentence on stated
goals. commitment_to_stem: one concise date-free sentence on demonstrated long-term STEM commitment;
summarize evidence categories instead of copying resume entries or dates.
"""


# ── Rendering ────────────────────────────────────────────────────────────────

def _render_pdf(content: bytes, marker: str | None = None, max_pages: int = MAX_FORM_PAGES) -> list[bytes]:
    """Render selected PDF pages to PNG bytes. Prefers pymupdf; falls back to
    pdf2image (poppler). Returns [] when neither rendering path is available."""
    try:
        import fitz  # pymupdf

        doc = fitz.open(stream=content, filetype="pdf")
        if marker is not None:
            indices = [i for i in range(len(doc)) if marker in doc[i].get_text()]
        else:
            indices = list(range(len(doc)))
        if not indices:
            indices = list(range(len(doc)))
        indices = indices[:max_pages]
        return [doc[i].get_pixmap(dpi=RENDER_DPI).tobytes("png") for i in indices]
    except Exception:
        pass

    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(content, dpi=RENDER_DPI)[:max_pages]
        out = []
        for image in images:
            import io

            if image.width > 1800:
                ratio = 1800 / image.width
                image = image.resize((1800, int(image.height * ratio)))
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            out.append(buf.getvalue())
        return out
    except Exception:
        return []


# ── Public extractors ────────────────────────────────────────────────────────

def extract_application_profile_ai(filename: str, text: str, content: bytes | None) -> dict:
    """Primary application extractor. Raises on any failure so the caller can
    fall back to the legacy regex path."""
    images = _render_pdf(content, marker="Intern Application Form") if content else []
    prompt = (
        "You are extracting facts from a high school summer research program application package "
        "(cover letter, resume, Sunnybrook application form, STEM statement).\n"
        + ("Attached are images of the application form pages, followed by the full package text.\n\n"
           if images else "Only the flat text layer is available (no images).\n\n")
        + _RULES + "\n" + _RUBRIC
        + f"\nFull package text:\n<package>\n{text}\n</package>"
    )
    data = llm.complete_structured(
        prompt,
        schema=APPLICATION_SCHEMA,
        schema_name="application_profile",
        max_tokens=16000,
        images=images or None,
    )
    return _map_application(filename, data, text)


def extract_teacher_evaluation_ai(filename: str, text: str, content: bytes | None) -> dict:
    """Primary teacher-evaluation extractor. Raises on any failure so the caller
    can fall back to the legacy regex path."""
    images = _render_pdf(content) if content else []
    prompt = (
        "You are extracting facts from a confidential teacher evaluation form for a high school "
        "summer research program.\n"
        + ("Attached are images of every page, followed by the recovered text layer (which may miss "
           "handwriting and checkmarks).\n\n" if images else "Only the flat text layer is available.\n\n")
        + _RULES
        + "\nThe form has a criterion/score table (e.g. Cooperation, Independence, Enthusiasm, "
          "Creativity, Responsibility), an academic-ranking checkbox row (Top 5%..Top 25%), a total "
          "score out of 50, and a comments section. Read checkmarks and handwritten values from the "
          "images. Set total_max to the form's maximum (usually 50). For teacher_comments, return a "
          "faithful 1-3 sentence summary of what the teacher actually wrote (strengths, concerns, and "
          "any stated area for improvement); do not invent details. Infer gender only from pronouns in "
          "the comments.\n\n"
        + f"Text layer:\n<text>\n{text}\n</text>"
    )
    data = llm.complete_structured(
        prompt,
        schema=TEACHER_EVAL_SCHEMA,
        schema_name="teacher_evaluation",
        max_tokens=4000,
        images=images or None,
    )
    return _map_teacher_eval(filename, data)


# ── Mapping LLM output → legacy dict contract ────────────────────────────────

def _map_application(filename: str, data: dict, text: str) -> dict:
    ranks = data.get("project_ranks") or {}
    courses = data.get("courses") or []
    current_grade = _int_or_none(data.get("current_grade"))
    lowest = _lowest_grade_in_current_grade(courses, current_grade)

    # FUS understanding rating and transcript rating are computed with the legacy
    # deterministic algorithms (concept-count and mark-banding) so they stay
    # reproducible and identical to the old pipeline.
    fus = _legacy_fus_understanding(text)
    transcript_rating = _legacy_transcript_rating(courses)

    notes = _local_missing_section_warnings(text, data, courses)
    if not _clean(data.get("applicant_name")):
        notes.append("Applicant name could not be read.")
    if current_grade is None:
        notes.append("Current grade could not be read.")
    if all(_int_or_none(ranks.get(k)) is None for k in
           ("experimental_work", "engineering_technology_development", "programming")):
        notes.append("Project preference ranks could not be read.")

    return {
        "file_name": filename,
        "applicant_name": _clean(data.get("applicant_name")),
        "email": _clean(data.get("email")),
        "school": _clean(data.get("school")),
        "city": _clean(data.get("city")),
        "current_grade": current_grade if current_grade is not None else "",
        "gender": "",
        "experimental_work_rank": _rank_value(ranks.get("experimental_work")),
        "engineering_technology_development_rank": _rank_value(ranks.get("engineering_technology_development")),
        "programming_rank": _rank_value(ranks.get("programming")),
        "project_preference_notes": _project_preference_notes(ranks),
        "cover_letter_rating_10": _num_or_blank(data.get("cover_letter_rating_10")),
        "cover_letter_notes": _clean(data.get("cover_letter_notes")),
        "fus_understanding_mentioned": bool(fus["mentioned"]),
        "fus_understanding_summary": _clean(fus["summary"]),
        "fus_understanding_rating": _num_or_blank(fus["rating"]),
        "resume_rating_10": _num_or_blank(data.get("resume_rating_10")),
        "resume_notes": _clean(data.get("resume_notes")),
        "features_technical_experience": _clean(data.get("technical_experience")),
        "features_technical_skills": _clean(data.get("technical_skills")),
        "volunteer_experience": "Yes" if data.get("volunteer_experience") else "No",
        "previous_research_experience": "Yes" if data.get("previous_research_experience") else "No",
        "career_goals": _clean(data.get("career_goals")),
        "stem_statement_rating_10": _num_or_blank(data.get("stem_statement_rating_10")),
        "stem_statement_notes": _clean(data.get("stem_statement_notes")),
        "commitment_to_stem": _clean(data.get("commitment_to_stem")),
        "transcript_relative_to_class_median_5": _num_or_blank(transcript_rating),
        "lowest_grade_in_current_grade": lowest if lowest is not None else "",
        "general_application_note": "; ".join(notes),
        "sunnybrook_form_note": _sunnybrook_form_note(data, current_grade, ranks),
    }


def _map_teacher_eval(filename: str, data: dict) -> dict:
    total = _num_or_none(data.get("total_score"))
    total_max = _num_or_none(data.get("total_max")) or 50.0
    rating_5 = round((total / total_max) * 5, 2) if total is not None and total_max else ""
    total_str = f"{_fmt_num(total)}/{_fmt_num(total_max)}" if total is not None else ""
    ranking = _clean(data.get("academic_ranking"))
    comments = _clean(data.get("teacher_comments"))

    notes = []
    if total is None:
        notes.append("Teacher rating could not be read.")
    if not ranking:
        notes.append("Academic ranking could not be read.")
    if not comments:
        notes.append("Teacher comments could not be read.")

    return {
        "teacher_evaluation_file_name": filename,
        "applicant_name": _clean(data.get("student_name")),
        "teacher_report_rating_5": rating_5,
        "teacher_evaluation_total_score": total_str,
        "teacher_evaluation_note": " ".join(notes),
        "teacher_comments": comments,
        "academic_ranking": ranking,
        "gender": _clean(data.get("gender")),
    }


# ── Small helpers ────────────────────────────────────────────────────────────

def _legacy_fus_understanding(text: str) -> dict:
    """Deterministic FUS-understanding scoring, reusing the legacy concept-count
    algorithm so the rating matches the old pipeline exactly."""
    try:
        from application_profile import _evaluate_fus_understanding

        return _evaluate_fus_understanding(text or "")
    except Exception:
        return {"mentioned": False, "summary": "", "rating": ""}


def _legacy_transcript_rating(courses: list[dict]) -> object:
    """Deterministic transcript rating (math/science/English mark banding),
    reusing the legacy algorithm against the LLM-extracted course list."""
    try:
        from application_profile import CourseGrade, _transcript_math_science_english_rating

        grades = []
        for course in courses:
            percentage = _num_or_none(course.get("percentage"))
            if percentage is None:
                continue
            grades.append(CourseGrade(
                grade_level=_int_or_none(course.get("grade_level")) or 0,
                course_title=_clean(course.get("course_title")),
                course_code=_clean(course.get("course_code")),
                percentage=percentage,
            ))
        return _transcript_math_science_english_rating(grades)
    except Exception:
        return ""


def _local_missing_section_warnings(text: str, data: dict, courses: list[dict]) -> list[str]:
    warnings = []
    if not _looks_like_sunnybrook_form(text):
        warnings.append("Sunnybrook application form was not clearly detected")
    if not courses and not _looks_like_transcript(text):
        warnings.append("Transcript section was not clearly detected")
    if _num_or_none(data.get("cover_letter_rating_10")) is None and not _looks_like_cover_letter(text):
        warnings.append("Cover letter section was not confidently detected")
    if _num_or_none(data.get("resume_rating_10")) is None and not _looks_like_resume(text):
        warnings.append("Resume/CV section was not confidently detected")
    return warnings


def _looks_like_sunnybrook_form(text: str) -> bool:
    lowered = (text or "").lower()
    markers = [
        "sunnybrook focused ultrasound lab summer program",
        "current high school",
        "current grade",
        "project preference",
        "more about the applicant",
    ]
    return sum(1 for marker in markers if marker in lowered) >= 2


def _looks_like_transcript(text: str) -> bool:
    return bool(re.search(
        r"Ministry\s+of\s+Education|Ontario\s+Student\s+Transcript|Student\s+Transcript|Report\s+Card",
        text or "",
        re.IGNORECASE,
    ))


def _looks_like_cover_letter(text: str) -> bool:
    return bool(re.search(r"\bDear\b|\bTo\s+Whom\s+It\s+May\s+Concern\b|\bSincerely\b", text or "", re.IGNORECASE))


def _looks_like_resume(text: str) -> bool:
    lowered = (text or "").lower()
    markers = ["resume", "curriculum vitae", "education", "experience", "skills", "awards", "certifications"]
    return sum(1 for marker in markers if marker in lowered) >= 3


def _clean(value: object) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _num_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_or_blank(value: object) -> object:
    number = _num_or_none(value)
    if number is None:
        return ""
    return int(number) if float(number).is_integer() else number


def _rank_value(value: object) -> object:
    number = _int_or_none(value)
    return number if number is not None else ""


def _fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _lowest_grade_in_current_grade(courses: list[dict], current_grade: int | None) -> float | None:
    if current_grade is None:
        return None
    percentages = [
        _num_or_none(course.get("percentage"))
        for course in courses
        if _int_or_none(course.get("grade_level")) == current_grade
    ]
    percentages = [p for p in percentages if p is not None]
    return min(percentages) if percentages else None


_PROJECT_LABELS = {
    "experimental_work": "Experimental Work",
    "engineering_technology_development": "Engineering and Technology Development",
    "programming": "Programming",
}


def _project_preference_notes(ranks: dict) -> str:
    ranked = []
    for key, label in _PROJECT_LABELS.items():
        rank = _int_or_none(ranks.get(key))
        if rank is not None:
            ranked.append((rank, label))
    if not ranked:
        return ""
    ranked.sort()
    return "; ".join(f"#{rank} {label}" for rank, label in ranked)


def _sunnybrook_form_note(data: dict, current_grade: int | None, ranks: dict) -> str:
    missing = []
    if not _clean(data.get("school")):
        missing.append("school")
    if current_grade is None:
        missing.append("current grade")
    if not (data.get("courses") or []):
        missing.append("course grades")
    if missing:
        return "Form fields not read from Sunnybrook application: " + ", ".join(missing) + "."
    return ""
