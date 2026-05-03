# Copyright 2026 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Bounded rich-text parsing for generated reference documentation.

The model layer remains the source of truth, but maintainers still need
ergonomic authoring. This module therefore accepts a small Markdown-like subset,
validates it aggressively, and converts it into typed nodes that renderers can
target deterministically.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import re
from typing import cast
from urllib.parse import urlparse

from mistletoe import Document
from mistletoe import block_token, span_token

_SYMBOLIC_TYPE_TARGET = re.compile(
    r"^type:(?P<type_name>[A-Za-z][A-Za-z0-9_]*)(?:#(?P<field_name>[A-Za-z][A-Za-z0-9_]*))?$"
)


class ReferenceDocError(ValueError):
    """Raised when authored reference-doc markup violates the supported subset."""


@dataclass(frozen=True, slots=True)
class TypeReferenceTarget:
    """Stable symbolic link target for one generated reference type or field."""

    type_name: str
    field_name: str | None = None

    @property
    def symbolic_target(self) -> str:
        return f"type:{self.type_name}" if self.field_name is None else f"type:{self.type_name}#{self.field_name}"

    @property
    def plain_text_label(self) -> str:
        return self.type_name if self.field_name is None else f"{self.type_name}.{self.field_name}"


@dataclass(frozen=True, slots=True)
class ExternalLinkTarget:
    """Validated external reference URL allowed in authored docs."""

    url: str


ReferenceLinkTarget = TypeReferenceTarget | ExternalLinkTarget


@dataclass(frozen=True, slots=True)
class ReferenceText:
    value: str


@dataclass(frozen=True, slots=True)
class ReferenceCodeSpan:
    value: str


@dataclass(frozen=True, slots=True)
class ReferenceEmphasis:
    children: tuple[ReferenceInlineNode, ...]


@dataclass(frozen=True, slots=True)
class ReferenceStrong:
    children: tuple[ReferenceInlineNode, ...]


@dataclass(frozen=True, slots=True)
class ReferenceLineBreak:
    pass


@dataclass(frozen=True, slots=True)
class ReferenceLink:
    label: tuple[ReferenceInlineNode, ...]
    target: ReferenceLinkTarget


ReferenceInlineNode = (
    ReferenceText | ReferenceCodeSpan | ReferenceEmphasis | ReferenceStrong | ReferenceLineBreak | ReferenceLink
)


@dataclass(frozen=True, slots=True)
class ReferenceParagraph:
    children: tuple[ReferenceInlineNode, ...]


@dataclass(frozen=True, slots=True)
class ReferenceCodeBlock:
    language: str
    code: str


@dataclass(frozen=True, slots=True)
class ReferenceListItem:
    blocks: tuple[ReferenceBlockNode, ...]


@dataclass(frozen=True, slots=True)
class ReferenceList:
    ordered: bool
    items: tuple[ReferenceListItem, ...]


ReferenceBlockNode = ReferenceParagraph | ReferenceCodeBlock | ReferenceList


@dataclass(frozen=True, slots=True)
class ReferenceDocument:
    blocks: tuple[ReferenceBlockNode, ...]


TypeTargetResolver = Callable[[TypeReferenceTarget], str]


def parse_reference_document(source: str) -> ReferenceDocument:
    """Parse one bounded Markdown-like fragment into typed rich-text nodes."""

    if not source.strip():
        raise ReferenceDocError("Reference documentation fragments must not be blank.")
    document = Document(source)
    return ReferenceDocument(blocks=tuple(_convert_block_token(child) for child in _block_children(document)))


def render_reference_markdown(
    document: ReferenceDocument,
    *,
    resolve_type_target: TypeTargetResolver | None = None,
) -> str:
    """Render rich-text nodes back to deterministic Markdown output."""

    return "\n\n".join(
        _render_block_markdown(block, resolve_type_target=resolve_type_target) for block in document.blocks
    )


def render_reference_schema_text(document: ReferenceDocument) -> str:
    """Render rich-text nodes into schema-safe human-readable prose."""

    return "\n\n".join(_render_block_schema_text(block) for block in document.blocks)


