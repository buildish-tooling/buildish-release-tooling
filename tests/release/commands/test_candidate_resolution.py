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

"""Provider-neutral candidate resolution integration tests."""

from __future__ import annotations

import json
import unittest
from typing import Any

from tests.support import (
    cleanup_sandbox,
    cli_env,
    create_build_test_sandbox,
    git_create_annotated_tag,
    init_git_origin_and_clone,
    run_cli,
    set_github_origin_url,
)


class CandidateResolutionIntegrationTest(unittest.TestCase):
    """Verify candidate numbering without ASF or built-source requirements."""

    def setUp(self) -> None:
        self.sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, self.sandbox_dir)
        _origin_dir, self.clone_dir = init_git_origin_and_clone(self.sandbox_dir)
        set_github_origin_url(self.clone_dir, "apache/example-project")
        self.config_path = self.sandbox_dir / "release-config.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    "component:",
                    "  id: example-project",
                    "  display_name: Apache Example Project",
                    "source:",
                    "  selection: explicit-ref-or-default-branch",
                    "  default_branch: main",
                    "  snapshot:",
                    "    mode: platform-generated",
                    "lifecycle:",
                    "  mode: candidate",
                    "candidate:",
                    "  label: rc",
                    "  start_number: 1",
                    "  visibility: public-prerelease",
                    "  retention: retain-published",
                    "publication:",
                    "  authoritative:",
                    "    kind: github-release",
                    "    repository: apache/example-project",
                    "policy_profiles: {}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _resolve(self, filename: str, *extra_args: str) -> dict[str, Any]:
        result_path = self.sandbox_dir / filename
        completed = run_cli(
            [
                "resolve-candidate",
                *extra_args,
                "--component-config",
                str(self.config_path),
                "1.2.3",
            ],
            cwd=self.clone_dir,
            env=cli_env(result_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        return json.loads(result_path.read_text(encoding="utf-8"))

    def test_default_candidate_starts_at_one_and_has_no_asf_state(self) -> None:
        state = self._resolve("candidate-1.json")

        self.assertEqual("v1.2.3-rc1", state["candidate"]["tag"]["name"])
        self.assertEqual([], state["publications"])
        self.assertNotIn("source_artifact", state)
        self.assertNotIn("asf", json.dumps(state).lower())

    def test_follow_up_candidate_uses_next_retained_tag_number(self) -> None:
        git_create_annotated_tag(self.clone_dir, "v1.2.3-rc1")

        state = self._resolve("candidate-2.json")

        self.assertEqual(2, state["candidate"]["number"])
        self.assertEqual("v1.2.3-rc2", state["candidate"]["tag"]["name"])

    def test_candidate_label_can_be_selected_explicitly(self) -> None:
        state = self._resolve("preview-1.json", "--candidate-label", "preview")

        self.assertEqual("preview", state["candidate"]["label"])
        self.assertEqual("v1.2.3-preview1", state["candidate"]["tag"]["name"])


if __name__ == "__main__":
    unittest.main()
