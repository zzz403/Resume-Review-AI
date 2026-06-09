import json
import io
import os
import re
from dataclasses import dataclass

import llm


@dataclass(frozen=True)
class CourseGrade:
    grade_level: int
    course_title: str
    course_code: str
    percentage: int


@dataclass(frozen=True)
class ApplicationSections:
    cover_letter: str
    resume_text: str
    form_text: str
    stem_statement: str
    transcript_text: str
    warnings: list[str]


@dataclass(frozen=True)
class TextMatch:
    start_pos: int
    end_pos: int

    def start(self) -> int:
        return self.start_pos

    def end(self) -> int:
        return self.end_pos


def extract_application_profile(filename: str, text: str, content: bytes | None = None) -> dict:
    sections = _classify_application_sections(text)
    form_courses = _extract_form_course_grades(sections.form_text)
    transcript_courses = _extract_course_grades(sections.transcript_text or text)
    courses = form_courses or transcript_courses
    form_current_grade = _infer_current_grade(sections.form_text, form_courses)
    current_grade = form_current_grade or _infer_current_grade(sections.form_text or text, courses)
    current_grade_courses = [course for course in courses if course.grade_level == current_grade]
    lowest_current_grade = min((course.percentage for course in current_grade_courses), default=None)
    transcript_rating = _transcript_math_science_english_rating(courses)

    cover_letter = sections.cover_letter
    resume_text = sections.resume_text
    stem_statement = sections.stem_statement
    applicant_text = "\n".join([cover_letter, resume_text, stem_statement])

    technical_experience = _technical_experience(resume_text)
    technical_skills = _technical_skills(resume_text)
    resume_features = _resume_feature_summary(resume_text, stem_statement)
    applicant_name = _extract_name(sections.form_text or text, filename)
    school = _extract_school(sections.form_text, text)
    city = _extract_city(sections.form_text, text)
    project_ranks = _extract_project_preference_ranks(sections.form_text or text, content)
    visual_form = {}
    if _needs_visual_sunnybrook_fallback(
        content,
        form_text=sections.form_text,
        applicant_name=applicant_name,
        school=school,
        current_grade=current_grade,
        project_ranks=project_ranks,
        form_courses=form_courses,
    ):
        visual_form = _ai_extract_sunnybrook_form_from_images(content)
        applicant_name = applicant_name or str(visual_form.get("full_name", "")).strip()
        school = school or str(visual_form.get("current_high_school", "")).strip()
        city = city or str(visual_form.get("city", "")).strip()
        current_grade = current_grade or _int_or_none(visual_form.get("current_grade"))
        project_ranks = _merge_project_ranks(project_ranks, visual_form)

    general_application_notes = list(sections.warnings)
    sunnybrook_form_note = _sunnybrook_form_note(
        sections.form_text,
        form_courses,
        form_current_grade,
        project_ranks,
        stem_statement,
        visual_form,
    )

    fus_text = "\n".join([cover_letter, stem_statement])
    fus_mentions = _keyword_count(fus_text, ["focused ultrasound", "fus", "ultrasound"])
    fus_understanding = _evaluate_fus_understanding(fus_text)
    cover_letter_evaluation = _evaluate_cover_letter(cover_letter, fus_mentions)
    stem_evaluation = _evaluate_stem_statement(stem_statement)

    return {
        "file_name": filename,
        "applicant_name": applicant_name,
        "email": _extract_email(text),
        "school": school,
        "city": city,
        "current_grade": current_grade,
        "gender": "",
        "experimental_work_rank": project_ranks.get("experimental_work", ""),
        "engineering_technology_development_rank": project_ranks.get("engineering_technology_development", ""),
        "programming_rank": project_ranks.get("programming", ""),
        "project_preference_notes": _project_preference_notes(project_ranks),
        "cover_letter_rating_10": cover_letter_evaluation["score"],
        "cover_letter_notes": cover_letter_evaluation["notes"],
        "fus_understanding_mentioned": fus_understanding["mentioned"],
        "fus_understanding_summary": fus_understanding["summary"],
        "fus_understanding_rating": fus_understanding["rating"],
        "resume_rating_10": _rate_resume(resume_text, technical_experience, technical_skills),
        "resume_notes": _resume_notes(resume_text),
        "features_technical_experience": resume_features["experience"],
        "features_technical_skills": resume_features["skills"],
        "volunteer_experience": _has_any(text, ["volunteer", "community involvement"]),
        "previous_research_experience": _has_previous_research_experience(resume_text, stem_statement),
        "career_goals": _career_goals(stem_statement),
        "stem_statement_rating_10": stem_evaluation["score"],
        "stem_statement_notes": stem_evaluation["notes"],
        "commitment_to_stem": _commitment_to_stem(resume_text, stem_statement, courses),
        "transcript_relative_to_class_median_5": transcript_rating,
        "lowest_grade_in_current_grade": lowest_current_grade,
        "general_application_note": "; ".join(general_application_notes),
        "sunnybrook_form_note": sunnybrook_form_note,
    }


def _extract_email(text: str) -> str:
    match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", text)
    return match.group(0) if match else ""


def _extract_name(text: str, filename: str) -> str:
    form_name = _extract_name_from_form(text)
    file_name = _name_from_filename(filename)
    if form_name:
        value = form_name
        if value:
            if file_name and len(file_name.split()[-1]) > len(value.split()[-1]):
                return file_name
            return value
    for line in _clean_lines(text)[:10]:
        if "@" not in line and len(line.split()) in (2, 3) and line.isupper():
            return line.title()
    return file_name


def _extract_name_from_form(text: str) -> str:
    form_name = re.search(r"Full\s+Name:[ \t_]*([^\n_]+)", text, re.IGNORECASE)
    if form_name:
        value = _clean_cell(form_name.group(1))
        if value:
            return value

    lines = _clean_lines(text)
    for index, line in enumerate(lines):
        if not re.search(r"\bFull\s+Name\b", line, re.IGNORECASE):
            continue
        for candidate in lines[index + 1 : index + 60]:
            value = _clean_cell(candidate)
            if not value:
                continue
            if re.search(
                r"\b(Current\s+High\s+School|Current\s+Grade|How\s+did\s+you\s+hear|Sunnybrook|Application|Project|Preference|Academic|Grade|Science|Math|Programming|Engineering|Development|Experimental|Description|Computer|Please|work with animals|specify)\b",
                value,
                re.IGNORECASE,
            ):
                continue
            if re.fullmatch(r"\d{1,3}|x", value, re.IGNORECASE):
                continue
            if re.fullmatch(r"[A-Z][A-Za-z' -]+(?:\s+[A-Z][A-Za-z' -]+){1,3}", value):
                return value
    return ""