def parse_reference_link_target(target: str) -> ReferenceLinkTarget:
    """Parse and validate one authored link target."""

    symbolic_match = _SYMBOLIC_TYPE_TARGET.fullmatch(target)
    if symbolic_match is not None:
        return TypeReferenceTarget(
            type_name=symbolic_match.group("type_name"),
            field_name=symbolic_match.group("field_name"),
        )
    parsed_url = urlparse(target)
    if parsed_url.scheme == "https" and parsed_url.netloc:
        return ExternalLinkTarget(url=target)
    raise ReferenceDocError(f"Unsupported or unsafe link target: {target!r}")


def _convert_block_token(token: block_token.BlockToken) -> ReferenceBlockNode:
    if isinstance(token, block_token.Paragraph):
        return ReferenceParagraph(children=_convert_span_children(_span_children(token)))
    if isinstance(token, block_token.List):
        return ReferenceList(
            ordered=bool(token.start is not None),
            items=tuple(
                ReferenceListItem(blocks=tuple(_convert_block_token(child) for child in _block_children(item)))
                for item in _block_children(token)
            ),
        )
    if isinstance(token, block_token.CodeFence):
        if token.language is None or not token.language.strip():
            raise ReferenceDocError("Reference code fences must declare a language tag.")
        return ReferenceCodeBlock(
            language=token.language.strip(),
            code=_first_raw_text_child(token).content.rstrip("\n"),
        )
    raise ReferenceDocError(f"Unsupported block token in reference docs: {type(token).__name__}")


def _convert_span_children(children: tuple[span_token.SpanToken, ...]) -> tuple[ReferenceInlineNode, ...]:
    return tuple(_convert_span_token(child) for child in children)


def _convert_span_token(token: span_token.SpanToken) -> ReferenceInlineNode:
    if isinstance(token, span_token.RawText):
        return ReferenceText(value=token.content)
    if isinstance(token, span_token.InlineCode):
        return ReferenceCodeSpan(value=_render_raw_text_children(_span_children(token)))
    if isinstance(token, span_token.Emphasis):
        return ReferenceEmphasis(children=_convert_span_children(_span_children(token)))
    if isinstance(token, span_token.Strong):
        return ReferenceStrong(children=_convert_span_children(_span_children(token)))
    if isinstance(token, span_token.Link):
        return ReferenceLink(
            label=_convert_span_children(_span_children(token)),
            target=parse_reference_link_target(token.target),
        )
    if isinstance(token, span_token.EscapeSequence):
        return ReferenceText(value=_render_raw_text_children(_span_children(token)))
    if isinstance(token, span_token.LineBreak):
        return ReferenceLineBreak()
    raise ReferenceDocError(f"Unsupported inline token in reference docs: {type(token).__name__}")


def _render_raw_text_children(children: tuple[span_token.SpanToken, ...]) -> str:
    parts: list[str] = []
    for child in children:
        if not isinstance(child, span_token.RawText):
            raise ReferenceDocError(f"Expected raw text content, got {type(child).__name__}")
        parts.append(child.content)
    return "".join(parts)


def _block_children(token: object) -> tuple[block_token.BlockToken, ...]:
    children = cast(Iterable[object] | None, getattr(token, "children", None))
    return tuple(cast(block_token.BlockToken, child) for child in children or ())


def _span_children(token: object) -> tuple[span_token.SpanToken, ...]:
    children = cast(Iterable[object] | None, getattr(token, "children", None))
    return tuple(cast(span_token.SpanToken, child) for child in children or ())


def _first_raw_text_child(token: block_token.CodeFence) -> span_token.RawText:
    children = _span_children(token)
    if not children or not isinstance(children[0], span_token.RawText):
        raise ReferenceDocError("Reference code fences must contain raw text content.")
    return children[0]


