"""Parse and ingest policy PDFs into relational and vector stores."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pymupdf
from sqlalchemy import delete
from sqlalchemy.orm import Session

from packages.core.db.models import Policy, PolicyExclusion
from packages.rag.chunking import ContentBlock, PolicyChunk, chunk_blocks
from packages.rag.embeddings import Embedder
from packages.rag.store import QdrantPolicyStore

_RANGE = re.compile(r"^([A-Z]?\d{4,5}[A-Z]?)-([A-Z]?\d{4,5}[A-Z]?)$", re.IGNORECASE)
_FOOTER = "MediShield Health Insurance Ltd."


@dataclass(frozen=True)
class Exclusion:
    range_start: str
    range_end: str
    category: str
    basis: str
    page: int


@dataclass(frozen=True)
class ParsedPolicy:
    blocks: list[ContentBlock]
    exclusions: list[Exclusion]


def _extract_exclusions(content: bytes) -> list[Exclusion]:
    lines_with_pages: list[tuple[str, int]] = []
    document = pymupdf.open(stream=content, filetype="pdf")
    for page_index, page in enumerate(document):
        lines_with_pages.extend(
            (line.strip(), page_index + 1) for line in page.get_text().splitlines() if line.strip()
        )
    table_start = next(
        (
            index
            for index, (line, _) in enumerate(lines_with_pages)
            if "Excluded CPT Code Ranges" in line
        ),
        None,
    )
    if table_start is None:
        raise ValueError("The policy contains no Excluded CPT Code Ranges table")
    table_lines = lines_with_pages[table_start + 1 :]
    ranges = [
        (index, _RANGE.fullmatch(line), page) for index, (line, page) in enumerate(table_lines)
    ]
    rows = [(index, match, page) for index, match, page in ranges if match is not None]
    exclusions: list[Exclusion] = []
    for line_index, match, page in rows:
        cells = []
        for line, _ in table_lines[line_index + 1 :]:
            if _RANGE.fullmatch(line):
                break
            if line.startswith((_FOOTER, "Page ")) or line in {
                "CPT Range",
                "Procedure Category",
                "Exclusion Basis",
            }:
                continue
            cells.append(line)
            if len(cells) == 2:
                break
        if len(cells) < 2:
            raise ValueError(f"Incomplete exclusion row on page {page}")
        exclusions.append(
            Exclusion(match.group(1).upper(), match.group(2).upper(), cells[0], cells[1], page)
        )
    if not exclusions:
        raise ValueError("The policy contains no Excluded CPT Code Ranges table")
    return exclusions


def parse_policy(content: bytes, filename: str) -> ParsedPolicy:
    from docling.document_converter import DocumentConverter
    from docling_core.types.io import DocumentStream

    document_stream = DocumentStream(name=Path(filename).name, stream=BytesIO(content))
    document = DocumentConverter().convert(document_stream).document
    blocks: list[ContentBlock] = []
    headings: list[tuple[int, str]] = []
    for item, level in document.iterate_items():
        label = getattr(item.label, "value", str(item.label)).casefold()
        page = item.prov[0].page_no if getattr(item, "prov", None) else None
        if label in {"title", "section_header"}:
            heading = item.text.strip()
            headings = [(depth, text) for depth, text in headings if depth < level]
            headings.append((level, heading))
            continue
        section_path = " > ".join(text for _, text in headings) or "Document"
        if label == "table":
            try:
                text = item.export_to_markdown(document)
            except (AttributeError, TypeError):
                text = item.text
            blocks.append(ContentBlock(text, section_path, page, is_table=True))
        elif getattr(item, "text", "").strip():
            blocks.append(ContentBlock(item.text.strip(), section_path, page))
    return ParsedPolicy(blocks, _extract_exclusions(content))


def infer_plan_code(filename: str) -> str:
    name = Path(filename).stem.casefold()
    if "gold" in name:
        return "GOLD"
    if "silver" in name or "slv" in name:
        return "SILVER"
    raise ValueError("Policy filename must identify the GOLD or SILVER plan")


def ingest_policy_document(
    session: Session,
    policy_id: UUID,
    content: bytes,
    store: QdrantPolicyStore,
    embedder: Embedder,
) -> int:
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise ValueError(f"Unknown policy {policy_id}")
    policy.ingest_status = "PENDING"
    session.flush()
    try:
        parsed = parse_policy(content, policy.object_key or f"{policy.plan_code}.pdf")
        chunks: list[PolicyChunk] = chunk_blocks(parsed.blocks)
        vectors = embedder.embed([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("Embedder returned a different number of vectors than input chunks")
        store.ensure_collection(embedder.dimension)
        store.replace_policy_chunks(
            policy.policy_id,
            policy.version or "unknown",
            policy.effective_from or date.min,
            policy.effective_to,
            chunks,
            vectors,
        )
        session.execute(delete(PolicyExclusion).where(PolicyExclusion.policy_id == policy_id))
        session.add_all(
            [
                PolicyExclusion(
                    exclusion_id=uuid4(),
                    policy_id=policy_id,
                    range_start=item.range_start,
                    range_end=item.range_end,
                    category=item.category,
                    basis=item.basis,
                    page=item.page,
                )
                for item in parsed.exclusions
            ]
        )
        policy.ingest_status = "READY"
        policy.chunk_count = len(chunks)
        return len(chunks)
    except Exception:
        policy.ingest_status = "FAILED"
        policy.chunk_count = 0
        raise