def _name_from_filename(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = re.sub(r"_?FUS\s+HS\s+Program\s+20\d{2}$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_-]+", " ", stem)
    return _clean_cell(stem)


def _extract_school(form_text: str, full_text: str) -> str:
    form_school = _extract_current_high_school_from_form(form_text)
    if form_school:
        return form_school

    patterns = [
        r"Name of School\s+([^\n]+)",
        r"High School Diploma:.*?\n(.+?)\s+-",
        r"(Dr\.\s*G\.W\.\s*Williams Secondary School)",
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            value = _clean_school_value(match.group(1))
            if value:
                return value

    for line in _clean_lines(full_text):
        match = re.search(r"\b([A-Z][A-Za-z .'-]+?\s+(?:High|Secondary)\s+School)\b", line)
        if match:
            value = _clean_school_value(match.group(1))
            if value:
                return value
    return ""


def _extract_current_high_school_from_form(text: str) -> str:
    if not text.strip():
        return ""

    field = re.search(
        r"Current\s+High\s+School\s*\(please\s+include\s+city\):?\s*([^\n]+)",
        text,
        re.IGNORECASE,
    )
    if field:
        value = _clean_school_value(field.group(1))
        if value:
            return value

    lines = _clean_lines(text)
    for index, line in enumerate(lines):
        if not re.search(r"Current\s+High\s+School", line, re.IGNORECASE):
            continue
        for candidate in lines[index + 1 : index + 60]:
            value = _clean_school_value(candidate)
            lowered = value.lower()
            if not value:
                continue
            if not re.match(r"[A-Z0-9]", value):
                continue
            if any(
                marker in lowered
                for marker in [
                    "current grade",
                    "how did you hear",
                    "project type",
                    "academic grades",
                    "sunnybrook",
                    "application",
                    "first name",
                    "last name",
                    "project preference",
                    "academic grades",
                    "please rate",
                    "please fill",
                    "specific course",
                    "stem courses",
                    "include grades",
                    "bench-top",
                    "hands-on",
                    "may include",
                    "electronics design",
                    "animal work",
                    "please specify",
                    "description below",
                    "work with animals",
                ]
            ):
                continue
            if re.fullmatch(r"\d{1,3}|x", value, re.IGNORECASE):
                continue
            if "," in value or re.search(r"\b(C\.?S\.?S\.?|secondary|high school|collegiate|academy|school)\b", value, re.IGNORECASE):
                return value

    for line in _clean_lines(text):
        if re.search(r"\b(secondary|high)\s+school\b", line, re.IGNORECASE):
            value = _clean_school_value(line)
            if value and "current high school" not in value.lower():
                return value
    return ""


def _clean_school_value(value: str) -> str:
    value = re.sub(r"_+", " ", value)
    value = re.split(r"\bCurrent\s+Grade:|\bEnrolled\s+in\s+Specialty\s+Program\b|\bHow\s+did\s+you\s+hear\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.sub(r"\b(Current High School|please include city|Name of School|Number|Date of Entry)\b", " ", value, flags=re.IGNORECASE)
    value = _clean_cell(value)
    if not value or len(value) < 4:
        return ""
    if value.lower() in {"number date of entry", "date of entry", "number"}:
        return ""
    if re.fullmatch(r"[\W_]+", value):
        return ""
    return value


def _extract_city(form_text: str, full_text: str) -> str:
    school_from_form = _extract_current_high_school_from_form(form_text)
    city = _city_from_school_value(school_from_form)
    if city:
        return city

    school_line = re.search(r"Secondary School\s*[-–]\s*([^\n]+)", full_text, re.IGNORECASE)
    if school_line:
        city = _city_from_school_value(school_line.group(1))
        if city:
            return city
    match = re.search(r"\b([A-Za-z .'-]+),\s*(?:ON|Ontario)\b", full_text, re.IGNORECASE)
    return f"{match.group(1).strip()}, Ontario" if match else ""


def _city_from_school_value(value: str) -> str:
    value = _clean_cell(value)
    if not value:
        return ""

    province_match = re.search(r",\s*([A-Za-z .'-]{2,}),\s*(ON|Ontario)\b", value, re.IGNORECASE)
    if province_match:
        return f"{_clean_cell(province_match.group(1))}, Ontario"

    trailing_province = re.search(r",\s*([A-Za-z .'-]{2,})\s+(ON|Ontario)\b", value, re.IGNORECASE)
    if trailing_province:
        return f"{_clean_cell(trailing_province.group(1))}, Ontario"

    if "," in value:
        candidate = _clean_cell(value.rsplit(",", 1)[-1])
        candidate = re.sub(r"\b(?:ON|Ontario)\b\.?$", "", candidate, flags=re.IGNORECASE)
        candidate = _clean_cell(candidate)
        if _looks_like_city(candidate):
            return candidate

    dash_match = re.search(r"\s[-–]\s([A-Za-z .'-]{2,})(?:\s+(?:ON|Ontario))?$", value, re.IGNORECASE)
    if dash_match:
        candidate = _clean_cell(dash_match.group(1))
        if _looks_like_city(candidate):
            return candidate
    return ""


def _looks_like_city(value: str) -> bool:
    if not value:
        return False
    if re.search(r"\b(?:school|secondary|c\.?s\.?s\.?|academy|college|collegiate|institute)\b", value, re.IGNORECASE):
        return False
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,60}", value))


def _extract_form_course_grades(text: str) -> list[CourseGrade]:
    academic_block = _academic_grades_block(text)
    if not academic_block:
        return []

    courses: list[CourseGrade] = []
    pattern = re.compile(
        r"([A-Za-z][A-Za-z &/,.'()-]+?)\s*\(([A-Z]{3}\d[A-Z0-9]{0,3})\)\s*[;:]?\s*:?\s*[_\s%]*([0-9]{2,3}|X)(?=[_\W]|$)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(academic_block):
        course = _form_course_grade(match.group(2), match.group(3), match.group(1))
        if course:
            courses.append(course)

    code_only_pattern = re.compile(r"\b([A-Z]{3}\d[A-Z0-9]{0,3})\)\s*[;:]?\s*:?\s*[_\s%]*([0-9]{2,3}|X)(?=[_\W]|$)", re.IGNORECASE)
    for match in code_only_pattern.finditer(academic_block):
        if any(course.course_code == _normalize_course_code(match.group(1)) for course in courses):
            continue
        course = _form_course_grade(match.group(1), match.group(2), "")
        if course:
            courses.append(course)
    return _dedupe_course_grades(courses) or _extract_form_course_grades_from_appended_values(academic_block)


def _extract_form_course_grades_from_appended_values(text: str) -> list[CourseGrade]:
    codes = _form_course_codes_in_order(text)
    values = _form_appended_grade_values(text)
    if not codes or not values:
        return []

    courses: list[CourseGrade] = []
    for code, raw_mark in zip(codes, values):
        course = _form_course_grade(code, raw_mark, "")
        if course:
            courses.append(course)
    return _dedupe_course_grades(courses)


def _form_course_codes_in_order(text: str) -> list[str]:
    codes = []
    for match in re.finditer(r"\(([A-Z]{3}\d[A-Z0-9]{0,3})\):\s*_", text, re.IGNORECASE):
        codes.append(_normalize_course_code(match.group(1)))
    return _dedupe(codes)


def _form_appended_grade_values(text: str) -> list[str]:
    lines = _clean_lines(text)
    start_index = None
    for index, line in enumerate(lines):
        if line.lower() == "programming":
            start_index = index + 1
            break
    if start_index is None:
        return []

    values = []
    started = False
    for line in lines[start_index:]:
        if started and "sunnybrook focused ultrasound lab summer program" in line.lower():
            break
        match = re.fullmatch(r"([0-9]{2,3})%?|X", line, re.IGNORECASE)
        if not match:
            continue
        if match.group(1) and int(match.group(1)) < 50:
            continue
        if not started and not match.group(1):
            continue
        started = True
        values.append(match.group(1).upper() if match.group(1) else "X")
    return values


def _form_course_grade(code: str, raw_mark: str, title: str) -> CourseGrade | None:
    raw_mark = raw_mark.upper()
    if raw_mark == "X":
        return None
    percentage = int(raw_mark)
    if percentage > 100:
        return None
    normalized_code = _normalize_course_code(code)
    grade_level = _grade_level_from_course_code(normalized_code)
    if grade_level is None:
        return None
    return CourseGrade(
        grade_level=grade_level,
        course_title=_clean_cell(title),
        course_code=normalized_code,
        percentage=percentage,
    )


def _academic_grades_block(text: str) -> str:
    start = re.search(r"Academic\s+Grades:|GRADES\s*\(", text, re.IGNORECASE)
    if not start:
        return ""
    end = re.search(r"More\s+about\s+the\s+Applicant:", text[start.end() :], re.IGNORECASE)
    if end:
        return text[start.start() : start.end() + end.start()]
    return text[start.start() :]


def _extract_course_grades(text: str) -> list[CourseGrade]:
    courses: list[CourseGrade] = []
    pattern = re.compile(
        r"\b20\d{2}\s+\d{2}\s+(1[0-2])\s+(.+?)\s+([A-Z]{3}\d[A-Z0-9]{1,3})\s+(\d{2,3})\s+1\.00",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        courses.append(
            CourseGrade(
                grade_level=int(match.group(1)),
                course_title=_clean_cell(match.group(2)),
                course_code=match.group(3),
                percentage=int(match.group(4)),
            )
        )
    return courses or _extract_course_grades_from_code_percent(text)


def _extract_course_grades_from_code_percent(text: str) -> list[CourseGrade]:
    courses: list[CourseGrade] = []
    pattern = re.compile(r"\b([A-Z]{2}[A-ZIl]\d[A-Z0-9]{1,3})\s+(\d{2,3})\b")
    for match in pattern.finditer(text):
        code = _normalize_course_code(match.group(1))
        percentage = int(match.group(2))
        if percentage > 100:
            continue
        grade_level = _grade_level_from_course_code(code)
        if grade_level is None:
            continue
        courses.append(
            CourseGrade(
                grade_level=grade_level,
                course_title="",
                course_code=code,
                percentage=percentage,
            )
        )
    return _dedupe_course_grades(courses)


def _normalize_course_code(code: str) -> str:
    return code.upper().replace("L", "I") if code.upper().startswith("SB") else code.upper()


def _grade_level_from_course_code(code: str) -> int | None:
    match = re.search(r"\d", code)
    if not match:
        return None
    grade_digit = int(match.group(0))
    if grade_digit in (1, 2, 3, 4):
        return grade_digit + 8
    return None


def _dedupe_course_grades(courses: list[CourseGrade]) -> list[CourseGrade]:
    seen = set()
    result = []
    for course in courses:
        key = (course.course_code, course.percentage)
        if key not in seen:
            seen.add(key)
            result.append(course)
    return result


def _transcript_math_science_english_rating(courses: list[CourseGrade]) -> int | str:
    relevant_marks = [
        course.percentage
        for course in courses
        if _is_math_science_or_english(course)
    ]
    if not relevant_marks:
        return ""
    average = sum(relevant_marks) / len(relevant_marks)
    if average > 90:
        return 5
    if average >= 85:
        return 4
    if average >= 75:
        return 3
    if average >= 65:
        return 2
    return 1


def _is_math_science_or_english(course: CourseGrade) -> bool:
    code = course.course_code.upper()
    title = course.course_title.lower()
    if code.startswith("M"):
        return True
    if code.startswith("S"):
        return True
    if code.startswith("ENG") or code.startswith("NBE"):
        return True
    return any(term in title for term in ["math", "science", "physics", "chemistry", "biology", "english"])


def _extract_project_preference_ranks(text: str, content: bytes | None) -> dict[str, int | str]:
    ranks = _project_ranks_from_pdf_annotations(content) if content else {}
    if ranks:
        return ranks
    return _project_ranks_from_text(text)


def _needs_visual_sunnybrook_fallback(
    content: bytes | None,
    *,
    form_text: str,
    applicant_name: str,
    school: str,
    current_grade: int | None,
    project_ranks: dict[str, int | str],
    form_courses: list[CourseGrade],
) -> bool:
    if not content or not llm.is_configured():
        return False
    if not form_text.strip():
        return True
    if not applicant_name or not school or not current_grade:
        return True
    if len([rank for rank in project_ranks.values() if isinstance(rank, int)]) < 2:
        return True
    if _academic_grades_block(form_text) and not form_courses:
        return True
    return False


def _ai_extract_sunnybrook_form_from_images(content: bytes | None) -> dict:
    if not content:
        return {}

    pages = _pdf_pages_as_png(content, max_pages=5)
    if not pages:
        return {}

    merged: dict[str, object] = {}
    prompt = (
        "Read this page image from a Sunnybrook Focused Ultrasound Lab high school application package. "
        "If this page is not the Sunnybrook application form, return JSON only as {}. "
        "Extract only visible typed or handwritten/form-filled values. Do not infer or guess. "
        "Return JSON only with keys: full_name, current_high_school, city, current_grade, "
        "experimental_work_rank, engineering_technology_development_rank, programming_rank. "
        "Ranks must be 1, 2, 3, or empty. City may be one or more words and may appear after a comma in the school field."
    )
    for image_png in pages:
        try:
            raw = llm.complete_vision(prompt, max_tokens=350, temperature=0, image_png=image_png)
            data = _parse_json_object(raw)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if merged.get(key) not in ("", None):
                continue
            if value in ("", None):
                continue
            merged[key] = value
    return merged


def _pdf_pages_as_png(content: bytes, max_pages: int) -> list[bytes]:
    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(content, dpi=220, first_page=1, last_page=max_pages)
    except Exception:
        return []

    result = []
    for image in images:
        if image.width > 1800:
            ratio = 1800 / image.width
            image = image.resize((1800, int(image.height * ratio)))
        output = io.BytesIO()
        image.save(output, format="PNG")
        result.append(output.getvalue())
    return result


def _merge_project_ranks(ranks: dict[str, int | str], visual_form: dict) -> dict[str, int | str]:
    merged = dict(ranks)
    for key in ["experimental_work", "engineering_technology_development", "programming"]:
        rank_key = f"{key}_rank"
        if isinstance(merged.get(key), int):
            continue
        rank = _int_or_none(visual_form.get(rank_key))
        if rank in {1, 2, 3}:
            merged[key] = rank
    return merged


def _int_or_none(value: object) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _project_ranks_from_pdf_annotations(content: bytes | None) -> dict[str, int]:
    if not content:
        return {}
    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return {}

    for page in reader.pages:
        labels = _project_label_positions(page)
        if len(labels) < 3:
            continue

        ranks: dict[str, int] = {}
        for annot_ref in page.get("/Annots") or []:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/FreeText":
                continue
            value = str(annot.get("/Contents") or "").strip()
            if value not in {"1", "2", "3"}:
                continue
            rect = annot.get("/Rect") or []
            if len(rect) != 4:
                continue
            x_center = (float(rect[0]) + float(rect[2])) / 2
            y_center = (float(rect[1]) + float(rect[3])) / 2
            if x_center < 430:
                continue
            key = min(labels, key=lambda item: abs(item[1] - y_center))[0]
            ranks[key] = int(value)
        if ranks:
            return ranks
    return {}


def _project_label_positions(page) -> list[tuple[str, float]]:
    found: dict[str, list[float]] = {
        "experimental_work": [],
        "engineering_technology_development": [],
        "programming": [],
    }

    def visitor(text, cm, tm, font_dict, font_size):
        cleaned = _clean_cell(text)
        lowered = cleaned.lower()
        y = float(tm[5])
        if "experimental work" in lowered:
            found["experimental_work"].append(y)
        elif "engineering and technology" in lowered or cleaned == "Development":
            found["engineering_technology_development"].append(y)
        elif cleaned == "Programming":
            found["programming"].append(y)

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return []

    labels = []
    for key, y_values in found.items():
        if y_values:
            labels.append((key, sum(y_values) / len(y_values)))
    return labels


def _project_ranks_from_text(text: str) -> dict[str, int]:
    project_block = _project_preference_block(text)
    ranks = _project_ranks_from_vertical_text(project_block)
    if ranks:
        return ranks

    ranks: dict[str, int] = {}
    labels = {
        "experimental_work": r"Experimental\s+Work",
        "engineering_technology_development": r"Engineering\s+and\s+Technology\s+Development",
        "programming": r"Programming",
    }
    for key, label in labels.items():
        rank = _rank_near_project_label(project_block, label)
        if rank:
            ranks[key] = rank
    if not ranks:
        ranks = _project_ranks_from_vertical_text(project_block)
    return ranks


def _project_ranks_from_vertical_text(text: str) -> dict[str, int]:
    lines = _clean_lines(text)
    label_keys = []

    def add_label(key: str) -> None:
        if not label_keys or label_keys[-1] != key:
            label_keys.append(key)

    for index, line in enumerate(lines):
        lowered = line.lower()
        if "experimental work" in lowered or (
            lowered == "work"
            and index > 0
            and "experimental" in lines[index - 1].lower()
        ):
            add_label("experimental_work")
        elif "engineering and technology" in lowered or (
            lowered == "development"
            and index > 0
            and "engineering and technology" in lines[index - 1].lower()
        ):
            add_label("engineering_technology_development")
        elif lowered == "programming":
            add_label("programming")

    if len(label_keys) < 2:
        return {}

    rank_values = []
    start_collecting = False
    for line in lines:
        lowered = line.lower()
        if lowered == "programming":
            start_collecting = True
            continue
        if rank_values and start_collecting and re.search(r"\b(?:math|science|chemistry|physics|biology|computer)\b", lowered):
            break
        if start_collecting and re.fullmatch(r"[123]", line):
            rank_values.append(int(line))

    if not rank_values:
        return {}

    keys = label_keys[-len(rank_values) :]
    return dict(zip(keys, rank_values))


def _rank_near_project_label(text: str, label_pattern: str) -> int | None:
    for match in re.finditer(label_pattern, text, re.IGNORECASE):
        window = text[max(0, match.start() - 80) : min(len(text), match.end() + 120)]
        candidates = [
            re.search(r"(?:rank|choice|preference)?\s*[:#-]?\s*\b([123])\b[\s\S]{0,50}" + label_pattern, window, re.IGNORECASE),
            re.search(label_pattern + r"[\s\S]{0,80}?(?:rank|choice|preference)?\s*[:#-]?\s*\b([123])\b", window, re.IGNORECASE),
        ]
        for candidate in candidates:
            if candidate:
                return int(candidate.group(1))
    return None


def _project_preference_block(text: str) -> str:
    start = re.search(r"Project Preference:", text, re.IGNORECASE)
    end = re.search(r"More about the Applicant:", text, re.IGNORECASE)
    if start and end and end.start() > start.start():
        return text[start.start() : end.start()]
    return text


def _project_preference_notes(ranks: dict[str, int | str]) -> str:
    if not ranks:
        return "No project preference rank was detected."
    labels = {
        "experimental_work": "Experimental Work",
        "engineering_technology_development": "Engineering and Technology Development",
        "programming": "Programming",
    }
    ordered = sorted(
        ((rank, labels[key]) for key, rank in ranks.items() if isinstance(rank, int)),
        key=lambda item: item[0],
    )
    return "; ".join(f"{label}: {rank}" for rank, label in ordered)


def _sunnybrook_form_note(
    form_text: str,
    form_courses: list[CourseGrade],
    form_current_grade: int | None,
    project_ranks: dict[str, int | str],
    stem_statement: str,
    visual_form: dict | None = None,
) -> str:
    if not form_text.strip():
        return ""

    visual_form = visual_form or {}
    notes = []
    if not _extract_name_from_form(form_text) and not str(visual_form.get("full_name", "")).strip():
        notes.append("Full name could not be read from Sunnybrook form.")
    if not _extract_current_high_school_from_form(form_text) and not str(visual_form.get("current_high_school", "")).strip():
        notes.append("Current high school could not be read from Sunnybrook form.")
    if not form_current_grade and not _int_or_none(visual_form.get("current_grade")):
        notes.append("Current grade could not be read from Sunnybrook form.")
    if _academic_grades_block(form_text) and not form_courses:
        notes.append("Academic grades could not be read from Sunnybrook form.")
    elif not _academic_grades_block(form_text):
        notes.append("Academic grades section could not be found in Sunnybrook form.")

    missing_project_ranks = _missing_project_rank_labels(project_ranks)
    if missing_project_ranks:
        notes.append(f"Project preference ranks could not be read for: {', '.join(missing_project_ranks)}.")
    if not stem_statement.strip():
        notes.append("More about the Applicant/STEM statement could not be read from Sunnybrook form.")
    return " ".join(notes)


def _missing_project_rank_labels(ranks: dict[str, int | str]) -> list[str]:
    if len([rank for rank in ranks.values() if isinstance(rank, int)]) >= 2:
        return []
    labels = {
        "experimental_work": "Experimental Work",
        "engineering_technology_development": "Engineering and Technology Development",
        "programming": "Programming",
    }
    return [label for key, label in labels.items() if not isinstance(ranks.get(key), int)]


def _infer_current_grade(text: str, courses: list[CourseGrade]) -> int | None:
    explicit = re.search(r"Current\s+Grade:?\s*_*\s*(?:Grade\s*)?([0-9]{1,2})", text, re.IGNORECASE)
    if explicit:
        return int(explicit.group(1))
    grade_mention = re.search(r"\bGrade\s+(9|1[0-2])\s+student\b", text, re.IGNORECASE)
    if grade_mention:
        return int(grade_mention.group(1))
    form_value = _current_grade_from_form_values(text)
    if form_value:
        return form_value
    if not courses:
        return None
    return max(course.grade_level for course in courses)


def _current_grade_from_form_values(text: str) -> int | None:
    lines = _clean_lines(text)
    for index, line in enumerate(lines):
        if line.lower() != "programming":
            continue
        for candidate in lines[index + 1 : index + 8]:
            if re.fullmatch(r"1[0-2]|9", candidate):
                return int(candidate)
    return None


def _classify_application_sections(text: str) -> ApplicationSections:
    form_range = _form_range(text)
    transcript_range = _transcript_range(text, form_range)
    stem_range = _stem_statement_range(text, form_range)
    ai_sections = None
    if (not form_range or not transcript_range) and llm.is_configured():
        ai_sections = _ai_split_application_sections(text)
        if ai_sections:
            if not form_range:
                form_range = ai_sections.get("form_range")
            if not transcript_range:
                transcript_range = ai_sections.get("transcript_range")
            if not stem_range:
                stem_range = ai_sections.get("stem_range")

    protected_ranges = [item for item in [form_range, transcript_range, stem_range] if item]

    form_text = _slice_range(text, form_range)
    transcript_text = _slice_range(text, transcript_range)
    stem_text = _section_stem_statement_from_form(form_text) or _slice_range(text, stem_range)
    remaining_text = _remove_ranges(text, protected_ranges)

    cover_blocks: list[str] = []
    resume_blocks: list[str] = []
    unknown_blocks: list[str] = []

    marker_cover, marker_resume = _split_cover_resume_by_markers(remaining_text)
    if marker_cover:
        cover_blocks.append(marker_cover)
    if marker_resume:
        resume_blocks.append(marker_resume)
    if marker_cover or marker_resume:
        consumed_ranges = []
        if marker_cover:
            consumed_ranges.append(_text_range_for_substring(remaining_text, marker_cover))
        if marker_resume:
            consumed_ranges.append(_text_range_for_substring(remaining_text, marker_resume))
        remaining_for_blocks = _remove_ranges(remaining_text, [item for item in consumed_ranges if item])
    else:
        remaining_for_blocks = remaining_text

    for block in _split_candidate_blocks(remaining_for_blocks):
        cover_part, rest_part = _split_cover_letter_from_following_material(block)
        if cover_part:
            cover_blocks.append(cover_part)
            block = rest_part
            if not block.strip():
                continue

        kind = _classify_candidate_block(block)
        if kind == "cover_letter":
            cover_blocks.append(block)
        elif kind == "resume":
            resume_blocks.append(block)
        else:
            unknown_blocks.append(block)

    if not cover_blocks and unknown_blocks:
        best_cover = max(unknown_blocks, key=_cover_letter_score)
        if _cover_letter_score(best_cover) >= 3:
            cover_blocks.append(best_cover)
            unknown_blocks.remove(best_cover)

    if not resume_blocks and unknown_blocks:
        best_resume = max(unknown_blocks, key=_resume_block_score)
        if _resume_block_score(best_resume) >= 3:
            resume_blocks.append(best_resume)
            unknown_blocks.remove(best_resume)

    if (not cover_blocks or not resume_blocks) and llm.is_configured():
        if ai_sections is None:
            ai_sections = _ai_split_application_sections(text)
        if ai_sections:
            if not cover_blocks:
                ai_cover = _slice_range(text, ai_sections.get("cover_range"))
                if ai_cover and _cover_letter_score(ai_cover) >= 2:
                    cover_blocks.append(ai_cover)
            if not resume_blocks:
                ai_resume = _slice_range(text, ai_sections.get("resume_range"))
                if ai_resume and _resume_block_score(ai_resume) >= 2:
                    resume_blocks.append(ai_resume)

    warnings = []
    if not form_text.strip():
        warnings.append("Sunnybrook application form was not clearly detected")
    if not transcript_text.strip():
        warnings.append("Transcript section was not clearly detected")
    if not cover_blocks:
        warnings.append("Cover letter section was not confidently detected")
    if not resume_blocks:
        warnings.append("Resume/CV section was not confidently detected")

    return ApplicationSections(
        cover_letter="\n\n".join(cover_blocks).strip(),
        resume_text="\n\n".join(resume_blocks).strip(),
        form_text=form_text.strip(),
        stem_statement=stem_text.strip(),
        transcript_text=transcript_text.strip(),
        warnings=warnings,
    )


def _split_cover_resume_by_markers(text: str) -> tuple[str, str]:
    resume_start = _resume_start_pos(text)
    if resume_start is None:
        return "", ""

    cover_candidate = text[:resume_start].strip()
    resume_candidate = text[resume_start:].strip()
    cover = cover_candidate if _cover_letter_score(cover_candidate) >= 3 else ""
    resume = resume_candidate if _resume_block_score(resume_candidate) >= 3 else ""
    return cover, resume


def _resume_start_pos(text: str) -> int | None:
    markers = [
        r"(?m)^\s*(?:Resume|Curriculum\s+Vitae|CV)\s*$",
        r"(?m)^\s*High\s+School\s+Diploma:",
        r"(?m)^\s*Profile\s*:?\s*$",
        r"(?m)^\s*Education\s*:?\s*$",
        r"(?m)^\s*Relevant\s+Experience\s*/?\s*Skills\s*:?\s*$",
        r"(?m)^\s*(?:Work|Volunteer|Technical|Professional)\s+Experience\s*:?\s*$",
    ]
    candidates = []
    for pattern in markers:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            candidate = text[match.start() :]
            if _resume_block_score(candidate) >= 3:
                candidates.append(match.start())
    return min(candidates) if candidates else None


def _text_range_for_substring(text: str, value: str) -> tuple[int, int] | None:
    if not value:
        return None
    start = text.find(value)
    if start < 0:
        return None
    return (start, start + len(value))


def _split_cover_letter_from_following_material(block: str) -> tuple[str, str]:
    if not re.search(r"\bSincerely\b", block, re.IGNORECASE):
        return "", block

    match = re.search(
        r"\bSincerely,?\s+(?:[A-Z][A-Za-z'-]+\s+){1,3}(?=(?:[A-Z][A-Za-z'-]+\s+){1,3}\s*(?:\d{3}|[•@])|\s*(?:Resume|Education|Work Experience|Volunteer Experience|Technical Experience|Professional Experience|Personal Profile|Profile)\s*:?\b|[A-Z][A-Z .'-]{5,}\b)",
        block,
        re.IGNORECASE,
    )
    if not match:
        return "", block
    cover_part = block[: match.end()].strip()
    if _cover_letter_score(cover_part) < 3:
        return "", block
    return cover_part, block[match.end() :].strip()


def _ai_split_application_sections(text: str) -> dict[str, tuple[int, int] | None] | None:
    numbered_lines = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        cleaned = _clean_cell(line)
        if cleaned:
            numbered_lines.append(f"{index}: {cleaned}")
    if not numbered_lines:
        return None

    prompt = (
        "Split this application text into sections for a high school research program application.\n"
        "Use semantic evidence, not fixed opening phrases.\n"
        "- cover_letter: prose addressed to the program, usually includes interest/fit and a closing.\n"
        "- resume: structured profile/CV with education, skills, experience, awards, dates, bullets, or certifications.\n"
        "- sunnybrook_form: Sunnybrook Focused Ultrasound Lab Summer Program form, including student info, project preferences, grades, and More about the Applicant.\n"
        "- transcript: official transcript/report card course records from school or Ministry of Education.\n"
        "- stem_statement: applicant answer to More about the Applicant, only if it can be isolated.\n"
        "Return JSON only with integer 1-based inclusive line ranges or null:\n"
        "{\"cover_letter_start\": number|null, \"cover_letter_end\": number|null, "
        "\"resume_start\": number|null, \"resume_end\": number|null, "
        "\"sunnybrook_form_start\": number|null, \"sunnybrook_form_end\": number|null, "
        "\"transcript_start\": number|null, \"transcript_end\": number|null, "
        "\"stem_statement_start\": number|null, \"stem_statement_end\": number|null}\n\n"
        "Lines:\n"
        f"{chr(10).join(numbered_lines[:360])}"
    )

    try:
        raw = llm.complete(prompt, max_tokens=180, temperature=0)
        data = _parse_json_object(raw)
        return {
            "cover_range": _line_range(lines, data.get("cover_letter_start"), data.get("cover_letter_end")),
            "resume_range": _line_range(lines, data.get("resume_start"), data.get("resume_end")),
            "form_range": _line_range(lines, data.get("sunnybrook_form_start"), data.get("sunnybrook_form_end")),
            "transcript_range": _line_range(lines, data.get("transcript_start"), data.get("transcript_end")),
            "stem_range": _line_range(lines, data.get("stem_statement_start"), data.get("stem_statement_end")),
        }
    except Exception:
        return None


def _line_range(lines: list[str], start: object, end: object) -> tuple[int, int] | None:
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    if start < 1 or end < start:
        return None
    line_starts = []
    cursor = 0
    for line in lines:
        line_starts.append(cursor)
        cursor += len(line) + 1
    if start > len(lines):
        return None
    range_start = line_starts[start - 1]
    range_end = line_starts[min(end, len(lines)) - 1] + len(lines[min(end, len(lines)) - 1])
    return (range_start, range_end)


def _form_range(text: str) -> tuple[int, int] | None:
    start = re.search(r"Sunnybrook\s+Focused\s+Ultrasound\s+Lab\s+Summer\s+Program", text, re.IGNORECASE)
    if not start:
        return None

    boundary = _first_match_after(
        text,
        start.end(),
        [
            r"Ministry\s+of\s+Education",
            r"ONTARIO\s+STUDENT\s+TRANSCRIPT",
            r"STUDENT\s+TRANSCRIP",
            r"(?m)^\s*(?:Resume|Curriculum\s+Vitae|CV)\s*$",
            r"(?m)^\s*Cover\s+Letter\s*$",
            r"(?m)^\s*High\s+School\s+Diploma:",
            r"(?m)^\s*Profile\s*:?\s*$",
            r"(?m)^\s*Education\s*:?\s*$",
            r"(?m)^\s*Dear\s+",
            r"(?m)^\s*To\s+Whom\s+it\s+May\s+Concern",
        ],
    )
    return (start.start(), boundary.start() if boundary else len(text))


def _transcript_range(text: str, form_range: tuple[int, int] | None) -> tuple[int, int] | None:
    start = re.search(
        r"Ministry\s+of\s+Education|ONTARIO\s+STUDENT\s+TRANSCRIPT|STUDENT\s+TRANSCRIP",
        text,
        re.IGNORECASE,
    )
    if not start:
        return None

    boundaries = [
        r"Sunnybrook\s+Focused\s+Ultrasound\s+Lab\s+Summer\s+Program",
        r"(?m)^\s*(?:Resume|Curriculum\s+Vitae|CV)\s*$",
        r"(?m)^\s*Cover\s+Letter\s*$",
        r"(?m)^\s*High\s+School\s+Diploma:",
        r"(?m)^\s*Profile\s*:?\s*$",
        r"(?m)^\s*Education\s*:?\s*$",
        r"(?m)^\s*Dear\s+",
        r"(?m)^\s*To\s+Whom\s+it\s+May\s+Concern",
    ]
    boundary = _first_match_after(text, start.end(), boundaries)
    end = boundary.start() if boundary else len(text)
    if form_range and form_range[0] > start.start():
        end = min(end, form_range[0])
    return (start.start(), end)


def _stem_statement_range(text: str, form_range: tuple[int, int] | None) -> tuple[int, int] | None:
    start = re.search(r"More\s+about\s+the\s+applicant:", text, re.IGNORECASE)
    if not start:
        return None
    boundary = _first_match_after(
        text,
        start.end(),
        [
            r"Ministry\s+of\s+Education",
            r"ONTARIO\s+STUDENT\s+TRANSCRIPT",
            r"STUDENT\s+TRANSCRIP",
            r"(?m)^\s*(?:Resume|Curriculum\s+Vitae|CV)\s*$",
            r"(?m)^\s*Cover\s+Letter\s*$",
            r"(?m)^\s*High\s+School\s+Diploma:",
            r"(?m)^\s*Profile\s*:?\s*$",
            r"(?m)^\s*Education\s*:?\s*$",
            r"(?m)^\s*Dear\s+",
            r"(?m)^\s*To\s+Whom\s+it\s+May\s+Concern",
        ],
    )
    end = boundary.start() if boundary else len(text)
    if form_range and form_range[0] <= start.start() < form_range[1]:
        return None
    return (start.start(), end)


def _first_match_after(text: str, offset: int, patterns: list[str]) -> TextMatch | None:
    matches = []
    for pattern in patterns:
        match = re.search(pattern, text[offset:], re.IGNORECASE)
        if match:
            matches.append(TextMatch(offset + match.start(), offset + match.end()))
    if not matches:
        return None
    return min(matches, key=lambda item: item.start())


def _slice_range(text: str, text_range: tuple[int, int] | None) -> str:
    if not text_range:
        return ""
    start, end = text_range
    return text[start:end]


def _remove_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    if not ranges:
        return text
    pieces = []
    cursor = 0
    for start, end in sorted(ranges):
        if start > cursor:
            pieces.append(text[cursor:start])
        cursor = max(cursor, end)
    if cursor < len(text):
        pieces.append(text[cursor:])
    return "\n\n".join(piece.strip() for piece in pieces if piece.strip())


def _split_candidate_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if current and _starts_new_candidate_block(line):
            blocks.append(current)
            current = []
        current.append(line)

    if current:
        blocks.append(current)

    return ["\n".join(block).strip() for block in blocks if "\n".join(block).strip()]


def _starts_new_candidate_block(line: str) -> bool:
    cleaned = _clean_cell(line)
    if not cleaned:
        return False
    return bool(
        re.search(r"^Dear\b", cleaned, re.IGNORECASE)
        or re.search(r"^To\s+Whom\s+it\s+May\s+Concern\b", cleaned, re.IGNORECASE)
        or re.search(r"^(Resume|Curriculum\s+Vitae|CV|Cover\s+Letter)$", cleaned, re.IGNORECASE)
        or re.search(
            r"^(Profile|Education|Work Experience|Volunteer Experience|Technical Experience|Professional Experience|Extracurriculars?|Skills|Awards|Certifications?)\s*:?$",
            cleaned,
            re.IGNORECASE,
        )
        or re.search(r"^High\s+School\s+Diploma:", cleaned, re.IGNORECASE)
    )


def _classify_candidate_block(block: str) -> str:
    cover_score = _cover_letter_score(block)
    resume_score = _resume_block_score(block)
    if cover_score >= 4 and cover_score > resume_score:
        return "cover_letter"
    if resume_score >= 3 and resume_score >= cover_score:
        return "resume"
    return "unknown"


def _cover_letter_score(text: str) -> int:
    lines = _clean_lines(text)
    paragraphish = len([line for line in lines if len(line.split()) >= 12])
    score = 0
    if re.search(r"\bDear\b|\bTo\s+Whom\s+it\s+May\s+Concern\b", text, re.IGNORECASE):
        score += 3
    if _has_any(text, ["sincerely", "regards", "thank you"]):
        score += 2
    if _has_any(text, ["RE:", "to whom it may concern", "wanted to contact you", "formal interview"]):
        score += 1
    if paragraphish >= 3:
        score += 2
    if _has_any(text, ["High School Diploma", "Skills", "Work Experience", "ONTARIO STUDENT TRANSCRIPT"]):
        score -= 2
    return score


def _resume_block_score(text: str) -> int:
    lines = _clean_lines(text)
    bulletish = len([line for line in lines if _is_resume_bullet_line(line)])
    heading_count = len(
        [
            line
            for line in lines
            if re.search(
                r"^(Education|Work Experience|Volunteer Experience|Technical Experience|Professional Experience|Extracurriculars?|Skills|Awards|Certifications?)$",
                line,
                re.IGNORECASE,
            )
        ]
    )
    score = 0
    if heading_count:
        score += min(heading_count, 3)
    if _has_any(text, ["High School Diploma", "Education", "Work Experience", "Employment", "Volunteer Experience"]):
        score += 3
    if _has_any(text, ["Skills", "Awards", "Accomplishments", "Certifications", "Projects"]):
        score += 2
    if re.search(
        r"\b(?:\d{2}/\d{4}|20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\w\s,./-]{0,30}(?:Current|Present|20\d{2})\b",
        text,
        re.IGNORECASE,
    ):
        score += 2
    if bulletish >= 3:
        score += 1
    if re.search(r"\bDear\b", text, re.IGNORECASE):
        score -= 2
    return score


def _section_stem_statement_from_form(text: str) -> str:
    start = re.search(r"More\s+about\s+the\s+Applicant:", text, re.IGNORECASE)
    if not start:
        return ""
    end = _first_match_after(
        text,
        start.end(),
        [
            r"Ministry\s+of\s+Education",
            r"ONTARIO\s+STUDENT\s+TRANSCRIPT",
            r"(?m)^\s*Academic\s+Grades:",
        ],
    )
    return text[start.start() : end.start()].strip() if end else text[start.start() :].strip()


def _section_before_resume(text: str) -> str:
    marker = re.search(r"High School Diploma:", text, re.IGNORECASE)
    return text[: marker.start()] if marker else text[:2000]


def _section_resume(text: str) -> str:
    start = re.search(r"High School Diploma:", text, re.IGNORECASE)
    end = re.search(r"Sunnybrook Focused Ultrasound Lab Summer Program", text, re.IGNORECASE)
    if start and end and end.start() > start.start():
        return text[start.start() : end.start()]
    return text


def _section_stem_statement(text: str) -> str:
    start = re.search(r"More about the Applicant:", text, re.IGNORECASE)
    end = re.search(r"Ministry of Education|ONTARIO STUDENT TRANSCRIPT", text, re.IGNORECASE)
    if start and end and end.start() > start.start():
        return text[start.start() : end.start()]
    return ""


def _technical_experience(text: str) -> list[str]:
    items = []
    for line in _clean_lines(text):
        line = _clean_resume_feature_line(line)
        if _is_generic_resume_summary(line):
            continue
        if _is_stem_relevant_resume_line(line):
            items.append(line)
    return _dedupe(items)[:12]


def _is_stem_relevant_resume_line(line: str) -> bool:
    lowered = line.lower()
    if len(line.split()) < 2:
        return False

    patterns = [
        r"\b(programming|coding|python|javascript|java|robotics|software|hardware|computer|logic-based|applications?)\b",
        r"\b(research|research papers?|science fair|laboratory|lab)\b",
        r"\b(hospital|health|healthcare|medical|medicine|patient|pediatrics|clinical|first aid|cpr|aed|lifesaving)\b",
        r"\b(biology|chemistry|physics|engineering|mathematics|math|stem|shsm)\b",
        r"\b(tutor|peer tutor|certification|certificate|honou?r roll|award)\b",
    ]
    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
        return True

    return _looks_like_stem_role_or_project(line)


def _looks_like_stem_role_or_project(line: str) -> bool:
    return bool(
        re.search(r"\b(volunteer|assistant|intern|coach|helper|project|paper|specialization)\b", line, re.IGNORECASE)
        and re.search(r"\b(hospital|health|science|technology|research|computer|robotics|medical)\b", line, re.IGNORECASE)
    )


def _is_long_narrative_line(line: str) -> bool:
    words = line.split()
    if len(words) < 35:
        return False
    narrative_markers = ["i ", " my ", " me ", " aspire", " motivation", " candidate", " future"]
    lowered = f" {line.lower()} "
    return any(marker in lowered for marker in narrative_markers)


def _is_generic_resume_summary(line: str) -> bool:
    lowered = line.lower()
    generic_starts = [
        "motivated individual",
        "detail-oriented professional",
        "offering solid foundation",
    ]
    return any(lowered.startswith(start) for start in generic_starts)


def _technical_skills(text: str) -> list[str]:
    skills = []
    for line in _clean_lines(text):
        skills.extend(_technical_skills_from_line(line))
    return _dedupe(skills)[:16]


def _resume_feature_summary(resume_text: str, stem_statement: str) -> dict[str, str]:
    ai_result = _ai_resume_feature_summary(resume_text, stem_statement)
    if ai_result:
        return ai_result
    return _fallback_resume_feature_summary(resume_text)


def _ai_resume_feature_summary(resume_text: str, stem_statement: str) -> dict[str, str] | None:
    if not llm.is_configured():
        return None

    try:
        message = llm.complete(
            max_tokens=500,
            temperature=0,
            prompt=(
                        "Extract and summarize STEM-relevant features from this high school applicant's resume.\n"
                        "Focus on concrete evidence of what they did, not isolated keywords. Include programming, engineering, robotics, research, lab/science, healthcare/clinical, hospital/patient-facing work, STEM tutoring, certifications, projects, and STEM-related leadership if present.\n"
                        "Do not invent details. Do not use generic labels like 'Health & Wellness' unless you explain the actual activity or specialization.\n"
                        "Return JSON only with keys:\n"
                        "- experience: 1-3 concise sentences summarizing concrete STEM-relevant experiences/actions.\n"
                        "- skills: concise comma-separated concrete skills/tools/domains, each grounded in the resume.\n"
                        "If little evidence exists, say that directly.\n\n"
                        f"Resume:\n{resume_text[:4500]}\n\n"
                        f"Personal statement context, only if useful:\n{stem_statement[:1200]}"
            ),
        )
        raw = message.strip()
        data = _parse_json_object(raw)
        experience = _clean_cell(str(data.get("experience", "")))
        skills = _clean_cell(str(data.get("skills", "")))
        if not experience and not skills:
            return None
        return {
            "experience": experience or "Limited concrete STEM-related resume experience found.",
            "skills": _filter_feature_skill_summary(skills) or "Limited concrete STEM-related skills found.",
        }
    except Exception:
        return None


def _fallback_resume_feature_summary(resume_text: str) -> dict[str, str]:
    experience_lines = _technical_experience(resume_text)
    skills = _technical_skills(resume_text)

    experience = _limit_words(_summarize_resume_evidence_lines(experience_lines), 100)
    skill_summary = _summarize_resume_skills(skills, experience_lines)
    skill_summary = _limit_words(skill_summary, 100)

    return {
        "experience": experience or "Limited concrete STEM-related resume experience found.",
        "skills": skill_summary or "Limited concrete STEM-related skills found.",
    }


def _summarize_resume_evidence_lines(lines: list[str]) -> str:
    if not lines:
        return ""

    normalized = " ".join(_clean_resume_feature_line(line) for line in lines)
    evidence = []

    physics_role = _phrase_if(
        normalized,
        r"Physics Club.*?Astronomy Executive",
        "Physics Club Astronomy Executive teaching astronomy and physics concepts, creating explanatory materials, and leading discussions."
    )
    if physics_role:
        evidence.append(physics_role)

    macs = _phrase_if(
        normalized,
        r"\bMaCS\b|Mathematics and Computer Science",
        "MaCS student with enriched mathematics, science, and computer science preparation."
    )
    if macs:
        evidence.append(macs)

    if re.search(r"\bAir Cadets?\b|aviation", normalized, re.IGNORECASE):
        evidence.append("Air Cadets experience includes aviation instruction, structured leadership, field training, and teamwork.")

    if re.search(r"\b(programming|python|javascript|logic-based applications|robotics)\b", normalized, re.IGNORECASE):
        evidence.append("Programming/technology experience includes " + _short_skill_context(normalized, ["Programming", "Python", "JavaScript", "logic-based applications", "robotics"]) + ".")

    if re.search(r"\b(research paper|research papers|conducted .*research|bacterial evolution|genomics)\b", normalized, re.IGNORECASE):
        evidence.append("Research experience includes " + _short_skill_context(normalized, ["research papers", "bacterial evolution research", "genomics research", "data analysis"]) + ".")

    if re.search(r"\b(hospital|pediatrics|patient|healthcare|first aid|CPR|AED|lifesaving)\b", normalized, re.IGNORECASE):
        evidence.append("Healthcare exposure includes " + _short_skill_context(normalized, ["hospital", "pediatrics", "patient interactions", "First Aid", "CPR", "AED", "lifesaving"]) + ".")

    if not evidence:
        evidence = [_strip_dates(line) for line in lines[:3]]

    return " ".join(_dedupe(evidence)[:4])


def _summarize_resume_skills(skills: list[str], evidence_lines: list[str]) -> str:
    concrete = []
    for skill in skills:
        if skill not in {"Health & Wellness", "SHSM", "STEM", "biology", "chemistry", "physics", "math", "mathematics"}:
            concrete.append(skill)
    if concrete:
        return ", ".join(_dedupe(concrete)[:14])

    evidence_based = []
    joined = " ".join(evidence_lines).lower()
    if "hospital" in joined or "patient" in joined:
        evidence_based.append("patient-facing healthcare exposure")
    if "research" in joined:
        evidence_based.append("research exposure")
    if "programming" in joined:
        evidence_based.append("programming exposure")
    return ", ".join(evidence_based)


def _filter_feature_skill_summary(summary: str) -> str:
    excluded = {"biology", "chemistry", "physics", "math", "mathematics"}
    parts = [_clean_cell(part) for part in re.split(r",|;", summary)]
    filtered = [part for part in parts if part and part.lower() not in excluded]
    return ", ".join(_dedupe(filtered))


def _phrase_if(text: str, pattern: str, phrase: str) -> str:
    return phrase if re.search(pattern, text, re.IGNORECASE) else ""


def _short_skill_context(text: str, terms: list[str]) -> str:
    found = []
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            found.append(term)
    return ", ".join(_dedupe(found)[:5]) or "relevant STEM work"


def _strip_dates(text: str) -> str:
    text = re.sub(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z.]*\s+\d{4}\s*(?:[-–]\s*(?:Present|Current|\d{4}))?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{1,2}/\d{4}\s*[-–]\s*(?:Present|Current|\d{1,2}/\d{4})", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b20\d{2}\s*[-–]\s*(?:20\d{2}|Present|Current)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b20\d{2}\b", "", text)
    return _clean_cell(text)


def _limit_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(" ,;:") + "."


def _technical_skills_from_line(line: str) -> list[str]:
    skills = []
    lowered = line.lower()

    explicit_terms = {
        "python": "Python",
        "javascript": "JavaScript",
        "java": "Java",
        "robotics": "robotics",
        "programming": "programming",
        "coding": "coding",
        "logic-based applications": "logic-based applications",
        "research papers": "research papers",
        "research": "research",
        "microsoft office": "Microsoft Office",
        "google workspace": "Google Workspace",
        "first aid": "First Aid",
        "cpr": "CPR",
        "aed": "AED",
        "health & wellness": "Health & Wellness",
        "health and wellness": "Health & Wellness",
        "healthcare": "healthcare",
        "hospital": "hospital volunteering",
        "patient": "patient support",
        "pediatrics": "pediatrics",
        "lifesaving": "lifesaving certification",
        "engineering": "engineering",
        "computer science": "computer science",
        "computer information science": "computer information science",
        "computer engineering": "computer engineering",
        "stem": "STEM",
        "shsm": "SHSM",
        "ocra": "OCRA certification",
    }
    for term, label in explicit_terms.items():
        if _contains_skill_phrase(lowered, term):
            skills.append(label)

    language_match = re.search(r"\bProgramming:\s*([A-Za-z0-9+#, ./-]+)", line, re.IGNORECASE)
    if language_match:
        for item in re.split(r",|/", language_match.group(1)):
            cleaned = _clean_cell(item)
            if cleaned:
                skills.append(cleaned)

    return skills


def _contains_skill_phrase(lowered_line: str, term: str) -> bool:
    if re.search(r"^\w|\w$", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", lowered_line, re.IGNORECASE))
    return term in lowered_line


def _clean_resume_feature_line(line: str) -> str:
    return _clean_cell(re.sub(r"[\ue000-\uf8ff]+", " ", line))


def _experimental_experience(text: str) -> list[str]:
    lines = []
    for line in _clean_lines(text):
        lowered = line.lower()
        if "focused ultrasound lab" in lowered or "application deadline" in lowered:
            continue
        if re.search(r"\b(biology|chemistry|physics|lab|laboratory|experimental|bench|animal)\b", line, re.IGNORECASE):
            lines.append(line)
    return _dedupe(lines)[:8]


def _engineering_experience(text: str) -> list[str]:
    lines = []
    for line in _clean_lines(text):
        if re.search(r"\b(engineering|electronics|hardware|software|computer|programming|robotics|design)\b", line, re.IGNORECASE):
            lines.append(line)
    return _dedupe(lines)[:8]


def _programming_skills(text: str) -> list[str]:
    skills = []
    for term in ["Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "MATLAB", "R", "HTML", "CSS", "programming", "coding"]:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            skills.append(term)
    return _dedupe(skills)


def _programming_summary(skills: list[str]) -> str:
    if not skills:
        return "No clear programming skills found in the submitted application."
    return f"Programming evidence found: {', '.join(skills)}."


def _rate_cover_letter(text: str, fus_mentions: int) -> int:
    return _evaluate_cover_letter(text, fus_mentions)["score"]


def _cover_letter_notes(text: str, fus_mentions: int) -> str:
    return _evaluate_cover_letter(text, fus_mentions)["notes"]


def _evaluate_cover_letter(text: str, fus_mentions: int) -> dict:
    if not text.strip():
        return {"score": "", "notes": ""}

    ai_result = _ai_evaluate_cover_letter(text)
    if ai_result is not None:
        return ai_result

    scorecard = _cover_letter_scorecard(text, fus_mentions)
    strengths = "; ".join(scorecard["strengths"]) or "No major rubric strengths detected."
    gaps = "; ".join(scorecard["gaps"]) or "No major rubric gaps detected."
    return {
        "score": scorecard["score"],
        "notes": f"Fallback rubric scoring. Strengths: {strengths}. Gaps: {gaps}.",
    }


def _ai_evaluate_cover_letter(text: str) -> dict | None:
    if not llm.is_configured():
        return None

    try:
        message = llm.complete(
            max_tokens=700,
            temperature=0,
            prompt=(
                        "Evaluate this cover letter for a Focused Ultrasound Lab high school research program.\n"
                        "Keep these criteria: strong opening explaining why they want the role; relevant skills/experience; concrete accomplishments; quantified impact; call to action; formal closing; professional brief format with contact information; addressed to a named person; personalization to the organization/program; and FUS lab relevance.\n\n"
                        "Additional strict restriction:\n"
                        "- Merely naming Sunnybrook, FUS, Focused Ultrasound, or the program is not enough for a high score.\n"
                        "- To score 8-10, the letter must show some understanding of what the FUS lab does, such as focused ultrasound research, non-invasive therapy/treatment, biomedical imaging, device/technology development, brain or cancer applications, experimental work, or other specific lab-relevant work.\n"
                        "- If it mentions the program but does not show what the FUS lab does, the maximum score is 7.\n"
                        "- If it does not reference the FUS lab/program at all, the maximum score is 6.\n\n"
                        "Return JSON only with keys: score, notes. score must be an integer 0-10. notes must be one concise sentence explaining the score and whether FUS understanding is present.\n\n"
                        f"Cover letter:\n{text[:5000]}"
            ),
        )
        raw = message.strip()
        data = _parse_json_object(raw)
        score = int(data.get("score", 0))
        notes = str(data.get("notes", "")).strip()
        if not 0 <= score <= 10 or not notes:
            return None
        return {"score": score, "notes": f"AI rubric scoring. {notes}"}
    except Exception:
        return None


def _cover_letter_scorecard(text: str, fus_mentions: int) -> dict:
    clean_text = _clean_cell(text)
    if not clean_text:
        return {"score": 0, "strengths": [], "gaps": ["cover letter not detected"]}

    strengths = []
    gaps = []
    score = 0

    if _has_any(text, ["excited", "interested", "passion", "opportunity", "wanted to contact you"]):
        score += 1
        strengths.append("opening shows interest in the opportunity")
    else:
        gaps.append("opening does not strongly explain why they want the role")

    if _has_any(text, ["skills", "experience", "teamwork", "communication", "problem-solving", "time management"]):
        score += 1
        strengths.append("body highlights relevant skills or experience")
    else:
        gaps.append("body does not clearly highlight relevant skills or experience")

    if _has_any(text, ["contributed", "developed", "achieve", "accomplishment", "improved", "helped"]):
        score += 1
        strengths.append("includes examples or accomplishments")
    else:
        gaps.append("limited concrete accomplishments")

    if _has_quantified_impact(text):
        score += 1
        strengths.append("quantifies impact with numbers")
    else:
        gaps.append("does not quantify impact")

    if _has_any(text, ["interview", "discuss", "look forward to hearing", "contact me"]):
        score += 1
        strengths.append("closing includes a call to action")
    else:
        gaps.append("closing lacks a clear call to action")

    if _has_any(text, ["sincerely", "regards", "thank you"]):
        score += 1
        strengths.append("uses a formal closing")
    else:
        gaps.append("formal closing not detected")

    if _looks_professional_cover_letter(text):
        score += 1
        strengths.append("professional brief format with contact information")
    else:
        gaps.append("format/contact information may be incomplete or too long")

    if re.search(r"\bDear\s+(Mr\.|Ms\.|Mrs\.|Dr\.)?\s*[A-Z][A-Za-z]+", text):
        score += 1
        strengths.append("addresses the reader by name")
    else:
        gaps.append("does not address a named reader")

    if _has_any(text, ["Sunnybrook", "Focused Ultrasound", "FUS", "research program"]):
        score += 1
        strengths.append("personalized to the program or organization")
    else:
        gaps.append("limited personalization to the program")

    has_program_reference = _has_any(text, ["Sunnybrook", "Focused Ultrasound", "FUS", "research program"])
    has_fus_understanding = _shows_fus_lab_understanding(text)

    if has_fus_understanding:
        score += 1
        strengths.append("references the FUS lab and shows some understanding of its work")
    else:
        gaps.append("does not clearly show understanding of what the FUS lab does")

    score = min(score, 10)
    if has_program_reference and not has_fus_understanding:
        score = min(score, 7)
    elif not has_program_reference:
        score = min(score, 6)

    return {"score": score, "strengths": strengths, "gaps": gaps}


def _looks_professional_cover_letter(text: str) -> bool:
    lines = _clean_lines(text)
    paragraphish = len([line for line in lines if len(line) > 80])
    has_contact = bool(_extract_email(text)) or bool(re.search(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", text))
    not_too_long = len(text) < 4500 and paragraphish <= 8
    return has_contact and not_too_long


def _has_quantified_impact(text: str) -> bool:
    impact_pattern = (
        r"\b\d+\b\s+"
        r"(students|people|residents|patients|projects|events|hours|weeks|months|years|members|participants)"
    )
    return bool(re.search(impact_pattern, text, re.IGNORECASE))


def _shows_fus_lab_understanding(text: str) -> bool:
    return bool(_fus_relevant_concepts(text))


def _evaluate_fus_understanding(text: str) -> dict:
    mentioned = _keyword_count(text, ["focused ultrasound", "fus", "ultrasound"]) > 0
    if not mentioned:
        return {
            "mentioned": False,
            "summary": "Focused ultrasound/FUS is not clearly mentioned by the applicant.",
            "rating": 0,
        }

    concepts = _fus_relevant_concepts(text)
    if not concepts:
        return {
            "mentioned": True,
            "summary": "Applicant mentions FUS/focused ultrasound or the program, but does not explain their understanding of what the FUS lab does.",
            "rating": 1,
        }

    rating = min(5, len(concepts) + 1)
    return {
        "mentioned": True,
        "summary": f"Applicant mentions FUS/focused ultrasound and uses {len(concepts)} relevant concept category/categories: {', '.join(concepts)}.",
        "rating": rating,
    }


def _fus_relevant_concepts(text: str) -> list[str]:
    if _keyword_count(text, ["focused ultrasound", "fus", "ultrasound"]) == 0:
        return []

    lowered = text.lower()
    concept_patterns = [
        ("non-invasive therapy/treatment", [r"non[- ]?invasive", r"\btherapy\b", r"\btreatment\b", r"\bablation\b", r"\bsonodynamic\b"]),
        ("imaging/guidance", [r"\bimaging\b", r"\bmri\b", r"ultrasound-guided", r"\bguided\b"]),
        ("biomedical/medical application", [r"\bbiomedical\b", r"\bmedical\b", r"\bclinical\b", r"clinical application", r"\bhealthcare\b"]),
        ("device/technology development", [r"\bdevice\b", r"technology development", r"\btransducer\b", r"\bengineering\b"]),
        ("acoustics/sonication", [r"\bacoustic", r"\bsonication\b", r"\bsonodynamic\b", r"\bsound waves?\b"]),
        ("brain/neuroscience application", [r"\bbrain\b", r"\bneuro", r"blood[- ]brain barrier", r"\bneurostimulation\b"]),
        ("cancer/tumor application", [r"\bcancer\b", r"\btumou?r\b", r"\boncology\b"]),
        ("drug delivery/nanomedicine", [r"drug delivery", r"\bnanoparticles?\b", r"\bmicrobubbles?\b"]),
        ("preclinical/experimental research", [r"\bpreclinical\b", r"\bexperimental\b", r"\bresearch\b", r"\blab(?:oratory)?\b"]),
    ]

    concepts = []
    for label, patterns in concept_patterns:
        if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in patterns):
            concepts.append(label)
    return concepts


def _rate_resume(text: str, experiences: list[str], skills: list[str]) -> int:
    return _resume_scorecard(text, experiences, skills)["score"]


def _resume_notes(text: str) -> str:
    scorecard = _resume_scorecard(text, _technical_experience(text), _technical_skills(text))
    if not text.strip():
        return "Resume section was not clearly detected."
    strengths = "; ".join(scorecard["strengths"]) or "No major rubric strengths detected."
    gaps = "; ".join(scorecard["gaps"]) or "No major rubric gaps detected."
    return f"Strengths: {strengths}. Gaps: {gaps}."


def _resume_scorecard(text: str, experiences: list[str], skills: list[str]) -> dict:
    clean_text = _clean_cell(text)
    if not clean_text:
        return {"score": 0, "strengths": [], "gaps": ["resume not detected"]}

    strengths = []
    gaps = []
    score = 0

    experience_score = _resume_experience_score(text)
    score += experience_score
    if experience_score == 3:
        strengths.append("includes work/volunteering experience with useful detail and FUS/lab relevance")
    elif experience_score in (1, 2):
        gaps.append("work/volunteering experience is present but limited, weakly detailed, or lacks FUS/lab relevance")
    else:
        gaps.append("relevant work/volunteering experience not clearly listed")

    education_score = _resume_education_score(text)
    score += education_score
    if education_score == 1:
        strengths.append("education is clearly listed")
    else:
        gaps.append("education section not clearly listed")

    skills_score = _resume_skills_score(text, skills)
    score += skills_score
    if skills_score == 2:
        strengths.append("skills are relevant and clearly listed")
    elif skills_score == 1:
        gaps.append("skills are present but generic or weakly connected to the program")
    else:
        gaps.append("skills section not clearly listed")

    awards_score = _resume_awards_score(text)
    score += awards_score
    if awards_score == 1:
        strengths.append("includes relevant awards, accomplishments, or certifications")
    else:
        gaps.append("awards/accomplishments not clearly listed")

    format_score = _resume_format_score(text)
    score += format_score
    if format_score == 3:
        strengths.append("plain, simple, and likely concise")
    elif format_score == 2:
        gaps.append("format is acceptable but could be cleaner or more concise")
    else:
        gaps.append("resume format is weak or could be significantly condensed")

    return {"score": min(score, 10), "strengths": strengths, "gaps": gaps}


def _resume_experience_score(text: str) -> int:
    has_experience = _has_any(text, ["volunteer", "work experience", "employment", "tutor", "intern", "assistant"])
    if not has_experience:
        return 0

    score = 1
    quality = _has_any(text, ["developed", "facilitated", "assisted", "organized", "collaborated", "supported", "helped", "promoted"])
    quantified = _has_quantified_impact(text)
    if quality or quantified:
        score += 1
    if _resume_experience_has_fus_relevance(text):
        score += 1
    return score


def _resume_experience_has_fus_relevance(text: str) -> bool:
    return _shows_fus_lab_understanding(text) or _has_any(
        text,
        [
            "focused ultrasound",
            "ultrasound",
            "biomedical imaging",
            "medical device",
            "device development",
            "non-invasive",
            "noninvasive",
            "acoustic",
            "transducer",
            "lab research",
            "research assistant",
            "research intern",
        ],
    )


def _resume_education_score(text: str) -> int:
    has_education = _has_any(text, ["High School Diploma", "Secondary School", "Education", "Expected in"])
    if not has_education:
        return 0
    has_school_detail = _has_any(text, ["Secondary School", "High School", "Expected in"])
    return 1 if has_school_detail else 0


def _resume_skills_score(text: str, skills: list[str]) -> int:
    if not skills and not _has_any(text, ["Skills", "Problem-solving", "Teamwork", "Critical thinking"]):
        return 0
    relevant_skills = [
        "biology",
        "chemistry",
        "physics",
        "computer",
        "programming",
        "problem-solving",
        "critical thinking",
        "communication",
        "teamwork",
        "ocra",
    ]
    relevant_count = sum(1 for term in relevant_skills if term in text.lower())
    return 2 if relevant_count >= 3 else 1


def _resume_awards_score(text: str) -> int:
    has_award = _has_any(text, ["award", "honor", "honour", "accomplishment", "certification", "certificate", "OCRA"])
    if not has_award:
        return 0
    relevant = _has_any(text, ["certification", "certificate", "ocra", "science", "math", "biology", "chemistry", "physics"])
    return 1 if relevant else 0


def _resume_format_score(text: str) -> int:
    lines = _clean_lines(text)
    likely_pages = _resume_likely_pages(text)
    too_many_sections = len(lines) > 90
    max_bullets = _max_bullets_per_experience(lines)
    if likely_pages > 1 or max_bullets > 6:
        return 0
    if likely_pages <= 1 and not too_many_sections:
        return 3
    if likely_pages <= 2 and not too_many_sections:
        return 2
    return 1


def _resume_likely_pages(text: str) -> int:
    lines = _clean_lines(text)
    experience_sections = len([line for line in lines if re.search(r"\b\d{2}/\d{4}\s*-\s*(Current|\d{2}/\d{4})\b", line, re.IGNORECASE)])
    bulletish_lines = len([line for line in lines if _is_resume_bullet_line(line)])
    if experience_sections >= 2 and bulletish_lines >= 12:
        return 2
    return max(1, len(text) // 3000 + (1 if len(text) % 3000 else 0))


def _max_bullets_per_experience(lines: list[str]) -> int:
    max_count = 0
    current_count = 0
    in_experience = False
    for line in lines:
        if re.search(r"\b\d{2}/\d{4}\s*-\s*(Current|\d{2}/\d{4})\b", line, re.IGNORECASE):
            max_count = max(max_count, current_count)
            current_count = 0
            in_experience = True
            continue
        if in_experience and re.search(r"\b(English|Persian|Sunnybrook|Student Personal Information|Ministry of Education)\b", line, re.IGNORECASE):
            max_count = max(max_count, current_count)
            current_count = 0
            in_experience = False
            continue
        if in_experience and _is_resume_bullet_line(line):
            current_count += 1
    return max(max_count, current_count)


def _is_resume_bullet_line(line: str) -> bool:
    if len(line.split()) < 5:
        return False
    action_verbs = [
        "assisted",
        "developed",
        "facilitated",
        "adapted",
        "helped",
        "encouraged",
        "promoted",
        "organized",
        "supported",
        "collaborated",
        "communicated",
        "documented",
        "engaged",
        "worked",
        "strengthened",
        "took",
    ]
    lowered = line.lower()
    return any(lowered.startswith(verb) for verb in action_verbs)


def _has_previous_research_experience(resume_text: str, stem_statement: str) -> bool:
    ai_result = _ai_has_previous_research_experience(resume_text, stem_statement)
    if ai_result is not None:
        return ai_result
    return _fallback_has_previous_research_experience(resume_text)


def _ai_has_previous_research_experience(resume_text: str, stem_statement: str) -> bool | None:
    if not llm.is_configured():
        return None

    try:
        message = llm.complete(
            max_tokens=180,
            temperature=0,
            prompt=(
                        "Decide whether this high school applicant has previous research experience.\n"
                        "Use only actual past experience from the resume or personal statement. Count clear evidence such as research assistant, research intern, lab research, independent research project, publication, poster, science fair research project, or documented experimental investigation.\n"
                        "Do NOT count: interest in research, applying to a research program, wanting hands-on experience, tutoring, normal class labs, observing someone else, or generic phrases like 'research projects' without a specific past project.\n"
                        "Return JSON only: {\"has_research_experience\": true/false, \"reason\": \"short reason\"}.\n\n"
                        f"Resume:\n{resume_text[:3500]}\n\nPersonal statement:\n{stem_statement[:2500]}"
            ),
        )
        raw = message.strip()
        data = _parse_json_object(raw)
        return bool(data.get("has_research_experience"))
    except Exception:
        return None


def _fallback_has_previous_research_experience(resume_text: str) -> bool:
    strong_patterns = [
        r"\bresearch\s+(assistant|intern|student|volunteer|fellow)\b",
        r"\blab\s+(assistant|intern|research)\b",
        r"\bindependent\s+research\s+project\b",
        r"\bscience\s+fair\s+research\b",
        r"\bpublication\b",
        r"\bposter\s+presentation\b",
    ]
    return any(re.search(pattern, resume_text, re.IGNORECASE) for pattern in strong_patterns)


def _career_goals(text: str) -> str:
    if not text.strip():
        return ""
    ai_result = _ai_extract_career_goals(text)
    if ai_result:
        return ai_result
    return _fallback_career_goals(text)


def _ai_extract_career_goals(text: str) -> str:
    if not llm.is_configured():
        return ""

    try:
        message = llm.complete(
            max_tokens=160,
            temperature=0,
            prompt=(
                        "Extract the applicant's career goal from this personal statement. "
                        "Return one concise phrase or sentence only. If no career goal is stated, return an empty string.\n\n"
                        f"Personal statement:\n{text[:4000]}"
            ),
        )
        return _clean_cell(message).strip('"')
    except Exception:
        return ""


def _fallback_career_goals(text: str) -> str:
    specialty_match = re.search(
        r"career\s+in\s+(.+?),\s+with\s+a\s+strong\s+interest\s+in\s+(.+?)(?:\.|\n)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if specialty_match:
        field = _clean_cell(specialty_match.group(1))
        specialty = _clean_cell(specialty_match.group(2))
        return f"Career in {field}; strong interest in {specialty}"

    patterns = [
        r"I\s+aspire\s+to\s+(.+?)(?:\.|\n)",
        r"My\s+goal\s+is\s+to\s+(.+?)(?:\.|\n)",
        r"I\s+am\s+drawn\s+to\s+(.+?)(?:\.|\n)",
        r"strong\s+interest\s+in\s+(.+?)(?:\.|\n)",
        r"career\s+in\s+(.+?)(?:\.|\n)",
    ]
    matches = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            matches.append(_clean_cell(match.group(1)))

    if not matches:
        return _career_goal_from_intent_sentence(text)

    return matches[0][:220]


def _career_goal_from_intent_sentence(text: str) -> str:
    sentences = _statement_sentences(text)
    best_sentence = ""
    best_score = 0
    for sentence in sentences:
        lowered = sentence.lower()
        if _is_stem_statement_prompt_line(sentence):
            continue

        score = 0
        if any(term in lowered for term in ["aspiration", "aspire", "goal", "future", "become", "pursue", "career", "long-term", "hope", "want to"]):
            score += 3
        if any(term in lowered for term in ["technology", "engineering", "medicine", "medical", "healthcare", "science", "research", "entrepreneur", "innovation", "stem"]):
            score += 2
        if any(term in lowered for term in ["understands", "develop", "create", "bring", "deliver", "serve", "help", "impact"]):
            score += 1

        if score > best_score:
            best_score = score
            best_sentence = sentence

    if best_score < 4:
        return ""
    return _clean_cell(best_sentence)[:260]


def _statement_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [_clean_cell(part) for part in parts if len(part.split()) >= 6]


def _rate_stem_statement(text: str) -> int:
    return _evaluate_stem_statement(text)["score"]


def _stem_notes(text: str) -> str:
    return _evaluate_stem_statement(text)["notes"]


def _evaluate_stem_statement(text: str) -> dict:
    if not text.strip():
        return {"score": 0, "notes": "No completed STEM statement was detected in extracted text."}

    ai_result = _ai_evaluate_stem_statement(text)
    if ai_result is not None:
        return ai_result

    scorecard = _stem_statement_scorecard(text)
    strengths = "; ".join(scorecard["strengths"]) or "No required question was clearly answered."
    gaps = "; ".join(scorecard["gaps"]) or "All required questions were addressed"
    return {
        "score": scorecard["score"],
        "notes": f"Fallback rubric scoring. Strengths: {strengths}. Gaps: {gaps}.",
    }


def _ai_evaluate_stem_statement(text: str) -> dict | None:
    if not llm.is_configured():
        return None

    try:
        message = llm.complete(
            max_tokens=700,
            temperature=0,
            prompt=(
                        "Evaluate the applicant's STEM personal statement for a high school research program.\n"
                        "Score out of 10 using these sub-scores:\n"
                        "- General statement quality: 0-5. This includes answering: what they aspire to be/do, what motivates them to get involved in STEM, and why they are a valuable candidate. Award high marks only when these are specific, evidenced, and clearly written.\n"
                        "- FUS/lab relevance and passion: 0-5. Award high marks only when the applicant shows strong interest in focused ultrasound/FUS and/or clear understanding of what the FUS lab does. This can include non-invasive therapy, ultrasound research, biomedical imaging, device/technology development, brain/cancer applications, experimental work, or other specific lab-relevant work.\n\n"
                        "Use this rubric:\n"
                        "- 0: no usable statement.\n"
                        "- 1-4: weak/generic statement and little to no FUS relevance.\n"
                        "- 5: answers the general questions well, but interests/experience are too general or not relevant to FUS/the lab.\n"
                        "- 6-8: answers the general questions and has some FUS/lab relevance or passion, but limited specificity.\n"
                        "- 9-10: answers the general questions very well and shows strong FUS/lab passion or understanding with specific evidence.\n\n"
                        "Caps:\n"
                        "- If there is no clear FUS/lab relevance or understanding, max score is 5 even if the general statement is good.\n"
                        "- If FUS is merely named without explaining interest in or understanding of lab work, max score is 6.\n"
                        "- If any one of the three general questions is missing, max score is 7.\n"
                        "- If there are no concrete examples, max score is 6.\n"
                        "- If it is mostly a generic trait list without evidence, max score is 6.\n\n"
                        "Ignore form instructions/template text. Evaluate only the applicant's answer.\n"
                        "Return JSON only with keys: score, notes. score must be an integer 0-10. notes must be one concise sentence explaining the score.\n\n"
                        f"Statement:\n{text[:5000]}"
            ),
        )
        raw = message.strip()
        data = _parse_json_object(raw)
        score = int(data.get("score", 0))
        notes = str(data.get("notes", "")).strip()
        if not 0 <= score <= 10 or not notes:
            return None
        return {"score": score, "notes": f"AI rubric scoring. {notes}"}
    except Exception:
        return None


def _parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def _stem_statement_scorecard(text: str) -> dict:
    if not text.strip():
        return {"score": 0, "strengths": [], "gaps": ["statement not detected"]}

    strengths = []
    gaps = []

    aspiration_score = _stem_aspiration_score(text)
    if aspiration_score == 3:
        strengths.append("specific and well-explained career aspiration")
    elif aspiration_score > 0:
        gaps.append("career aspiration is present but vague or weakly explained")
    else:
        gaps.append("does not clearly answer what they aspire to be or do")

    motivation_score = _stem_motivation_score(text)
    if motivation_score == 3:
        strengths.append("specific and authentic STEM motivation")
    elif motivation_score > 0:
        gaps.append("STEM motivation is present but generic or weakly supported")
    else:
        gaps.append("does not clearly explain STEM motivation")

    candidate_fit_score = _stem_candidate_fit_score(text)
    if candidate_fit_score == 3:
        strengths.append("clearly explains why they are a valuable candidate")
    elif candidate_fit_score > 0:
        gaps.append("candidate fit is present but generic or weakly evidenced")
    else:
        gaps.append("does not clearly explain why they are a valuable candidate")

    specificity_score = _stem_specificity_score(text)
    if specificity_score:
        strengths.append("includes concrete examples and clear writing")
    else:
        gaps.append("lacks concrete examples or clear specificity")

    general_score = _stem_general_statement_score(
        aspiration_score,
        motivation_score,
        candidate_fit_score,
        specificity_score,
    )
    fus_score = _stem_fus_relevance_score(text)
    score = general_score + fus_score
    if fus_score >= 4:
        strengths.append("shows strong FUS/lab-specific passion or understanding")
    elif fus_score > 0:
        gaps.append("FUS/lab relevance is present but limited or weakly explained")
    else:
        gaps.append("interests and experiences are too general or not clearly relevant to FUS/lab work")

    score = _apply_stem_score_caps(score, aspiration_score, motivation_score, candidate_fit_score, specificity_score, fus_score, text)
    return {"score": min(score, 10), "strengths": strengths, "gaps": gaps}


def _stem_general_statement_score(
    aspiration_score: int,
    motivation_score: int,
    candidate_fit_score: int,
    specificity_score: int,
) -> int:
    raw_score = aspiration_score + motivation_score + candidate_fit_score + specificity_score
    return round((raw_score / 10) * 5)


def _stem_aspiration_score(text: str) -> int:
    if not _answers_aspiration_question(text):
        return 0
    specific_terms = ["medicine", "anesthesiology", "emergency care", "university", "research", "engineer", "scientist", "healthcare"]
    return 3 if _has_any(text, specific_terms) else 2


def _stem_motivation_score(text: str) -> int:
    if not _answers_stem_motivation_question(text):
        return 0
    evidence_terms = ["observed", "experienced", "exposure", "because", "curiosity", "personal", "real-world", "healthcare", "science and technology"]
    return 3 if _has_any(text, evidence_terms) else 2


def _stem_candidate_fit_score(text: str) -> int:
    if not _answers_valuable_candidate_question(text):
        return 0
    evidence_terms = ["because", "bring", "developed", "experience", "skills", "dedication", "curiosity", "adaptability", "commitment", "contribute"]
    return 3 if _has_any(text, evidence_terms) else 2


def _stem_specificity_score(text: str) -> int:
    concrete_terms = [
        "university of toronto",
        "anesthesiology",
        "emergency",
        "cousin",
        "department",
        "laboratory",
        "projects",
        "biology",
        "medicine",
        "healthcare",
    ]
    return 1 if _has_any(text, concrete_terms) else 0


def _stem_fus_relevance_score(text: str) -> int:
    lowered = text.lower()
    has_fus_reference = any(term in lowered for term in ["focused ultrasound", "fus", "ultrasound"])
    has_understanding = _shows_fus_lab_understanding(text)
    if has_understanding and _has_any(text, ["passion", "interested", "curiosity", "motivated", "eager"]):
        return 5
    if has_understanding:
        return 4
    if has_fus_reference:
        return 0
    return 0


def _apply_stem_score_caps(
    score: int,
    aspiration_score: int,
    motivation_score: int,
    candidate_fit_score: int,
    specificity_score: int,
    fus_score: int,
    text: str,
) -> int:
    if fus_score == 0:
        score = min(score, 5)
    elif fus_score == 1:
        score = min(score, 6)
    if 0 in (aspiration_score, motivation_score, candidate_fit_score):
        score = min(score, 7)
    if specificity_score == 0:
        score = min(score, 6)
    if _is_generic_trait_list(text):
        score = min(score, 6)
    if not _has_any(text, ["stem", "science", "research", "laboratory", "medicine", "engineering", "technology", "healthcare"]):
        score = min(score, 8)
    return score


def _is_generic_trait_list(text: str) -> bool:
    lowered = text.lower()
    generic_traits = ["hardworking", "hard-working", "dedicated", "curious", "adaptable", "passionate", "motivated", "teamwork"]
    has_many_traits = sum(1 for trait in generic_traits if trait in lowered) >= 4
    has_evidence = _has_any(text, ["because", "for example", "observed", "developed", "project", "experience", "laboratory"])
    return has_many_traits and not has_evidence


def _answers_aspiration_question(text: str) -> bool:
    return _has_any(text, ["aspire", "career", "goal", "pursue", "become", "study medicine", "future"])


def _answers_stem_motivation_question(text: str) -> bool:
    return _has_any(text, ["motivation for STEM", "motivates", "interested in STEM", "passion", "curiosity", "science and technology"])


def _answers_valuable_candidate_question(text: str) -> bool:
    return _has_any(text, ["strong candidate", "valuable candidate", "bring dedication", "I bring", "because I bring", "skills needed", "contribute"])


def _commitment_to_stem(resume_text: str, stem_statement: str, courses: list[CourseGrade]) -> str:
    evidence = []

    experience = _stem_experience_summary(resume_text)
    if experience:
        evidence.append(experience)

    awards = _stem_awards_summary(resume_text)
    if awards:
        evidence.append(awards)

    motivation = _stem_motivation_summary(stem_statement)
    if motivation:
        evidence.append(motivation)

    if not evidence:
        return "Limited explicit STEM skills or experience found."
    return " ".join(evidence)


def _stem_course_summary(courses: list[CourseGrade]) -> str:
    if not courses:
        return ""

    relevant = [course for course in courses if _is_math_science_or_english(course) or course.course_code.upper().startswith(("ICS", "TEJ"))]
    if not relevant:
        return ""

    current_grade = max(course.grade_level for course in relevant)
    current_courses = [course for course in relevant if course.grade_level == current_grade]
    if not current_courses:
        return ""

    labels = []
    for course in sorted(current_courses, key=lambda item: item.course_code):
        label = course.course_title or course.course_code
        labels.append(f"{label} {course.percentage}%")
    return f"STEM coursework: {', '.join(labels[:6])}."


def _stem_experience_summary(text: str) -> str:
    lines = []
    for line in _clean_lines(text):
        if _is_long_narrative_line(line):
            continue
        if len(line.split()) < 4:
            continue
        if re.search(r"\b(STEM|science|math|biology|chemistry|physics|computer|programming|coding|engineering|robotics|research|lab|hospital|health)\b", line, re.IGNORECASE):
            lines.append(line)
    if not lines:
        return ""
    return f"STEM-related experience: {'; '.join(_dedupe(lines)[:4])}."


def _stem_awards_summary(text: str) -> str:
    lines = []
    for line in _clean_lines(text):
        if re.search(r"\b(award|honou?r roll|certification|certificate|first aid|CPR|OCRA|lifesaving|science fair)\b", line, re.IGNORECASE):
            lines.append(line)
    if not lines:
        return ""
    return f"Relevant awards/certifications: {'; '.join(_dedupe(lines)[:4])}."


def _stem_motivation_summary(text: str) -> str:
    for line in _clean_lines(text):
        lowered = line.lower()
        if len(line.split()) < 8:
            continue
        if _is_stem_statement_prompt_line(line):
            continue
        if any(term in lowered for term in ["stem", "science", "medicine", "engineering", "research", "healthcare", "technology", "biology", "chemistry", "physics"]):
            return f"STEM motivation: {line[:260]}."
    return ""


def _is_stem_statement_prompt_line(line: str) -> bool:
    lowered = line.lower()
    prompt_markers = [
        "please provide a description",
        "what do you aspire",
        "motivates you to get involved",
        "how does this make you",
        "valuable candidate",
        "max 1/2 page",
        "please note:",
        "you will only be contacted",
        "we do not send confirmation",
        "thank you in advance",
    ]
    return any(marker in lowered for marker in prompt_markers)


def _areas(items: list[str]) -> list[str]:
    areas = []
    joined = " ".join(items).lower()
    for area in ["physics", "chemistry", "biology", "engineering"]:
        if area in joined:
            areas.append(area)
    return areas


def _scale_count(count: int) -> int:
    if count <= 0:
        return 0
    if count == 1:
        return 3
    if count == 2:
        return 5
    if count <= 4:
        return 7
    return 9


def _keyword_count(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(keyword.lower()) for keyword in keywords)


def _has_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _clean_lines(text: str) -> list[str]:
    return [_clean_cell(line) for line in text.splitlines() if _clean_cell(line)]


def _clean_cell(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -–•\t")


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
