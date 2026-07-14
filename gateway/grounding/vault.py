"""A minimal client-owned-data Vault + a citation provider backed by it.

The north-star describes the Vault as "a client-owned-data sandbox that pulls
data on demand rather than warehousing it" — the store the anti-hallucination
guardrail verifies citations against. Donald had the guardrail
(:mod:`citation_validator`) but no Vault to back it, so verification ran
trace-only. This module gives it a real, dependency-free backing store.

Two pieces:

* :func:`chunk_text_with_pages` — page-, line-, and char-aware chunking, ported
  from Drift's ``lib/vault/chunking.ts``. Pure; the same normalization the
  source viewer uses, so a stored ``(page, line_start..line_end)`` maps to the
  exact lines a viewer would highlight.
* :class:`Vault` — a tiny document store (in-memory, or JSON files under a
  directory) that ingests documents as page arrays and chunks them. Mirrors
  Drift's ``vault_items`` + ``vault_item_chunks`` schema without a database.
* :class:`VaultCitationContextProvider` — adapts the Vault to the validator's
  :class:`CitationContextProvider` protocol, so ``[v1]`` citations verify
  against real ingested documents (quote match, page bounds → strong /
  confirmed / provenance / page_mismatch).

Memory and regulatory lookups return empty here — the Vault is document-only.
Compose additional providers when Donald grows those corpora.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Union

from .citation_validator import VaultChunk, VaultDoc

# ── Chunking (ported from lib/vault/chunking.ts) ─────────────────────

CHUNK_WORDS = 500
CHUNK_OVERLAP = 50
MAX_CHUNKS_PER_ITEM = 800  # safety: ~400k words
MAX_CHUNK_CHARS = 3000  # dense tabular data tokenizes at ~2 chars/token


def normalize_page_text(s: str) -> str:
    """Normalize page text: CRLF/CR → LF, non-breaking space → space."""
    return re.sub(r"\r\n?", "\n", s or "").replace(" ", " ")


@dataclass
class ChunkWithProvenance:
    content: str
    page_number: Optional[int] = None  # 1-based primary page
    line_start: Optional[int] = None  # 1-based within the primary page
    line_end: Optional[int] = None
    char_start: Optional[int] = None  # 0-based within the primary page
    char_end: Optional[int] = None  # exclusive


@dataclass
class _WordEntry:
    word: str
    page: int
    cs: int
    ce: int


def _count_newlines(s: str, end: int) -> int:
    return s.count("\n", 0, min(end, len(s)))


def chunk_text_with_pages(pages: Sequence[str]) -> list[ChunkWithProvenance]:
    """Chunk per-page text into overlapping, page-/line-aware chunks.

    A chunk that spans a page boundary is assigned the page it started on, and
    its char/line span covers the portion on that primary page.
    """
    if len(pages) == 0:
        return []

    page_texts = [normalize_page_text(p or "") for p in pages]

    word_entries: list[_WordEntry] = []
    for p, t in enumerate(page_texts):
        for m in re.finditer(r"\S+", t):
            word_entries.append(_WordEntry(m.group(0), p + 1, m.start(), m.end()))
    if len(word_entries) == 0:
        return []

    def prov_for(slice_: list[_WordEntry]) -> ChunkWithProvenance:
        page = slice_[0].page
        cs = slice_[0].cs
        ce = slice_[0].ce
        for e in slice_:
            if e.page != page:
                break
            ce = e.ce
        t = page_texts[page - 1] if page - 1 < len(page_texts) else ""
        return ChunkWithProvenance(
            content=" ".join(e.word for e in slice_),
            page_number=page,
            char_start=cs,
            char_end=ce,
            line_start=_count_newlines(t, cs) + 1,
            line_end=_count_newlines(t, max(cs, ce - 1)) + 1,
        )

    raw_chunks: list[ChunkWithProvenance] = []
    if len(word_entries) <= CHUNK_WORDS:
        raw_chunks.append(prov_for(word_entries))
    else:
        stride = CHUNK_WORDS - CHUNK_OVERLAP
        for i in range(0, len(word_entries), stride):
            slice_ = word_entries[i : i + CHUNK_WORDS]
            if len(slice_) == 0:
                break
            raw_chunks.append(prov_for(slice_))
            if len(raw_chunks) >= MAX_CHUNKS_PER_ITEM:
                break
            if i + CHUNK_WORDS >= len(word_entries):
                break

    # Split any chunk over the char limit; sub-splits inherit provenance.
    chunks: list[ChunkWithProvenance] = []
    for c in raw_chunks:
        if len(c.content) <= MAX_CHUNK_CHARS:
            chunks.append(c)
        else:
            for off in range(0, len(c.content), MAX_CHUNK_CHARS):
                sub = ChunkWithProvenance(**{**asdict(c), "content": c.content[off : off + MAX_CHUNK_CHARS]})
                chunks.append(sub)
        if len(chunks) >= MAX_CHUNKS_PER_ITEM:
            break

    return chunks


# ── Vault store ──────────────────────────────────────────────────────

@dataclass
class VaultDocument:
    """One ingested document (a Drift ``vault_items`` row + its chunks)."""

    document_id: str
    title: str
    chunks: list[ChunkWithProvenance] = field(default_factory=list)

    @property
    def page_count(self) -> Optional[int]:
        pages = [c.page_number for c in self.chunks if c.page_number is not None]
        return max(pages) if pages else None


class Vault:
    """A tiny client-owned document store.

    In-memory by default; pass ``root`` to persist each document as a JSON file
    under that directory (one file per ``document_id``), so a session's Vault
    survives a restart. This is deliberately minimal — no embeddings, no
    warehousing — matching the "pull on demand" posture of the north-star.
    """

    def __init__(self, root: Optional[Union[str, Path]] = None) -> None:
        self.root = Path(root) if root is not None else None
        self._mem: dict[str, VaultDocument] = {}
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)

    # -- ingest / read ----------------------------------------------------
    def ingest(self, document_id: str, title: str, pages: Sequence[str]) -> VaultDocument:
        """Chunk ``pages`` and store them under ``document_id``."""
        doc = VaultDocument(
            document_id=document_id,
            title=title,
            chunks=chunk_text_with_pages(pages),
        )
        if self.root is not None:
            self._path(document_id).write_text(
                json.dumps(
                    {
                        "document_id": doc.document_id,
                        "title": doc.title,
                        "chunks": [asdict(c) for c in doc.chunks],
                    }
                ),
                encoding="utf-8",
            )
        else:
            self._mem[document_id] = doc
        return doc

    def get(self, document_id: str) -> Optional[VaultDocument]:
        if self.root is not None:
            path = self._path(document_id)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return VaultDocument(
                document_id=data["document_id"],
                title=data.get("title", "(untitled)"),
                chunks=[ChunkWithProvenance(**c) for c in data.get("chunks", [])],
            )
        return self._mem.get(document_id)

    def document_ids(self) -> list[str]:
        if self.root is not None:
            return sorted(p.stem for p in self.root.glob("*.json"))
        return sorted(self._mem)

    def _path(self, document_id: str) -> Path:
        assert self.root is not None
        # Keep filenames filesystem-safe without inventing an id scheme.
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", document_id)
        return self.root / f"{safe}.json"


# ── Provider adapter ─────────────────────────────────────────────────

class VaultCitationContextProvider:
    """Adapt a :class:`Vault` to the validator's ``CitationContextProvider``.

    Only vault (document) citations are verified against the store; memory and
    regulatory lookups return empty (the Vault is document-only). Pass an
    instance to :func:`validate_citations` / :func:`grounding_for_turn` to move
    from trace-only to real document verification.
    """

    def __init__(self, vault: Vault) -> None:
        self.vault = vault

    def fetch_vault_context(self, document_ids: Sequence[str]) -> dict[str, VaultDoc]:
        out: dict[str, VaultDoc] = {}
        for doc_id in document_ids:
            doc = self.vault.get(doc_id)
            if doc is None:
                continue
            out[doc_id] = VaultDoc(
                page_count=doc.page_count,
                chunks=[
                    VaultChunk(page_number=c.page_number, content=c.content)
                    for c in doc.chunks
                ],
            )
        return out

    def fetch_memory_context(self, short_ids: Sequence[str]) -> dict:
        return {}

    def fetch_regulatory_context(self, reg_keys: Sequence[str]) -> dict:
        return {}
