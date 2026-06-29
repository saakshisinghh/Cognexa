"""
OCR Service — Textract abstraction with Tesseract fallback.
Handles PDF, images, and scanned documents.
"""
from __future__ import annotations
import io
import re
import logging
import tempfile
import os
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from langdetect import detect, LangDetectException

from apps.api.config import settings

logger = logging.getLogger(__name__)


def _clean_text(text: str) -> str:
    """Normalize whitespace and remove junk characters."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_language(text: str) -> Optional[str]:
    try:
        sample = text[:2000]
        return detect(sample)
    except LangDetectException:
        return None


def _ocr_image_with_tesseract(image: Image.Image) -> str:
    """Run Tesseract OCR on a PIL image."""
    config = "--oem 3 --psm 6"
    text = pytesseract.image_to_string(image, config=config)
    return text


def _extract_text_from_pdf_native(pdf_bytes: bytes) -> tuple[str, int]:
    """Extract text natively from a PDF (no OCR needed if text layer exists)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text: list[str] = []
    for page in doc:
        pages_text.append(page.get_text("text"))
    full_text = "\n\n".join(pages_text)
    page_count = len(doc)
    doc.close()
    return full_text, page_count


def _pdf_needs_ocr(text: str) -> bool:
    """Heuristic: if extracted text is too sparse, PDF is likely scanned."""
    words = text.split()
    return len(words) < 50


def _ocr_pdf_with_tesseract(pdf_bytes: bytes) -> tuple[str, int]:
    """Rasterize PDF pages and OCR each one."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text: list[str] = []
    for page in doc:
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR accuracy
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        page_text = _ocr_image_with_tesseract(img)
        pages_text.append(page_text)
    page_count = len(doc)
    doc.close()
    return "\n\n".join(pages_text), page_count


def _ocr_with_textract(file_bytes: bytes, mime_type: str) -> str:
    """Use AWS Textract for OCR (abstraction layer)."""
    try:
        import boto3
        client = boto3.client(
            "textract",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        response = client.detect_document_text(Document={"Bytes": file_bytes})
        lines = [
            block["Text"]
            for block in response.get("Blocks", [])
            if block["BlockType"] == "LINE"
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Textract failed: {e}")
        raise


def extract_text_and_metadata(
    file_bytes: bytes,
    mime_type: str,
    filename: str,
) -> dict:
    """
    Main entry point. Returns dict with:
      - text: str
      - page_count: int
      - language: str | None
      - ocr_engine: str
      - metadata: dict
    """
    text = ""
    page_count = 1
    ocr_engine = "none"

    try:
        if mime_type == "application/pdf":
            # Try native extraction first
            native_text, page_count = _extract_text_from_pdf_native(file_bytes)
            if _pdf_needs_ocr(native_text):
                logger.info(f"PDF '{filename}' appears scanned — running OCR")
                if settings.USE_TEXTRACT and settings.AWS_ACCESS_KEY_ID:
                    try:
                        text = _ocr_with_textract(file_bytes, mime_type)
                        ocr_engine = "textract"
                    except Exception:
                        logger.warning("Textract failed, falling back to Tesseract")
                        text, page_count = _ocr_pdf_with_tesseract(file_bytes)
                        ocr_engine = "tesseract"
                else:
                    text, page_count = _ocr_pdf_with_tesseract(file_bytes)
                    ocr_engine = "tesseract"
            else:
                text = native_text
                ocr_engine = "native"

        elif mime_type.startswith("image/"):
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            if settings.USE_TEXTRACT and settings.AWS_ACCESS_KEY_ID:
                try:
                    text = _ocr_with_textract(file_bytes, mime_type)
                    ocr_engine = "textract"
                except Exception:
                    text = _ocr_image_with_tesseract(img)
                    ocr_engine = "tesseract"
            else:
                text = _ocr_image_with_tesseract(img)
                ocr_engine = "tesseract"

        elif mime_type in ("text/plain", "text/markdown", "text/csv"):
            text = file_bytes.decode("utf-8", errors="replace")
            ocr_engine = "passthrough"

        else:
            logger.warning(f"Unsupported MIME type for OCR: {mime_type}")
            text = ""

        text = _clean_text(text)
        language = _detect_language(text) if text else None

        return {
            "text": text,
            "page_count": page_count,
            "language": language,
            "ocr_engine": ocr_engine,
            "metadata": {
                "filename": filename,
                "mime_type": mime_type,
                "char_count": len(text),
                "word_count": len(text.split()),
            },
        }

    except Exception as e:
        logger.error(f"OCR failed for '{filename}': {e}")
        raise RuntimeError(f"OCR processing failed: {e}") from e
