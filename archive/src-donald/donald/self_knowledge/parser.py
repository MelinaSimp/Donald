"""Parser for the self-knowledge document's AUTO blocks.

The document interleaves hand-written prose with machine-generated
sections delimited by HTML-comment markers::

    <!-- AUTO-START: capabilities -->
    ...generated content...
    <!-- AUTO-END: capabilities -->

The parser preserves everything outside the markers byte-for-byte, so a
parse → serialize round-trip with no edits is a no-op. Replacing a
block's body never touches hand-written content elsewhere in the file.

Mixed/CRLF line endings are handled: the dominant ending is detected and
reused when rendering replacement bodies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Union

# Matches a complete, name-balanced AUTO block. DOTALL so the body can
# span lines; non-greedy body so adjacent blocks don't merge.
_BLOCK_RE = re.compile(
    r"(?P<start><!--[ \t]*AUTO-START:[ \t]*(?P<name>[\w-]+)[ \t]*-->)"
    r"(?P<body>.*?)"
    r"(?P<end><!--[ \t]*AUTO-END:[ \t]*(?P=name)[ \t]*-->)",
    re.DOTALL,
)

# Used to detect stray (unbalanced) markers left in literal text.
_STRAY_RE = re.compile(r"<!--[ \t]*AUTO-(?:START|END):[ \t]*[\w-]+[ \t]*-->")


@dataclass
class HandwrittenSpan:
    """A run of hand-written text plus its 1-based starting line in the doc."""

    text: str
    start_line: int


@dataclass
class AutoBlock:
    """One AUTO block: its name plus the exact marker/body substrings."""

    name: str
    start_marker: str
    body: str
    end_marker: str

    def render(self) -> str:
        return f"{self.start_marker}{self.body}{self.end_marker}"


class SelfKnowledgeDoc:
    """A parsed self-knowledge document.

    Internally a flat list of segments, each either a literal ``str`` or
    an :class:`AutoBlock`. Reassembling the segments reproduces the
    original text exactly.
    """

    def __init__(self, segments: List[Union[str, AutoBlock]], eol: str) -> None:
        self._segments = segments
        self.eol = eol

    # -- construction --------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> "SelfKnowledgeDoc":
        eol = "\r\n" if "\r\n" in text else "\n"
        segments: List[Union[str, AutoBlock]] = []
        seen: set = set()
        pos = 0
        for match in _BLOCK_RE.finditer(text):
            literal = text[pos : match.start()]
            cls._reject_stray(literal)
            if literal:
                segments.append(literal)
            name = match.group("name")
            if name in seen:
                raise ValueError(f"duplicate AUTO block name: {name!r}")
            seen.add(name)
            segments.append(
                AutoBlock(
                    name=name,
                    start_marker=match.group("start"),
                    body=match.group("body"),
                    end_marker=match.group("end"),
                )
            )
            pos = match.end()
        trailing = text[pos:]
        cls._reject_stray(trailing)
        if trailing:
            segments.append(trailing)
        return cls(segments, eol)

    @staticmethod
    def _reject_stray(literal: str) -> None:
        stray = _STRAY_RE.search(literal)
        if stray:
            raise ValueError(
                f"unbalanced AUTO marker (no matching START/END pair): {stray.group(0)!r}"
            )

    # -- inspection ----------------------------------------------------

    def block_names(self) -> List[str]:
        return [s.name for s in self._segments if isinstance(s, AutoBlock)]

    def iter_segments(self) -> List[Union[str, AutoBlock]]:
        """Return the ordered segments (literals and AutoBlocks)."""
        return list(self._segments)

    def handwritten_spans(self) -> List["HandwrittenSpan"]:
        """Return hand-written (non-AUTO) text spans with 1-based start lines."""
        spans: List[HandwrittenSpan] = []
        line = 1
        for seg in self._segments:
            if isinstance(seg, AutoBlock):
                line += seg.render().count("\n")
            else:
                spans.append(HandwrittenSpan(text=seg, start_line=line))
                line += seg.count("\n")
        return spans

    def _block(self, name: str) -> AutoBlock:
        for seg in self._segments:
            if isinstance(seg, AutoBlock) and seg.name == name:
                return seg
        raise KeyError(f"no AUTO block named {name!r}")

    def get_block_body(self, name: str) -> str:
        return self._block(name).body

    # -- mutation ------------------------------------------------------

    def replace_block(self, name: str, content: str) -> None:
        """Replace the inner content of the named block.

        ``content`` is the raw text to place between the markers; line
        endings are normalized to the document's dominant ending and the
        body is wrapped in single blank-free separators so the markers
        each sit on their own line.
        """
        block = self._block(name)
        normalized = self._to_eol(content.strip("\r\n"))
        block.body = self.eol + normalized + self.eol

    def _to_eol(self, text: str) -> str:
        flat = text.replace("\r\n", "\n").replace("\r", "\n")
        return self.eol.join(flat.split("\n"))

    # -- output --------------------------------------------------------

    def serialize(self) -> str:
        out = []
        for seg in self._segments:
            out.append(seg if isinstance(seg, str) else seg.render())
        return "".join(out)
