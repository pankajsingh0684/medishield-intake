"""Tesseract OCR extraction with word-level confidence and bounding boxes."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


def configure_tesseract(command: str | None) -> None:
    """Set an optional explicit path to the Tesseract executable."""
    if command:
        executable = Path(command).expanduser()
        if executable.is_dir():
            executable /= "tesseract.exe" if os.name == "nt" else "tesseract"
        pytesseract.pytesseract.tesseract_cmd = str(executable)


@dataclass
class OcrWord:
    """A single word extracted by Tesseract."""

    text: str
    confidence: float  # 0-100, normalized to 0-1
    x: float
    y: float
    w: float
    h: float
    page: int = 1


def run_tesseract_ocr(
    image: Image.Image, page_num: int = 1
) -> tuple[list[OcrWord], str, float] | None:
    """
    Run Tesseract OCR on an image.

    Args:
        image: PIL Image to process (should be pre-processed: deskewed, at 300 DPI)
        page_num: Page number for tracking in bounding boxes

    Returns:
        Tuple of (words_list, raw_text, mean_confidence) or None if OCR fails
    """
    try:
        # Ensure image is RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Get word-level data with boxes and confidence
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )

        if not data or not data.get("text"):
            logger.debug("Tesseract returned no text")
            return None

        words = []
        confidences = []
        raw_text_parts = []

        for i in range(len(data["text"])):
            text = data["text"][i].strip()

            # Skip empty lines
            if not text:
                continue

            # Confidence is in range 0-100; convert to 0-1
            conf_raw = int(data["conf"][i])
            confidence = max(0.0, min(1.0, conf_raw / 100.0))

            # Only include words with some confidence
            if confidence > 0.0:
                word = OcrWord(
                    text=text,
                    confidence=confidence,
                    x=float(data["left"][i]),
                    y=float(data["top"][i]),
                    w=float(data["width"][i]),
                    h=float(data["height"][i]),
                    page=page_num,
                )
                words.append(word)
                confidences.append(confidence)
                raw_text_parts.append(text)

        if not words:
            logger.debug("No high-confidence words extracted")
            return None

        raw_text = " ".join(raw_text_parts)
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.debug(
            f"Extracted {len(words)} words, mean confidence: {mean_confidence:.2f}, "
            f"text length: {len(raw_text)}"
        )

        return words, raw_text, mean_confidence

    except (
        OSError,
        TypeError,
        ValueError,
        KeyError,
        pytesseract.TesseractError,
        pytesseract.TesseractNotFoundError,
    ) as e:
        logger.warning(f"Tesseract OCR failed: {e}")
        return None


def render_image_at_dpi(image: Image.Image, target_dpi: int = 300) -> Image.Image:
    """
    Render image at target DPI (300 DPI is standard for OCR).

    If the image's DPI is unknown, we assume it and resize proportionally.

    Args:
        image: PIL Image
        target_dpi: Target DPI for OCR (typically 300)

    Returns:
        Image at target DPI
    """
    try:
        # Get current DPI info if available
        dpi = image.info.get("dpi", (72, 72))
        if dpi and dpi[0] > 0:
            current_dpi = dpi[0]
        else:
            current_dpi = 72  # Default assumption

        if current_dpi == target_dpi:
            return image

        # Calculate scale factor
        scale = target_dpi / current_dpi

        if scale > 1.0:
            # Upscale using LANCZOS
            new_size = (int(image.width * scale), int(image.height * scale))
            return image.resize(new_size, Image.Resampling.LANCZOS)
        elif scale < 1.0:
            # Downscale using LANCZOS
            new_size = (int(image.width * scale), int(image.height * scale))
            return image.resize(new_size, Image.Resampling.LANCZOS)

        return image

    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"DPI adjustment failed: {e}; using original image")
        return image
