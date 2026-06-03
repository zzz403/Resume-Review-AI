import io

OCR_TEXT_THRESHOLD = 50


def extract_text(filename: str, content: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext == "pdf":
        return _from_pdf(content)
    if ext in ("doc", "docx"):
        return _from_docx(content)
    return content.decode("utf-8", errors="replace")

def _from_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for index, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if len(page_text.strip()) < OCR_TEXT_THRESHOLD:
            ocr_text = _ocr_pdf_page(content, index)
            if ocr_text.strip():
                page_text = ocr_text

        parts = [page_text]
        annotation_text = _annotation_text(page)
        if annotation_text:
            parts.append(annotation_text)
        pages.append("\n".join(part for part in parts if part.strip()))
    return "\n".join(pages).strip()


def _ocr_pdf_page(content: bytes, page_index: int) -> str:
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except Exception:
        return ""

    try:
        images = convert_from_bytes(
            content,
            dpi=400,
            first_page=page_index + 1,
            last_page=page_index + 1,
        )
        if not images:
            return ""
        return pytesseract.image_to_string(images[0])
    except Exception:
        return ""


def _annotation_text(page) -> str:
    values = []
    for annot_ref in page.get("/Annots") or []:
        annot = annot_ref.get_object()
        if annot.get("/Subtype") != "/FreeText":
            continue
        value = str(annot.get("/Contents") or "").strip()
        if value:
            values.append(value)
    return "\n".join(values)

def _from_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
