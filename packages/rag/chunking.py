"""Heading-aware policy chunking with shared token accounting."""

from dataclasses import dataclass
from functools import lru_cache

import tiktoken

TARGET_TOKENS = 600
MAX_TOKENS = 800
OVERLAP_TOKENS = 80
MAX_TABLE_TOKENS = 1000


@dataclass(frozen=True)
class ContentBlock:
    text: str
    section_path: str
    page: int | None
    is_table: bool = False
    is_heading: bool = False


@dataclass(frozen=True)
class PolicyChunk:
    text: str
    section_path: str
    page: int | None
    chunk_type: str
    is_table: bool = False
    is_heading_only: bool = False


@lru_cache(maxsize=1)
def _tokenizer() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_tokenizer().encode(text))


def chunk_type_for_heading(section_path: str) -> str:
    heading = section_path.casefold()
    for chunk_type, terms in (
        ("exclusion", ("exclusion", "excluded", "not covered")),
        ("definition", ("definition", "defined terms", "glossary")),
        ("schedule", ("schedule", "benefit table", "copayment")),
        (
            "coverage",
            ("coverage", "covered services", "covered under", "inclusion", "benefits"),
        ),
    ):
        if any(term in heading for term in terms):
            return chunk_type
    return "other"


def _split_text(text: str, max_tokens: int = TARGET_TOKENS) -> list[str]:
    tokens = _tokenizer().encode(text)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(_tokenizer().decode(tokens[start:end]).strip())
        if end == len(tokens):
            break
        start = end - OVERLAP_TOKENS
    return [chunk for chunk in chunks if chunk]


def chunk_blocks(blocks: list[ContentBlock]) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    section_blocks: list[ContentBlock] = []

    def flush_section() -> None:
        if not section_blocks:
            return
        section_path = section_blocks[0].section_path
        page = section_blocks[0].page
        text = "\n\n".join(block.text.strip() for block in section_blocks if block.text.strip())
        if not text:
            section_blocks.clear()
            return
        pieces = _split_text(text)
        heading_only = all(block.is_heading for block in section_blocks)
        for piece in pieces:
            chunks.append(
                PolicyChunk(
                    piece,
                    section_path,
                    page,
                    chunk_type_for_heading(section_path),
                    is_heading_only=heading_only,
                )
            )
        section_blocks.clear()

    for block in blocks:
        if block.is_table:
            flush_section()
            if count_tokens(block.text) <= MAX_TABLE_TOKENS:
                table_pieces = [block.text.strip()]
            else:
                table_pieces = _split_text(block.text)
            chunks.extend(
                PolicyChunk(
                    piece,
                    block.section_path,
                    block.page,
                    chunk_type_for_heading(block.section_path),
                    is_table=True,
                )
                for piece in table_pieces
            )
        elif section_blocks and (
            block.section_path != section_blocks[0].section_path
            or count_tokens("\n\n".join(item.text for item in section_blocks) + "\n\n" + block.text)
            > MAX_TOKENS
        ):
            flush_section()
            section_blocks.append(block)
        else:
            section_blocks.append(block)
    flush_section()

    def top_level(section_path: str) -> str:
        return section_path.split(">", maxsplit=1)[0].strip()

    def merge_chunks(left: PolicyChunk, right: PolicyChunk) -> PolicyChunk:
        section_path = " > ".join(dict.fromkeys((left.section_path, right.section_path)))
        return PolicyChunk(
            text=f"{left.text}\n\n{right.text}",
            section_path=section_path,
            page=left.page,
            chunk_type=left.chunk_type,
        )

    def can_merge(left: PolicyChunk, right: PolicyChunk) -> bool:
        return (
            not left.is_table
            and not right.is_table
            and left.chunk_type == right.chunk_type
            and top_level(left.section_path) == top_level(right.section_path)
            and count_tokens(left.text + "\n\n" + right.text) <= MAX_TOKENS
        )

    merged: list[PolicyChunk] = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        needs_merge = chunk.is_heading_only or (
            not chunk.is_table and count_tokens(chunk.text) < 60
        )
        if not needs_merge or chunk.is_table:
            merged.append(chunk)
            index += 1
            continue

        same_section_before = bool(
            merged
            and not merged[-1].is_table
            and top_level(merged[-1].section_path) == top_level(chunk.section_path)
        )
        if same_section_before and can_merge(merged[-1], chunk):
            merged[-1] = merge_chunks(merged[-1], chunk)
            index += 1
            continue

        same_section_after = bool(
            index + 1 < len(chunks)
            and not chunks[index + 1].is_table
            and top_level(chunks[index + 1].section_path) == top_level(chunk.section_path)
        )
        if same_section_after and can_merge(chunk, chunks[index + 1]):
            merged.append(merge_chunks(chunk, chunks[index + 1]))
            index += 2
            continue

        same_section_chunks = sum(
            top_level(candidate.section_path) == top_level(chunk.section_path)
            for candidate in chunks
        )
        if not chunk.is_heading_only and same_section_chunks == 1:
            merged.append(chunk)
        index += 1

    return merged
