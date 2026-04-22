# Copyright 2026 The Buildish Authors
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

"""Typed reference-doc metadata attached to public contract models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .rich_text import ReferenceDocument, parse_reference_document


@dataclass(frozen=True, slots=True)
class ReferenceMarkdown:
    """Validated bounded Markdown-like fragment authored in model metadata."""

    source: str
    document: ReferenceDocument = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "document", parse_reference_document(self.source))


@dataclass(frozen=True, slots=True)
class ReferenceSection:
    """One titled section of generated reference-only notes for a contract."""

    title: str
    body: ReferenceMarkdown

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Reference section titles must not be blank.")


@dataclass(frozen=True, slots=True)
class ReferenceDocumentation:
    """Optional richer notes used only by generated reference documentation."""

    summary: ReferenceMarkdown | None = None
    sections: tuple[ReferenceSection, ...] = ()