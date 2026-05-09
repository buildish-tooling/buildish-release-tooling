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

"""Shared support for release-legal tests."""

from __future__ import annotations

from pathlib import Path
import unittest


class ReleaseLegalTestBase(unittest.TestCase):
    """Shared fixture writers for release-legal tests."""

    @staticmethod
    def _write_distribution(
        *,
        root: Path,
        name: str,
        version: str,
        metadata_lines: tuple[str, ...],
        record_entries: tuple[str, ...],
        file_contents: dict[str, str],
    ) -> None:
        dist_info = root / f"{name.replace('-', '_')}-{version}.dist-info"
        dist_info.mkdir(parents=True, exist_ok=True)
        (dist_info / "METADATA").write_text(
            "\n".join(metadata_lines) + "\n",
            encoding="utf-8",
        )
        (dist_info / "RECORD").write_text(
            "\n".join(record_entries) + "\n",
            encoding="utf-8",
        )
        for relative_path, text in file_contents.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    @staticmethod
    def _write_egg_info_distribution(
        *,
        root: Path,
        name: str,
        version: str,
        metadata_lines: tuple[str, ...],
    ) -> None:
        egg_info = root / f"{name.replace('-', '_')}.egg-info"
        egg_info.mkdir(parents=True, exist_ok=True)
        (egg_info / "PKG-INFO").write_text(
            "\n".join(metadata_lines) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_site_pipeline_container_legal_inputs(root: Path) -> None:
        containerfile = root / "tools" / "release-tooling-image" / "Containerfile"
        containerfile.parent.mkdir(parents=True, exist_ok=True)
        containerfile.write_text(
            "\n".join(
                (
                    "FROM ghcr.io/astral-sh/uv:0.9.7@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142 AS uvbin",
                    "FROM docker.io/library/python:3.13-bookworm@sha256:345d669f21b1ab934cb67f2015a713ec041bb2ebb8e3f069484839361f64cc53",
                    "COPY --from=uvbin /uv /bin/uv",
                    "COPY --from=uvbin /uvx /bin/uvx",
                    "",
                )
            ),
            encoding="utf-8",
        )
        manifest_path = (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-image-bundles.toml"
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            "\n".join(
                (
                    "[[bundles]]",
                    'image-ref = "docker.io/library/python:3.13-bookworm@sha256:345d669f21b1ab934cb67f2015a713ec041bb2ebb8e3f069484839361f64cc53"',
                    'name = "python"',
                    'version = "3.13-bookworm"',
                    'output-key = "python-3.13-bookworm"',
                    'home-page = "https://www.python.org/"',
                    'license-expression = "Python-2.0"',
                    'license-files = ["tools/release-tooling-image/legal/base-images/python-3.13-bookworm/LICENSE"]',
                    "",
                    "[[bundles]]",
                    'image-ref = "ghcr.io/astral-sh/uv:0.9.7@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142"',
                    'name = "uv"',
                    'version = "0.9.7"',
                    'output-key = "uv-0.9.7"',
                    'home-page = "https://docs.astral.sh/uv/"',
                    'license-expression = "Apache-2.0 OR MIT"',
                    'license-files = ["tools/release-tooling-image/legal/base-images/uv-0.9.7/LICENSE-APACHE", "tools/release-tooling-image/legal/base-images/uv-0.9.7/LICENSE-MIT"]',
                    "",
                )
            ),
            encoding="utf-8",
        )
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "python-3.13-bookworm"
        ).mkdir(
            parents=True,
            exist_ok=True,
        )
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "uv-0.9.7"
        ).mkdir(
            parents=True,
            exist_ok=True,
        )
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "python-3.13-bookworm"
            / "LICENSE"
        ).write_text("Python license text\n", encoding="utf-8")
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "uv-0.9.7"
            / "LICENSE-APACHE"
        ).write_text("Apache license text\n", encoding="utf-8")
        (
            root
            / "tools"
            / "release-tooling-image"
            / "legal"
            / "base-images"
            / "uv-0.9.7"
            / "LICENSE-MIT"
        ).write_text("MIT license text\n", encoding="utf-8")
