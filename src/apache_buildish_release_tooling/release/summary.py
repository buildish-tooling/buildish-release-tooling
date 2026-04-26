# Copyright 2026 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GitHub step-summary helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class SummaryWriter:
    """Markdown writer for GitHub workflow summaries."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def from_environment(cls) -> SummaryWriter:
        """Resolve the required summary path from GitHub Actions."""

        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if not summary_path:
            raise ValueError("GITHUB_STEP_SUMMARY is required")
        return cls(Path(summary_path))

    def _append(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(text)

    def append_heading(self, title: str) -> None:
        """Append a level-two heading to the summary."""

        self._append(f"## {title}\n\n")

    def append_markdown(self, markdown: str) -> None:
        """Append already-rendered Markdown content."""

        self._append(markdown)
        if not markdown.endswith("\n"):
            self._append("\n")

    def append_plaintext_block(self, title: str, content: str) -> None:
        """Append a fenced plain-text block under a level-three heading."""

        self.append_code_block(title, "text", content)

    def append_code_block(self, title: str, language: str, content: str) -> None:
        """Append a fenced code block under a level-three heading."""

        self._append(f"### {title}\n\n```{language}\n{content}\n```\n\n")

    def append_json_block(self, title: str, payload: Any) -> None:
        """Append one JSON payload as a fenced code block."""

        self.append_code_block(title, "json", json.dumps(payload, indent=2, sort_keys=True))

    def append_bullet_list(self, title: str, items: list[str]) -> None:
        """Append one Markdown bullet list under a level-three heading."""

        if not items:
            self._append(f"### {title}\n\n- <none>\n\n")
            return
        rendered_items = "\n".join(f"- {item}" for item in items)
        self._append(f"### {title}\n\n{rendered_items}\n\n")

    def append_key_value_table(self, title: str, rows: list[tuple[str, str]]) -> None:
        """Append a simple two-column Markdown table."""

        self._append(f"### {title}\n\n")
        self._append("| Field | Value |\n")
        self._append("| --- | --- |\n")
        for field, value in rows:
            self._append(
                f"| {self._escape_table_cell(field)} | {self._escape_table_cell(value)} |\n"
            )
        self._append("\n")

    def _escape_table_cell(self, text: str) -> str:
        """Escape one Markdown table cell."""

        return text.replace("|", "\\|").replace("\n", "<br>")

    def append_checksum_block(self, algorithm: str, artifact_name: str, checksum: str) -> None:
        """Append the standard checksum line for an artifact and algorithm."""

        self.append_plaintext_block(
            f"{algorithm.upper()}: {artifact_name}",
            f"{checksum}  {artifact_name}",
        )

    def append_sha512_block(self, artifact_name: str, checksum: str) -> None:
        """Append the standard SHA512 line for an artifact."""

        self.append_checksum_block("sha512", artifact_name, checksum)

    def append_signature_text_block(self, artifact_name: str, signature_text: str) -> None:
        """Append a detached ASCII-armored signature block from in-memory text."""

        self.append_plaintext_block(f"Detached signature: {artifact_name}", signature_text)

    def append_signature_block(self, artifact_name: str, signature_file: Path) -> None:
        """Append a detached ASCII-armored signature block from a `.asc` file."""

        self.append_signature_text_block(artifact_name, signature_file.read_text(encoding="utf-8"))

    def append_email_template_blocks(self, label: str, subject: str, body: str) -> None:
        """Append a subject/body pair for one human-sent email template."""

        self.append_plaintext_block(f"{label} subject", subject)
        self.append_plaintext_block(f"{label} body", body)

    def append_vote_mail_blocks(self, label: str, subject: str, body: str) -> None:
        """Append a subject/body pair for a release-vote or result email template."""

        self.append_email_template_blocks(label, subject, body)
