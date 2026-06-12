import io
import json
import logging
import re

import llm

logger = logging.getLogger(__name__)


def extract_teacher_evaluation_profile(filename: str, text: str, content: bytes | None = None) -> dict:
    """Extract the teacher-evaluation profile via the LLM structured-output path,
    falling back to the legacy regex pipeline on any failure."""
    try:
        import llm_extract

        if llm.is_configured(llm.get_vision_provider()) or llm.is_configured(llm.get_text_provider()):
            profile = llm_extract.extract_teacher_evaluation_ai(filename, text, content)
            if profile.get("teacher_evaluation_total_score") or profile.get("teacher_comments") or profile.get("academic_ranking"):
                return profile
            logger.warning("LLM teacher-evaluation extraction returned nothing usable; using legacy path.")
    except Exception:  # noqa: BLE001 - any LLM/render failure falls back
        logger.warning("LLM teacher-evaluation extraction failed; using legacy path.", exc_info=True)
    return _extract_teacher_evaluation_profile_legacy(filename, text, content)


def _extract_teacher_evaluation_profile_legacy(filename: str, text: str, content: bytes | None = None) -> dict:
    total_score = _extract_total_score(text)
    visual_fields = _ai_extract_teacher_evaluation_from_image(content) if content and total_score is None else {}
    score_source = "text" if total_score is not None else ""
    if total_score is None:
        total_score = _parse_total_score_value(visual_fields.get("total_score", ""))
        if total_score is not None:
            score_source = "handwritten"
    academic_ranking = _clean_academic_ranking(
        _extract_academic_ranking(text, content) or str(visual_fields.get("academic_ranking", ""))
    )
    teacher_comments = _summarize_teacher_comments(text) or _visual_teacher_comments(visual_fields)
    evaluation_note = _teacher_evaluation_note(
        score_source=score_source,
        has_rating=total_score is not None,
        has_academic_ranking=bool(academic_ranking),
        has_teacher_comments=bool(teacher_comments),
        content=content,
    )
    return {
        "teacher_evaluation_file_name": filename,
        "applicant_name": _extract_student_name(text, filename),
        "teacher_report_rating_5": _score_out_of_5(total_score),
        "teacher_evaluation_total_score": _format_total_score(total_score),
        "teacher_evaluation_note": evaluation_note,
        "teacher_comments": teacher_comments,
        "academic_ranking": academic_ranking,
        "gender": _infer_gender_from_pronouns(text),
    }


def _extract_student_name(text: str, filename: str = "") -> str:
    match = re.search(r"Student.?s\s+Full\s+Name:\s*(.+?)(?:\n|Criterion)", text, re.IGNORECASE | re.DOTALL)
    if match:
        value = _clean_cell(match.group(1))
        if value and not re.search(r"\b(Criterion|Creativity|Academic|Cooperation|Score)\b", value, re.IGNORECASE):
            return value
    appended_name = _appended_student_name(text)
    if appended_name:
        return appended_name
    return _student_name_from_filename(filename)


