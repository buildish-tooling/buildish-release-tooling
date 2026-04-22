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
"""Tests for shared release communication text blocks."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from buildish_release_tooling.release.contracts import IncubatorDisclaimer
from buildish_release_tooling.release.config import ReleaseConfig
from buildish_release_tooling.release.release_text import (
    incubator_disclaimer_section,
    resolved_incubator_disclaimer,
)


class ReleaseTextTest(unittest.TestCase):
    """Verify policy text rendering from component configuration."""

    @staticmethod
    def _component_config(*, disclaimer_file: str = "DISCLAIMER") -> ReleaseConfig:
        payload: dict[str, object] = {
            "component": {"id": "buildish-example", "display_name": "Buildish Example"},
            "source": {
                "selection": "release-branch",
                "snapshot": {
                    "mode": "built-asset",
                    "filename_template": "apache-buildish-example-{version}-incubating-src.tar.gz",
                    "archive_root_template": "apache-buildish-example-{version}-incubating-src",
                },
                "checks": {"platform": "github", "required": ["component-ci"]},
            },
            "lifecycle": {"mode": "candidate"},
            "candidate": {"start_number": 1},
            "publication": {"authoritative": {"kind": "asf-dist-svn"}},
            "vote_materials": {
                "profile": "asf",
                "release_name": "Buildish Example",
                "verification_guide_url": "https://buildish.org/buildish-example/release-verification/",
                "instructions": "verify",
            },
            "policy_profiles": {
                "asf": {
                    "project_status": "incubating",
                    "dist_dev_base": "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
                    "dist_release_base": "https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
                    "keys_url": "https://downloads.apache.org/incubator/buildish/KEYS",
                    "disclaimer_file": disclaimer_file,
                }
            },
        }
        return ReleaseConfig.model_validate(payload)

    def test_resolved_incubator_disclaimer_reads_project_file(self) -> None:
        component_config = self._component_config()
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            (project_root / "DISCLAIMER").write_text("Approved disclaimer.\n", encoding="utf-8")

            disclaimer = resolved_incubator_disclaimer(component_config, project_root=project_root)

        if disclaimer is None:
            self.fail("expected incubating component to resolve a disclaimer")
        else:
            self.assertEqual("DISCLAIMER", disclaimer.source_path)
            self.assertEqual("Approved disclaimer.", disclaimer.text)
            self.assertEqual(128, len(disclaimer.sha512))

    def test_incubator_disclaimer_section_is_empty_for_top_level_projects(self) -> None:
        self.assertEqual("", incubator_disclaimer_section(None, heading="Disclaimer:"))

    def test_incubator_disclaimer_section_uses_manifest_text(self) -> None:
        disclaimer = IncubatorDisclaimer(
            source_path="DISCLAIMER",
            text="Approved disclaimer.",
            sha512="a" * 128,
        )

        self.assertEqual(
            "Disclaimer:\n\nApproved disclaimer.",
            incubator_disclaimer_section(disclaimer, heading="Disclaimer:"),
        )

    def test_missing_incubator_disclaimer_file_is_rejected(self) -> None:
        component_config = self._component_config()
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "incubator disclaimer file does not exist"):
                resolved_incubator_disclaimer(component_config, project_root=Path(temp_dir))

    def test_incubator_disclaimer_file_must_not_escape_project_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "disclaimer_file"):
            self._component_config(disclaimer_file="../DISCLAIMER")


if __name__ == "__main__":
    unittest.main()
