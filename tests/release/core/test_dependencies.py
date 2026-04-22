# Copyright 2026 The Buildish Authors
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

"""Dependency-direction tests for the provider-neutral release core."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

_FORBIDDEN_PACKAGE_SEGMENTS = frozenset(
    {
        "commands",
        "foundations",
        "harness",
        "platforms",
        "signing",
    }
)
_FORBIDDEN_LEGACY_MODULES = frozenset(
    {
        "asf_svn",
        "dockerhub",
        "gpg_signing",
    }
)


def _imported_module_names(source_path: Path) -> tuple[str, ...]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imported.append(node.module)
            imported.extend(alias.name for alias in node.names)
    return tuple(imported)


def _is_adapter_import(module_name: str) -> bool:
    segments = module_name.split(".")
    return (
        bool(_FORBIDDEN_PACKAGE_SEGMENTS.intersection(segments))
        or bool(_FORBIDDEN_LEGACY_MODULES.intersection(segments))
        or any(segment.startswith("github_") for segment in segments)
    )


class CoreDependencyTest(unittest.TestCase):
    """Keep provider and foundation adapters out of the release core."""

    def test_core_does_not_import_adapter_implementations(self) -> None:
        repository_root = Path(__file__).resolve().parents[3]
        core_root = (
            repository_root
            / "src"
            / "buildish_release_tooling"
            / "release"
            / "core"
        )
        violations = {
            str(source_path.relative_to(repository_root)): sorted(
                module_name
                for module_name in _imported_module_names(source_path)
                if _is_adapter_import(module_name)
            )
            for source_path in sorted(core_root.glob("*.py"))
        }
        violations = {
            source_path: module_names
            for source_path, module_names in violations.items()
            if module_names
        }

        self.assertEqual({}, violations)


if __name__ == "__main__":
    unittest.main()
