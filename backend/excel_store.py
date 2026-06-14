import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


DATA_DIR = Path(__file__).resolve().parent / "data"
JSON_PATH = DATA_DIR / "applications.json"
EXCEL_PATH = DATA_DIR / "applications.xlsx"

COLUMNS = [
    "student_id",
    "created_at",
    "submitted_at",
    "file_name",
    "applicant_name",
    "email",
    "school",
    "city",
    "current_grade",
    "gender",
    "experimental_work_rank",
    "engineering_technology_development_rank",
    "programming_rank",
    "project_preference_notes",
    "cover_letter_rating_10",
    "cover_letter_notes",
    "fus_understanding_mentioned",
    "fus_understanding_summary",
    "fus_understanding_rating",
    "resume_rating_10",
    "resume_notes",
    "features_technical_experience",
    "features_technical_skills",
    "volunteer_experience",
    "previous_research_experience",
    "career_goals",
    "stem_statement_rating_10",
    "stem_statement_notes",
    "commitment_to_stem",
    "transcript_relative_to_class_median_5",
    "lowest_grade_in_current_grade",
    "general_application_note",
    "sunnybrook_form_note",
    "teacher_evaluation_file_name",
    "teacher_report_rating_5",
    "teacher_evaluation_total_score",
    "teacher_evaluation_note",
    "teacher_comments",
    "academic_ranking",
]

EXCEL_COLUMNS = [
    ("applicant_name", "applicant_name"),
    ("general_application_note", "General Application Note"),
    ("email", "email"),
    ("school", "school"),
    ("city", "city"),
    ("current_grade", "current_grade"),
    ("gender", "gender"),
    ("experimental_work_rank", "experimental_work_rank"),
    ("engineering_technology_development_rank", "engineering_technology_development_rank"),
    ("programming_rank", "programming_rank"),
    ("cover_letter_rating_10", "cover_letter_rating_10"),
    ("fus_understanding_mentioned", "Reference to FUS"),
    ("fus_understanding_summary", "fus_understanding_summary"),
    ("fus_understanding_rating", "FUS Understanding Rate (/5)"),
    ("resume_rating_10", "resume_rating_10"),
    ("features", "features"),
    ("volunteer_experience", "volunteer_experience"),
    ("previous_research_experience", "previous_research_experience"),
    ("career_goals", "career_goals"),
    ("stem_statement_rating_10", "stem_statement_rating_10"),
    ("commitment_to_stem", "commitment_to_stem"),
    ("transcript_relative_to_class_median_5", "transcript_relative_to_class_median_5"),
    ("lowest_grade_in_current_grade", "lowest_grade_in_current_grade"),
    ("sunnybrook_form_note", "Sunnybrook Form Note"),
    ("teacher_report_rating_5", "Teacher's Report"),
    ("teacher_evaluation_note", "Teacher Evaluation Note"),
    ("teacher_comments", "Comments"),
    ("academic_ranking", "Academic Ranking"),
]

YES_NO_KEYS = {"volunteer_experience", "previous_research_experience"}


