from io import BytesIO

import pymupdf
import pytest
from PIL import Image

from packages.core.documents import (
    MAX_IMAGE_LONG_SIDE,
    DocumentRenderError,
    render_document,
)


def make_raster_bytes(image_format: str, color: tuple[int, int, int] = (20, 40, 60)) -> bytes:
    image = Image.new("RGB", (40, 20), color)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def make_pdf(page_count: int, width: int = 800, height: int = 400) -> bytes:
    document = pymupdf.open()
    for page_index in range(page_count):
        page = document.new_page(width=width, height=height)
        page.insert_text((40, 60), f"Synthetic page {page_index + 1}")
    content = document.tobytes()
    document.close()
    return content


def make_zero_page_pdf() -> bytes:
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [] /Count 0 >>"]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{object_number} 0 obj\n".encode("ascii"))
        content.extend(body)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(b"xref\n0 3\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n"
        + f"{xref_offset}\n".encode("ascii")
        + b"%%EOF\n"
    )
    return bytes(content)


def make_tiff(page_count: int, width: int = 2000, height: int = 1000) -> bytes:
    frames = [
        Image.new("RGB", (width, height), (index * 30, 50, 90)) for index in range(page_count)
    ]
    output = BytesIO()
    frames[0].save(output, format="TIFF", save_all=True, append_images=frames[1:])
    return output.getvalue()


def invalid_document_cases() -> list[tuple[str, bytes, str]]:
    png = make_raster_bytes("PNG")
    jpeg = make_raster_bytes("JPEG")
    return [
        ("empty PNG", b"", "image/png"),
        ("empty JPEG", b"", "image/jpeg"),
        ("empty PDF", b"", "application/pdf"),
        ("empty TIFF", b"", "image/tiff"),
        ("truncated PNG", png[: len(png) // 2], "image/png"),
        ("truncated JPEG", jpeg[: len(jpeg) // 2], "image/jpeg"),
        ("PNG declared as JPEG", png, "image/jpeg"),
        ("PDF with no pages", make_zero_page_pdf(), "application/pdf"),
    ]


@pytest.mark.parametrize("mime_type,image_format", [("image/png", "PNG"), ("image/jpeg", "JPEG")])
def test_png_and_jpeg_pass_through_unchanged(mime_type: str, image_format: str) -> None:
    content = make_raster_bytes(image_format)

    rendered = render_document(content, mime_type)

    assert rendered.images == (content,)
    assert rendered.page_count == 1


def test_pdf_renders_first_and_midpoint_pages_and_downscales() -> None:
    rendered = render_document(make_pdf(4, width=1600, height=900), "application/pdf")

    assert rendered.page_count == 4
    assert len(rendered.images) == 2
    with (
        Image.open(BytesIO(rendered.images[0])) as first_page,
        Image.open(BytesIO(rendered.images[1])) as sampled_page,
    ):
        assert first_page.size == (MAX_IMAGE_LONG_SIDE, 882)
        assert sampled_page.size == first_page.size


def test_single_page_pdf_returns_one_rendered_image() -> None:
    rendered = render_document(make_pdf(1), "application/pdf")

    assert rendered.page_count == 1
    assert len(rendered.images) == 1


def test_multipage_tiff_samples_first_and_midpoint_and_downscales() -> None:
    rendered = render_document(make_tiff(3), "image/tiff")

    assert rendered.page_count == 3
    assert len(rendered.images) == 2
    with Image.open(BytesIO(rendered.images[0])) as first_page:
        assert first_page.size == (MAX_IMAGE_LONG_SIDE, 784)


@pytest.mark.parametrize(
    ("content", "mime_type"),
    [(b"not a pdf", "application/pdf"), (b"not a tiff", "image/tiff")],
)
def test_invalid_document_bytes_raise_render_error(content: bytes, mime_type: str) -> None:
    with pytest.raises(DocumentRenderError):
        render_document(content, mime_type)


def test_unsupported_mime_type_raises_render_error() -> None:
    with pytest.raises(DocumentRenderError, match="Unsupported document type"):
        render_document(b"data", "text/plain")


@pytest.mark.parametrize(
    ("name", "content", "mime_type"),
    invalid_document_cases(),
    ids=[name for name, _, _ in invalid_document_cases()],
)
def test_invalid_image_or_document_is_rejected(
    name: str,
    content: bytes,
    mime_type: str,
) -> None:
    del name
    with pytest.raises(DocumentRenderError):
        render_document(content, mime_type)
