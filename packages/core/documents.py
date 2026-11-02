"""Render supported document files into images suitable for vision models."""

from dataclasses import dataclass
from io import BytesIO

import pymupdf
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_LONG_SIDE = 1568
PDF_RENDER_SCALE = 2


class DocumentRenderError(ValueError):
    """Raised when a document cannot be rendered as a supported image format."""


@dataclass(frozen=True)
class RenderedDocument:
    images: tuple[bytes, ...]
    page_count: int


def render_document(content: bytes, mime_type: str) -> RenderedDocument:
    normalized_mime_type = mime_type.split(";", maxsplit=1)[0].strip().lower()
    if not content:
        raise DocumentRenderError("The document is empty")
    if normalized_mime_type in {"image/png", "image/jpeg"}:
        expected_format = "PNG" if normalized_mime_type == "image/png" else "JPEG"
        _validate_passthrough_image(content, expected_format)
        return RenderedDocument(images=(content,), page_count=1)
    if normalized_mime_type == "application/pdf":
        return _render_pdf(content)
    if normalized_mime_type in {"image/tiff", "image/tif"}:
        return _render_tiff(content)
    raise DocumentRenderError(f"Unsupported document type: {mime_type}")


def _validate_passthrough_image(content: bytes, expected_format: str) -> None:
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != expected_format:
                raise DocumentRenderError(
                    f"Declared MIME type does not match {image.format or 'unknown'} image data"
                )
            image.verify()
        with Image.open(BytesIO(content)) as image:
            if image.format != expected_format:
                raise DocumentRenderError(
                    f"Declared MIME type does not match {image.format or 'unknown'} image data"
                )
            image.load()
    except DocumentRenderError:
        raise
    except Exception as error:
        raise DocumentRenderError(f"The {expected_format} image is corrupt or truncated") from error


def _sampled_page_indices(page_count: int) -> tuple[int, ...]:
    if page_count <= 0:
        raise DocumentRenderError("Document contains no pages")
    if page_count == 1:
        return (0,)
    return (0, page_count // 2)


def _render_pdf(content: bytes) -> RenderedDocument:
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise DocumentRenderError("The PDF could not be opened") from error

    with document:
        page_count = document.page_count
        selected_pages = _sampled_page_indices(page_count)
        images = tuple(
            _pixmap_to_png(
                document.load_page(index).get_pixmap(
                    matrix=pymupdf.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE), alpha=False
                )
            )
            for index in selected_pages
        )
    return RenderedDocument(images=images, page_count=page_count)


def _render_tiff(content: bytes) -> RenderedDocument:
    try:
        source = Image.open(BytesIO(content))
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise DocumentRenderError("The TIFF could not be opened") from error

    try:
        with source:
            page_count = getattr(source, "n_frames", 1)
            selected_pages = _sampled_page_indices(page_count)
            rendered: list[bytes] = []
            for index in selected_pages:
                source.seek(index)
                source.load()
                rendered.append(_image_to_png(source.convert("RGB")))
    except DocumentRenderError:
        raise
    except Exception as error:
        raise DocumentRenderError("The TIFF could not be decoded") from error
    return RenderedDocument(images=tuple(rendered), page_count=page_count)


def _pixmap_to_png(pixmap: pymupdf.Pixmap) -> bytes:
    return _image_to_png(Image.open(BytesIO(pixmap.tobytes("png"))))


def _image_to_png(image: Image.Image) -> bytes:
    image.thumbnail((MAX_IMAGE_LONG_SIDE, MAX_IMAGE_LONG_SIDE), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