def create_student(name: str, email: str = "") -> dict:
    """Create an empty student row keyed by a fresh student_id."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_rows()
    row = {column: "" for column in COLUMNS}
    row["student_id"] = uuid.uuid4().hex
    row["applicant_name"] = name.strip()
    row["email"] = email.strip()
    row["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows.append(row)
    _write_json(rows)
    _write_xlsx(rows)
    return _student_summary(row)


def list_students() -> list[dict]:
    return [_student_summary(row) for row in _read_rows()]


def get_student(student_id: str) -> dict | None:
    for row in _read_rows():
        if row.get("student_id") == student_id:
            return row
    return None


def delete_student(student_id: str) -> dict | None:
    rows = _read_rows()
    removed = None
    for row in rows:
        if row.get("student_id") == student_id:
            removed = row
            break
    if removed is None:
        return None
    rows = [row for row in rows if row.get("student_id") != student_id]
    _write_json(rows)
    _write_xlsx(rows)
    return removed


def save_application_profile(profile: dict, student_id: str) -> dict:
    """Merge an extracted application profile into the given student's row."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_rows()
    index = _find_by_id(rows, student_id)
    if index is None:
        raise KeyError(student_id)

    incoming = {column: profile.get(column, "") for column in COLUMNS}
    incoming["features"] = _combined_features(incoming)
    incoming["submitted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    rows[index] = _merge_into_student(rows[index], incoming)
    _write_json(rows)
    _write_xlsx(rows)
    return rows[index]


# Fields a teacher is allowed to edit by hand after the AI has read a document.
# Identity/bookkeeping columns and the on-disk file names are deliberately excluded
# so an edit can never orphan a stored PDF or rewrite a student's id.
PROTECTED_COLUMNS = {
    "student_id",
    "created_at",
    "file_name",
    "teacher_evaluation_file_name",
}
EDITABLE_COLUMNS = {c for c in COLUMNS if c not in PROTECTED_COLUMNS} | {"features"}


def update_student_fields(student_id: str, updates: dict) -> dict:
    """Apply hand-entered field edits onto a student's row.

    Unlike the AI merge helpers, this writes values verbatim — including blanks —
    so a teacher can both correct and clear a field. Unknown or protected keys are
    ignored rather than rejected, keeping the endpoint forgiving of stray payload.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_rows()
    index = _find_by_id(rows, student_id)
    if index is None:
        raise KeyError(student_id)

    row = dict(rows[index])
    for key, value in updates.items():
        if key not in EDITABLE_COLUMNS:
            continue
        row[key] = "" if value is None else value
    row["submitted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows[index] = row
    _write_json(rows)
    _write_xlsx(rows)
    return row


def save_teacher_evaluation_profile(profile: dict, student_id: str) -> dict:
    """Merge an extracted teacher-evaluation profile into the given student's row."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = _read_rows()
    index = _find_by_id(rows, student_id)
    if index is None:
        raise KeyError(student_id)

    incoming = {column: profile.get(column, "") for column in COLUMNS}
    updates = _non_empty_values(incoming)
    updates["teacher_evaluation_note"] = incoming.get("teacher_evaluation_note", "")
    rows[index] = _merge_into_student(rows[index], updates)
    _write_json(rows)
    _write_xlsx(rows)
    return rows[index]


def excel_file_path() -> Path:
    if not EXCEL_PATH.exists():
        _write_xlsx(_read_rows())
    return EXCEL_PATH


def clear_application_data() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    removed_files = []
    for path in [JSON_PATH, EXCEL_PATH, DATA_DIR / "~$applications.xlsx"]:
        if path.exists():
            path.unlink()
            removed_files.append(str(path))
    _write_json([])
    _write_xlsx([])
    return {"removed_files": removed_files, "excel_path": str(EXCEL_PATH)}


def _find_by_id(rows: list[dict], student_id: str) -> int | None:
    for index, row in enumerate(rows):
        if row.get("student_id") == student_id:
            return index
    return None


def _merge_into_student(existing: dict, incoming: dict) -> dict:
    """Apply non-empty incoming values onto a student row.

    Empty incoming values never wipe existing data, so an application upload
    cannot erase teacher-evaluation fields (and vice versa). The student_id,
    created_at, and the operator-chosen applicant_name are always preserved.
    """
    merged = dict(existing)
    for key, value in incoming.items():
        if key in ("student_id", "created_at"):
            continue
        if value in ("", None):
            continue
        merged[key] = value
    if existing.get("applicant_name"):
        merged["applicant_name"] = existing["applicant_name"]
    merged["student_id"] = existing.get("student_id", "")
    merged["created_at"] = existing.get("created_at", "")
    return merged


def _student_summary(row: dict) -> dict:
    return {
        "student_id": row.get("student_id", ""),
        "applicant_name": row.get("applicant_name", ""),
        "email": row.get("email", ""),
        "school": row.get("school", ""),
        "current_grade": row.get("current_grade", ""),
        "has_application": _application_row_has_application(row),
        "has_teacher_evaluation": _application_row_has_teacher_evaluation(row),
        "resume_rating_10": row.get("resume_rating_10", ""),
        "cover_letter_rating_10": row.get("cover_letter_rating_10", ""),
        "stem_statement_rating_10": row.get("stem_statement_rating_10", ""),
        "teacher_report_rating_5": row.get("teacher_report_rating_5", ""),
        "academic_ranking": row.get("academic_ranking", ""),
        "created_at": row.get("created_at", ""),
        "submitted_at": row.get("submitted_at", ""),
    }


def _non_empty_values(row: dict) -> dict:
    return {key: value for key, value in row.items() if value not in ("", None)}


def _normalize_name(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def _read_rows() -> list[dict]:
    if not JSON_PATH.exists():
        return []
    with JSON_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        return []
    for row in data:
        if row.get("teacher_score_note") and not row.get("teacher_evaluation_note"):
            row["teacher_evaluation_note"] = row["teacher_score_note"]
        if row.get("processing_warnings") and not row.get("general_application_note"):
            row["general_application_note"] = row["processing_warnings"]
        row.pop("teacher_score_note", None)
        row.pop("processing_warnings", None)
        for key in YES_NO_KEYS:
            if key in row:
                row[key] = _yes_no_value(row.get(key))
        if not row.get("student_id"):
            row["student_id"] = uuid.uuid4().hex
        if not row.get("created_at"):
            row["created_at"] = row.get("submitted_at", "")
    return data


def _write_json(rows: list[dict]) -> None:
    with JSON_PATH.open("w", encoding="utf-8") as file:
        json.dump(rows, file, indent=2, ensure_ascii=False)


def _write_xlsx(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    worksheet = _worksheet_xml(rows)
    with zipfile.ZipFile(EXCEL_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        archive.writestr("xl/styles.xml", _styles_xml())


def _worksheet_xml(rows: list[dict]) -> str:
    headers = [header for _, header in EXCEL_COLUMNS]
    all_rows = [headers] + [[_excel_value(row, key) for key, _ in EXCEL_COLUMNS] for row in rows]
    xml_rows = []
    for row_index, values in enumerate(all_rows, start=1):
        cells = []
        for col_index, value in enumerate(values, start=1):
            ref = f"{_excel_col(col_index)}{row_index}"
            style_id = _cell_style(row_index, col_index)
            style = f' s="{style_id}"' if style_id else ""
            cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{escape(_cell_text(value))}</t></is></c>')
        row_height = ' ht="42" customHeight="1"' if row_index == 1 else ""
        xml_rows.append(f'<row r="{row_index}"{row_height}>{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'{_cols_xml()}'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        f'<autoFilter ref="A1:{_excel_col(len(EXCEL_COLUMNS))}1"/>'
        '</worksheet>'
    )


def _cell_style(row_index: int, col_index: int) -> int:
    if row_index == 1:
        return 1
    key = EXCEL_COLUMNS[col_index - 1][0]
    if key in {
        "features",
        "general_application_note",
        "sunnybrook_form_note",
        "teacher_evaluation_note",
        "teacher_comments",
        "career_goals",
        "commitment_to_stem",
    }:
        return 2
    return 0


def _cols_xml() -> str:
    cols = []
    for index, (key, header) in enumerate(EXCEL_COLUMNS, start=1):
        width = _column_width(key, header)
        cols.append(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>')
    return f'<cols>{"".join(cols)}</cols>'


def _column_width(key: str, header: str) -> int:
    preferred = {
        "applicant_name": 24,
        "email": 30,
        "school": 34,
        "city": 20,
        "current_grade": 16,
        "gender": 12,
        "experimental_work_rank": 24,
        "engineering_technology_development_rank": 42,
        "programming_rank": 18,
        "cover_letter_rating_10": 24,
        "fus_understanding_mentioned": 18,
        "fus_understanding_summary": 34,
        "fus_understanding_rating": 28,
        "resume_rating_10": 18,
        "features": 58,
        "volunteer_experience": 22,
        "previous_research_experience": 28,
        "career_goals": 42,
        "stem_statement_rating_10": 26,
        "commitment_to_stem": 42,
        "transcript_relative_to_class_median_5": 38,
        "lowest_grade_in_current_grade": 30,
        "general_application_note": 48,
        "sunnybrook_form_note": 54,
        "teacher_report_rating_5": 20,
        "teacher_evaluation_note": 54,
        "teacher_comments": 60,
        "academic_ranking": 20,
    }
    return max(preferred.get(key, 16), min(len(header) + 2, 45))


def _excel_value(row: dict, key: str) -> object:
    if key == "features":
        return row.get("features") or _combined_features(row)
    if key == "general_application_note":
        return _general_application_note(row)
    if key in YES_NO_KEYS:
        return _yes_no_value(row.get(key))
    return row.get(key, "")


def _yes_no_value(value: object) -> object:
    if value is True or value == "true":
        return "Yes"
    if value is False or value == "false":
        return "No"
    return value


def _general_application_note(row: dict) -> str:
    notes = []
    base_note = str(row.get("general_application_note") or row.get("processing_warnings") or "").strip()
    if base_note:
        notes.append(base_note)
    if _application_row_has_application(row) and not _application_row_has_teacher_evaluation(row):
        notes.append("Teacher evaluation is missing.")
    return "; ".join(_dedupe_values(notes))


def _application_row_has_application(row: dict) -> bool:
    application_fields = [
        "file_name",
        "school",
        "current_grade",
        "cover_letter_rating_10",
        "resume_rating_10",
        "stem_statement_rating_10",
        "transcript_relative_to_class_median_5",
        "sunnybrook_form_note",
    ]
    return any(row.get(field) not in ("", None) for field in application_fields)


def _application_row_has_teacher_evaluation(row: dict) -> bool:
    teacher_fields = [
        "teacher_evaluation_file_name",
        "teacher_report_rating_5",
        "teacher_evaluation_total_score",
        "teacher_evaluation_note",
        "teacher_comments",
        "academic_ranking",
    ]
    return any(row.get(field) not in ("", None) for field in teacher_fields)


def _dedupe_values(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _combined_features(row: dict) -> str:
    technical_experience = str(row.get("features_technical_experience", "")).strip()
    technical_skills = str(row.get("features_technical_skills", "")).strip()
    technical_skills = _dedupe_skills_against_experience(technical_skills, technical_experience)
    parts = []
    if technical_experience:
        parts.append(f"Technical experience: {technical_experience}")
    if technical_skills:
        parts.append(f"Technical skills: {technical_skills}")
    return " | ".join(parts)


def _dedupe_skills_against_experience(skills: str, experience: str) -> str:
    if not skills:
        return ""
    experience_lower = experience.lower()
    kept = []
    for skill in [part.strip() for part in skills.split(",") if part.strip()]:
        skill_lower = skill.lower()
        if skill_lower in experience_lower:
            continue
        if skill_lower == "ocra certification" and "ocra" in experience_lower:
            continue
        if skill_lower in {"biology", "chemistry", "physics"} and f"{skill_lower} peer tutor" in experience_lower:
            continue
        kept.append(skill)
    return ", ".join(kept)


def _excel_col(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Y" if value else "N"
    text = str(value)
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )


def _rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Applications" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )


def _workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
        '<alignment vertical="top" wrapText="1"/></xf></cellXfs>'
        '</styleSheet>'
    )
