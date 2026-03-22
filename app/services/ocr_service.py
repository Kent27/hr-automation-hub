from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

from app.config import OCR_DPI, OCR_LANG


def _resolve_paddle_lang(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized in {"en", "eng", "ind", "id", "eng+ind", "ind+eng"}:
        return "en"
    return normalized or "en"


class OCRService:
    def __init__(self, ocr_dpi: int = OCR_DPI, lang: str = OCR_LANG):
        self.ocr_dpi = max(72, ocr_dpi)
        self.lang = _resolve_paddle_lang(lang)
        self._ocr = None

    @property
    def ocr(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise ValueError(
                    "PaddleOCR is not installed. Install paddleocr and paddlepaddle first."
                ) from exc
            try:
                self._ocr = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    lang=self.lang,
                )
            except TypeError:
                self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang)
        return self._ocr

    def extract_text_from_pdf(self, pdf_path: Path, max_pages: int) -> str:
        try:
            import fitz
        except ImportError as exc:
            raise ValueError("PyMuPDF is not installed. Install pymupdf first.") from exc

        pages_text: List[str] = []
        with fitz.open(str(pdf_path)) as document:
            pages_to_read = min(max_pages, document.page_count)
            zoom = self.ocr_dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            for page_index in range(pages_to_read):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)

                temp_path: Optional[Path] = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                        temp_path = Path(temp_file.name)
                    pixmap.save(str(temp_path))
                    page_text = self.extract_text_from_image(temp_path)
                    if page_text.strip():
                        pages_text.append(page_text)
                finally:
                    if temp_path and temp_path.exists():
                        temp_path.unlink()

        return "\n".join(pages_text).strip()

    def extract_text_from_image(self, image_path: Path) -> str:
        try:
            result = self.ocr.ocr(str(image_path), cls=True)
        except TypeError:
            result = self.ocr.ocr(str(image_path))
        lines: List[str] = []
        for block in result or []:
            if isinstance(block, dict):
                rec_texts = block.get("rec_texts")
                if isinstance(rec_texts, list):
                    for text in rec_texts:
                        if isinstance(text, str) and text.strip():
                            lines.append(text.strip())
                continue

            for item in block or []:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                text_info = item[1]
                if not isinstance(text_info, (list, tuple)) or not text_info:
                    continue
                text = text_info[0]
                if isinstance(text, str) and text.strip():
                    lines.append(text.strip())
        return "\n".join(lines)


ocr_service = OCRService()