def _student_name_from_filename(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = re.sub(r"\s*-\s*Teacher\s+Evaluation$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_?FUS\s+HS\s+Program\s+20\d{2}\s+Teacher\s+Reference\s+Form$", "", stem, flags=re.IGNORECASE)
    stem = stem.replace("(", " ").replace(")", " ")
    stem = re.sub(r"[_-]+", " ", stem)
    return _clean_cell(stem)


def _appended_student_name(text: str) -> str:
    answers = _appended_answer_lines(text)
    if answers and _looks_like_person_name(answers[0]):
        return _clean_cell(answers[0])
    return ""


def _extract_total_score(text: str) -> tuple[float, float] | None:
    match = re.search(r"Total\s+Score:\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return float(match.group(1)), float(match.group(2))
    appended_score = _appended_total_score(text)
    return (float(appended_score), 50.0) if appended_score is not None else None


def _parse_total_score_value(value: object) -> tuple[float, float] | None:
    value = str(value or "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _teacher_evaluation_note(
    score_source: str,
    has_rating: bool,
    has_academic_ranking: bool,
    has_teacher_comments: bool,
    content: bytes | None,
) -> str:
    is_scanned = _looks_like_scanned_teacher_evaluation(content)
    notes = []
    if score_source == "handwritten":
        notes.append("Teacher rating was read from handwriting/scanned form; verify manually.")
    elif not has_rating:
        notes.append("Teacher rating could not be read.")
    if not has_academic_ranking:
        notes.append("Academic ranking could not be read.")
    if not has_teacher_comments:
        notes.append("Teacher comments could not be read.")
    if notes and is_scanned:
        notes.append("Manual review recommended for scanned/handwritten teacher evaluation.")
    return " ".join(notes)


def _looks_like_scanned_teacher_evaluation(content: bytes | None) -> bool:
    if not content:
        return False
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        if not reader.pages:
            return False
        first_page_text = reader.pages[0].extract_text() or ""
        return len(first_page_text.strip()) < 200
    except Exception:
        return False


def _ai_extract_teacher_evaluation_from_image(content: bytes | None) -> dict:
    if not content or not llm.is_configured():
        return {}

    image_data = _teacher_evaluation_first_page_png(content)
    if not image_data:
        return {}

    try:
        message = llm.complete_vision(
            (
                "Read this teacher evaluation form image. Extract only visible handwritten or typed form values. "
                "Return JSON only with keys: student_name, academic_ranking, total_score, teacher_comments, improvement_area. "
                "academic_ranking must be one of Top 5%, Top 10%, Top 15%, Top 20%, Top 25%, or empty. "
                "total_score must look like 49/50 or 50/50, or empty if not legible. "
                "teacher_comments should contain the visible Further Comments text only. "
                "improvement_area should contain the visible improvement-area answer only. "
                "Do not infer or guess unclear handwritten numbers."
            ),
            max_tokens=300,
            temperature=0,
            image_png=image_data,
        )
        return _parse_json_object(message.strip())
    except Exception:
        return {}


def _teacher_evaluation_first_page_png(content: bytes) -> bytes:
    image_data = _image_bytes_as_png(content)
    if image_data:
        return image_data

    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(content, dpi=220, first_page=1, last_page=1)
    except Exception:
        return b""

    if not images:
        return b""

    image = images[0]
    if image.width > 1800:
        ratio = 1800 / image.width
        image = image.resize((1800, int(image.height * ratio)))

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _image_bytes_as_png(content: bytes) -> bytes:
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception:
        return b""

    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    if image.width > 1800:
        ratio = 1800 / image.width
        image = image.resize((1800, int(image.height * ratio)))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _score_out_of_5(total_score: tuple[float, float] | None) -> float | str:
    if total_score is None:
        return ""
    score, maximum = total_score
    if maximum <= 0:
        return ""
    return round((score / maximum) * 5, 2)


def _format_total_score(total_score: tuple[float, float] | None) -> str:
    if total_score is None:
        return ""
    score, maximum = total_score
    return f"{_format_number(score)}/{_format_number(maximum)}"


def _extract_academic_ranking(text: str, content: bytes | None = None) -> str:
    ranking_line = re.search(
        r"Top\s+5%.*?Top\s+10%.*?Top\s+15%.*?Top\s+20%.*?Top\s+25%.*?(?:\n|Cooperation)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not ranking_line:
        return _extract_academic_ranking_from_image(content) if content else ""
    line = ranking_line.group(0)
    for rank in ["5", "10", "15", "20", "25"]:
        pattern = rf"Top\s+{rank}%\s*[_\s]*[xX✓✔☑]"
        if re.search(pattern, line):
            return f"Top {rank}%"
    return _extract_academic_ranking_from_image(content) if content else ""


def _clean_academic_ranking(value: str) -> str:
    match = re.search(r"Top\s*(5|10|15|20|25)\s*%", value, re.IGNORECASE)
    return f"Top {match.group(1)}%" if match else ""


def _extract_academic_ranking_from_image(content: bytes | None) -> str:
    if not content:
        return ""

    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(content, dpi=200, first_page=1, last_page=1)
    except Exception:
        return ""

    if not images:
        return ""

    boxes = _academic_rank_checkbox_boxes(images[0])
    if len(boxes) != 5:
        return ""

    ranks = ["5", "10", "15", "20", "25"]
    for rank, box in zip(ranks, boxes):
        if _checkbox_has_inner_mark(images[0], box):
            return f"Top {rank}%"
    return ""


def _academic_rank_checkbox_boxes(image) -> list[tuple[int, int, int, int]]:
    gray = image.convert("L")
    width, height = gray.size
    y_start = int(height * 0.24)
    y_end = int(height * 0.34)
    threshold = 100
    pixels = gray.load()
    visited: set[tuple[int, int]] = set()
    components = []

    for y in range(y_start, y_end):
        for x in range(width):
            if (x, y) in visited or pixels[x, y] > threshold:
                continue
            stack = [(x, y)]
            visited.add((x, y))
            xs = []
            ys = []
            while stack:
                current_x, current_y = stack.pop()
                xs.append(current_x)
                ys.append(current_y)
                for next_x, next_y in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    if next_x < 0 or next_x >= width or next_y < y_start or next_y >= y_end:
                        continue
                    if (next_x, next_y) in visited or pixels[next_x, next_y] > threshold:
                        continue
                    visited.add((next_x, next_y))
                    stack.append((next_x, next_y))

            if len(xs) < 80:
                continue
            box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
            box_width = box[2] - box[0]
            box_height = box[3] - box[1]
            if 25 <= box_width <= 100 and 25 <= box_height <= 90:
                components.append((box, len(xs)))

    outer_boxes = []
    for box, area in components:
        if area < 300:
            continue
        if any(_box_contains(other_box, box) and other_box != box for other_box, _ in components):
            continue
        outer_boxes.append(box)

    return sorted(outer_boxes, key=lambda item: item[0])[:5]


def _checkbox_has_inner_mark(image, box: tuple[int, int, int, int]) -> bool:
    gray = image.convert("L")
    pixels = gray.load()
    x_start, y_start, x_end, y_end = box
    box_width = x_end - x_start
    box_height = y_end - y_start
    side = min(box_width, box_height)
    square = (x_start, y_start, x_start + side, y_start + side)
    threshold = 100
    visited: set[tuple[int, int]] = set()

    for y in range(square[1] + 3, square[3] - 3):
        for x in range(square[0] + 3, square[2] - 3):
            if (x, y) in visited or pixels[x, y] > threshold:
                continue
            stack = [(x, y)]
            visited.add((x, y))
            xs = []
            ys = []
            while stack:
                current_x, current_y = stack.pop()
                xs.append(current_x)
                ys.append(current_y)
                for next_x, next_y in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    if next_x <= square[0] + 2 or next_x >= square[2] - 2 or next_y <= square[1] + 2 or next_y >= square[3] - 2:
                        continue
                    if (next_x, next_y) in visited or pixels[next_x, next_y] > threshold:
                        continue
                    visited.add((next_x, next_y))
                    stack.append((next_x, next_y))

            if len(xs) >= 25:
                component = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
                if _box_inside(component, square, margin=2):
                    return True
    return False


def _box_contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _box_inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int], margin: int = 0) -> bool:
    return (
        inner[0] >= outer[0] + margin
        and inner[1] >= outer[1] + margin
        and inner[2] <= outer[2] - margin
        and inner[3] <= outer[3] - margin
    )


def _infer_gender_from_pronouns(text: str) -> str:
    comments_text = " ".join([_comments_block(text), _improvement_block(text)])
    male_count = len(re.findall(r"\b(he|him|his)\b", comments_text, re.IGNORECASE))
    female_count = len(re.findall(r"\b(she|her|hers)\b", comments_text, re.IGNORECASE))
    if male_count >= 2 and female_count == 0:
        return "Male"
    if female_count >= 2 and male_count == 0:
        return "Female"
    return ""


def _summarize_teacher_comments(text: str) -> str:
    comments = _comments_block(text)
    improvement = _improvement_block(text)
    if _placeholder_teacher_text(comments):
        comments = ""
    if _placeholder_teacher_text(improvement):
        improvement = ""
    if not comments.strip() and not improvement.strip():
        return ""
    ai_summary = _ai_summarize_teacher_comments(comments, improvement)
    if ai_summary:
        return ai_summary
    return _fallback_teacher_comment_summary(comments, improvement)


def _visual_teacher_comments(visual_fields: dict) -> str:
    comments = _clean_cell(str(visual_fields.get("teacher_comments", "")))
    improvement = _clean_cell(str(visual_fields.get("improvement_area", "")))
    parts = []
    if comments:
        parts.append(comments)
    if improvement and improvement.lower() != comments.lower():
        parts.append(f"Improvement area: {improvement}")
    return " ".join(parts)


def _ai_summarize_teacher_comments(comments: str, improvement: str) -> str:
    if not llm.is_configured():
        return ""

    try:
        message = llm.complete(
            (
                "Summarize this teacher evaluation comment for an applicant review spreadsheet.\n"
                "Do not use a keyword checklist. Include whatever the teacher actually says, positive or negative.\n"
                "Capture strengths, concerns, and any stated area for improvement. Do not invent details.\n"
                "Write 1-2 concise sentences, maximum 70 words. Return only the summary.\n\n"
                f"Further comments:\n{comments[:3000]}\n\nArea for improvement:\n{improvement[:1200]}"
            ),
            max_tokens=220,
            temperature=0,
        )
        return _limit_words(_clean_cell(message).strip('"'), 70)
    except Exception:
        return ""


def _comments_block(text: str) -> str:
    start = re.search(r"Further\s+Comments.*?\):", text, re.IGNORECASE | re.DOTALL)
    end = re.search(r"Please\s+indicate\s+one\s+skill\s+or\s+area\s+for\s+improvement", text, re.IGNORECASE)
    if start and end and end.start() > start.end():
        comments = text[start.end() : end.start()]
        letter = _attached_letter_block(text)
        if re.search(r"next page|attached|letter", comments, re.IGNORECASE) or (letter and len(_clean_cell(comments)) < 80):
            if letter:
                return letter
            if _placeholder_teacher_text(comments):
                return _appended_comments_block(text) or ""
        if _clean_cell(comments) and not _placeholder_teacher_text(comments):
            return comments
    return _attached_letter_block(text) or _appended_comments_block(text)


def _improvement_block(text: str) -> str:
    start = re.search(r"Please\s+indicate\s+one\s+skill\s+or\s+area\s+for\s+improvement.*?answer", text, re.IGNORECASE | re.DOTALL)
    end = re.search(r"Teacher.?s\s+Full\s+Name:", text, re.IGNORECASE)
    if start and end and end.start() > start.end():
        improvement = text[start.end() : end.start()]
        if not re.search(r"next page|attached|letter|help us place", improvement, re.IGNORECASE):
            return improvement

    letter_recommendation = re.search(
        r"If\s+I\s+were\s+to\s+offer\s+a\s+recommendation.*?(?:\.|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if letter_recommendation:
        return letter_recommendation.group(0)
    return _appended_improvement_block(text)


def _attached_letter_block(text: str) -> str:
    start = re.search(r"\bDear\s+(?:Dr\.|Mr\.|Ms\.|Mrs\.)?", text, re.IGNORECASE)
    end = re.search(r"\bSincerely\b", text[start.start() :] if start else "", re.IGNORECASE)
    if start and end:
        return text[start.start() : start.start() + end.start()]
    if start:
        return text[start.start() :]
    return ""


def _placeholder_teacher_text(text: str) -> bool:
    cleaned = _clean_cell(text).lower()
    if not cleaned:
        return True
    placeholder_patterns = [
        r"please\s+see\s+attached",
        r"found\s+in\s+next\s+page",
        r"next\s+page",
        r"attached\s+pdf",
        r"attached\s+letter",
        r"help\s+us\s+place\s+the\s+student",
    ]
    return any(re.search(pattern, cleaned) for pattern in placeholder_patterns)


def _appended_answer_lines(text: str) -> list[str]:
    marker = re.search(r"Teacher.?s\s+Signature\s*\(Electronic\s+is\s+acceptable\):\s*Date:", text, re.IGNORECASE)
    if not marker:
        return []
    return _clean_lines(text[marker.end() :])


def _appended_total_score(text: str) -> int | None:
    answers = _appended_answer_lines(text)
    for index in range(len(answers) - 1, -1, -1):
        line = answers[index]
        if re.fullmatch(r"\d{1,2}", line):
            score = int(line)
            if 0 <= score <= 50 and _line_after_comment_answers(answers, index) and _line_before_improvement(answers, index):
                return score
    return None


def _appended_comments_block(text: str) -> str:
    answers = _appended_answer_lines(text)
    if not answers:
        return ""

    comment_lines = []
    started = False
    for line in answers[1:]:
        if not started:
            if _looks_like_sentence(line):
                started = True
                comment_lines.append(line)
            continue
        if _looks_like_person_name(line) or _looks_like_school_or_email_or_date(line) or re.fullmatch(r"\d{1,2}", line):
            break
        comment_lines.append(line)
    return _clean_cell(" ".join(comment_lines))


def _appended_improvement_block(text: str) -> str:
    answers = _appended_answer_lines(text)
    total_score = _appended_total_score(text)
    if total_score is None:
        return ""
    for index, line in enumerate(answers):
        if line == str(total_score) and _line_after_comment_answers(answers, index):
            return _clean_cell(" ".join(answers[index + 1 :]))
    return ""


def _line_after_comment_answers(lines: list[str], index: int) -> bool:
    return index >= 1 and any(_looks_like_sentence(line) for line in lines[:index])


def _line_before_improvement(lines: list[str], index: int) -> bool:
    return any(_looks_like_sentence(line) for line in lines[index + 1 :])


def _looks_like_sentence(line: str) -> bool:
    return len(line.split()) >= 6 and not _looks_like_school_or_email_or_date(line)


def _looks_like_person_name(line: str) -> bool:
    if "@" in line or re.search(r"\d", line):
        return False
    words = line.split()
    return 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Z][A-Za-z'.-]*", word) for word in words)


def _looks_like_school_or_email_or_date(line: str) -> bool:
    return bool(
        "@" in line
        or re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", line)
        or re.search(r"\b(CI|C\.I\.|School|Secondary|High)\b", line, re.IGNORECASE)
    )


def _fallback_teacher_comment_summary(comments: str, improvement: str) -> str:
    parts = []
    comment_summary = _sentence_summary(_clean_teacher_comment_source(comments), max_sentences=2)
    if comment_summary:
        parts.append(comment_summary)
    improvement_summary = _sentence_summary(_clean_teacher_comment_source(improvement), max_sentences=1)
    if improvement_summary:
        parts.append(f"Area for improvement: {improvement_summary}")
    return _limit_words(" ".join(parts), 70)


def _sentence_summary(text: str, max_sentences: int) -> str:
    cleaned = _clean_cell(text)
    if not cleaned:
        return ""
    sentences = [
        _clean_cell(sentence)
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
        if len(sentence.split()) >= 4
    ]
    if not sentences and len(cleaned.split()) >= 4:
        sentences = [cleaned]
    return " ".join(sentences[:max_sentences])


def _clean_teacher_comment_source(text: str) -> str:
    cleaned = _clean_cell(re.sub(r"_+", " ", text))
    start_patterns = [
        r"\bIt\s+is\s+(?:an\s+honou?r|a\s+privilege)\b",
        r"\bIt\s+is\s+with\s+great\s+pleasure\b",
        r"\bI\s+have\s+known\b",
        r"\bHaving\s+mentored\b",
        r"\bIt\s+has\s+been\s+a\s+pleasure\b",
        r"\bI\s+am\s+pleased\b",
        r"\bI\s+am\s+writing\b",
        r"\bIf\s+I\s+were\s+to\s+offer\b",
        r"\bThough\s+",
    ]
    starts = [match.start() for pattern in start_patterns for match in [re.search(pattern, cleaned, re.IGNORECASE)] if match]
    if starts:
        cleaned = cleaned[min(starts) :]
    cleaned = re.sub(r"^(?:Dear\s+[^,]+,\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:To\s+whom\s+it\s+may\s+concern,?\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:Re:\s*[^.]+?\s+)", "", cleaned, flags=re.IGNORECASE)
    return _clean_cell(cleaned)


def _limit_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "."


def _clean_cell(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -–•\t")


def _clean_lines(text: str) -> list[str]:
    return [_clean_cell(line) for line in text.splitlines() if _clean_cell(line)]


def _parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
