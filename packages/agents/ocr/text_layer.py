"""PDF text layer extraction."""

import logging

import pymupdf

logger = logging.getLogger(__name__)

MIN_TEXT_LAYER_CHARS = 50


def extract_text_layer_pages(content: bytes) -> tuple[list[str], int] | None:
    """
    Extract text layer from a PDF if present.

    Args:
        content: PDF file bytes

    Returns:
        Tuple of (text, page_count) if text layer has sufficient content,
        else None
    """
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
        page_count = len(doc)

        if page_count == 0:
            logger.debug("PDF has no pages")
            return None

        with doc:
            page_texts = [doc[page_num].get_text().strip() for page_num in range(page_count)]

        insufficient_pages = [
            page_num
            for page_num, text in enumerate(page_texts, start=1)
            if len(text) < MIN_TEXT_LAYER_CHARS
        ]
        if insufficient_pages:
            logger.debug(
                "PDF pages %s have fewer than %s text characters",
                insufficient_pages,
                MIN_TEXT_LAYER_CHARS,
            )
            return None

        logger.debug(
            "Extracted %s characters from each of %s PDF pages",
            [len(text) for text in page_texts],
            page_count,
        )
        return page_texts, page_count

    except (pymupdf.FileDataError, RuntimeError, TypeError, ValueError) as e:
        logger.debug(f"Failed to extract PDF text layer: {e}")
        return None


def extract_text_layer(content: bytes) -> tuple[str, int] | None:
    """Return concatenated text when every PDF page meets the minimum threshold."""
    result = extract_text_layer_pages(content)
    if result is None:
        return None
    page_texts, page_count = result
    return "\n".join(page_texts), page_count
