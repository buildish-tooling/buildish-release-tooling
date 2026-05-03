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

"""Structured metadata and bounded rich-text helpers for reference docs."""

from .model import ReferenceDocumentation, ReferenceMarkdown, ReferenceSection
from .rich_text import (
    ExternalLinkTarget,
    ReferenceCodeBlock,
    ReferenceCodeSpan,
    ReferenceDocError,
    ReferenceDocument,
    ReferenceEmphasis,
    ReferenceLineBreak,
    ReferenceLink,
    ReferenceList,
    ReferenceListItem,
    ReferenceParagraph,
    ReferenceStrong,
    ReferenceText,
    TypeReferenceTarget,
    parse_reference_document,
    parse_reference_link_target,
    render_reference_markdown,
    render_reference_schema_text,
)

__all__ = [
    "ExternalLinkTarget",
    "ReferenceCodeBlock",
    "ReferenceCodeSpan",
    "ReferenceDocError",
    "ReferenceDocumentation",
    "ReferenceDocument",
    "ReferenceEmphasis",
    "ReferenceLineBreak",
    "ReferenceLink",
    "ReferenceList",
    "ReferenceListItem",
    "ReferenceMarkdown",
    "ReferenceParagraph",
    "ReferenceSection",
    "ReferenceStrong",
    "ReferenceText",
    "TypeReferenceTarget",
    "parse_reference_document",
    "parse_reference_link_target",
    "render_reference_markdown",
    "render_reference_schema_text",
]