def _render_block_markdown(block: ReferenceBlockNode, *, resolve_type_target: TypeTargetResolver | None) -> str:
    if isinstance(block, ReferenceParagraph):
        return _render_inline_markdown(block.children, resolve_type_target=resolve_type_target)
    if isinstance(block, ReferenceCodeBlock):
        return f"```{block.language}\n{block.code}\n```"
    if isinstance(block, ReferenceList):
        return "\n".join(
            _render_list_item_markdown(index=index, item=item, ordered=block.ordered, resolve_type_target=resolve_type_target)
            for index, item in enumerate(block.items, start=1)
        )
    raise AssertionError(f"Unexpected block node: {block!r}")


def _render_list_item_markdown(
    *,
    index: int,
    item: ReferenceListItem,
    ordered: bool,
    resolve_type_target: TypeTargetResolver | None,
) -> str:
    marker = f"{index}. " if ordered else "- "
    joined = "\n\n".join(
        _render_block_markdown(block, resolve_type_target=resolve_type_target) for block in item.blocks
    ).splitlines()
    return "\n".join([marker + joined[0], *[f"  {line}" if line else "" for line in joined[1:]]])


def _render_inline_markdown(
    nodes: tuple[ReferenceInlineNode, ...],
    *,
    resolve_type_target: TypeTargetResolver | None,
) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, ReferenceText):
            parts.append(node.value)
        elif isinstance(node, ReferenceCodeSpan):
            parts.append(f"`{node.value}`")
        elif isinstance(node, ReferenceEmphasis):
            parts.append(f"*{_render_inline_markdown(node.children, resolve_type_target=resolve_type_target)}*")
        elif isinstance(node, ReferenceStrong):
            parts.append(f"**{_render_inline_markdown(node.children, resolve_type_target=resolve_type_target)}**")
        elif isinstance(node, ReferenceLineBreak):
            parts.append("\\\n")
        elif isinstance(node, ReferenceLink):
            label = _render_inline_markdown(node.label, resolve_type_target=resolve_type_target)
            target = _render_markdown_target(node.target, resolve_type_target=resolve_type_target)
            parts.append(f"[{label}]({target})")
        else:
            raise AssertionError(f"Unexpected inline node: {node!r}")
    return "".join(parts)


def _render_markdown_target(
    target: ReferenceLinkTarget,
    *,
    resolve_type_target: TypeTargetResolver | None,
) -> str:
    if isinstance(target, ExternalLinkTarget):
        return target.url
    return target.symbolic_target if resolve_type_target is None else resolve_type_target(target)


def _render_block_schema_text(block: ReferenceBlockNode) -> str:
    if isinstance(block, ReferenceParagraph):
        return _render_inline_schema_text(block.children)
    if isinstance(block, ReferenceCodeBlock):
        return f"[{block.language} code]\n{block.code}"
    if isinstance(block, ReferenceList):
        lines: list[str] = []
        for index, item in enumerate(block.items, start=1):
            marker = f"{index}. " if block.ordered else "- "
            rendered = "\n\n".join(_render_block_schema_text(child) for child in item.blocks).splitlines()
            lines.append(marker + rendered[0])
            lines.extend(f"  {line}" if line else "" for line in rendered[1:])
        return "\n".join(lines)
    raise AssertionError(f"Unexpected block node: {block!r}")


def _render_inline_schema_text(nodes: tuple[ReferenceInlineNode, ...]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, ReferenceText):
            parts.append(node.value)
        elif isinstance(node, ReferenceCodeSpan):
            parts.append(f"`{node.value}`")
        elif isinstance(node, (ReferenceEmphasis, ReferenceStrong)):
            parts.append(_render_inline_schema_text(node.children))
        elif isinstance(node, ReferenceLineBreak):
            parts.append("\n")
        elif isinstance(node, ReferenceLink):
            label = _render_inline_schema_text(node.label)
            parts.append(
                f"{label} ({node.target.url})"
                if isinstance(node.target, ExternalLinkTarget)
                else f"{label} ({node.target.plain_text_label})"
            )
        else:
            raise AssertionError(f"Unexpected inline node: {node!r}")
    return "".join(parts)