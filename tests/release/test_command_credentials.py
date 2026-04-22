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
"""Credential-handling tests for release command helpers."""

from tests.release.commands.support import (
    Any,
    Mapping,
    Path,
    Sequence,
    cast,
    delete_remote_ref_best_effort,
    mock,
    os,
    push_remote_ref,
    subprocess,
    unittest,
)


class CommandCredentialHandlingUnitTest(unittest.TestCase):
    """Expose credential-sensitive command tests under the release test package."""

    def test_push_remote_ref_uses_git_askpass_for_github_https_pushes(self) -> None:
        repo = mock.Mock()
        repo.path = Path("/sandbox/repo")
        repo.remote_url.return_value = "git@github.com:apache/example-project.git"
        seen_script_path: Path | None = None

        def fake_run_logged_command(
            command: Sequence[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[str]:
            nonlocal seen_script_path
            self.assertEqual(
                [
                    "git",
                    "-C",
                    "/sandbox/repo",
                    "push",
                    "https://github.com/apache/example-project.git",
                    "HEAD:refs/buildish/test",
                ],
                command,
            )
            self.assertNotIn("gh-secret-token", "".join(command))
            self.assertEqual(
                ["gh-secret-token"], cast(Sequence[str], kwargs["extra_secret_values"])
            )
            env = cast(Mapping[str, str], kwargs["env"])
            self.assertEqual("0", env["GIT_TERMINAL_PROMPT"])
            self.assertEqual("", env["GH_TOKEN"])
            self.assertEqual("", env["GITHUB_TOKEN"])
            self.assertEqual("gh-secret-token", env["BUILDISH_GIT_ASKPASS_TOKEN"])
            self.assertEqual("x-access-token", env["BUILDISH_GIT_ASKPASS_USERNAME"])
            seen_script_path = Path(env["GIT_ASKPASS"])
            self.assertTrue(seen_script_path.is_file())
            self.assertEqual(
                "\n".join(
                    [
                        "#!/bin/sh",
                        "set -eu",
                        'prompt="${1-}"',
                        'case "$prompt" in',
                        "  *Username*|*username*)",
                        "    printf '%s\\n' \"${BUILDISH_GIT_ASKPASS_USERNAME:-x-access-token}\"",
                        "    ;;",
                        "  *)",
                        "    printf '%s\\n' \"${BUILDISH_GIT_ASKPASS_TOKEN:?}\"",
                        "    ;;",
                        "esac",
                        "",
                    ]
                ),
                seen_script_path.read_text(encoding="utf-8"),
            )
            return subprocess.CompletedProcess(list(command), 0, "", "")

        with (
            mock.patch.dict(
                os.environ, {"GITHUB_TOKEN": "gh-secret-token"}, clear=False
            ),
            mock.patch(
                "buildish_release_tooling.release.git_materialization.run_logged_command",
                side_effect=fake_run_logged_command,
            ),
        ):
            actual = push_remote_ref(
                repo,
                repository_slug="apache/example-project",
                source_ref="HEAD",
                target_ref="refs/buildish/test",
                force=False,
            )

        self.assertEqual("pushed", actual)
        self.assertIsNotNone(seen_script_path)
        if seen_script_path is None:
            self.fail("expected askpass helper path to be captured")
        self.assertFalse(seen_script_path.exists())

    def test_delete_remote_ref_best_effort_uses_git_askpass_for_github_https_pushes(
        self,
    ) -> None:
        repo = mock.Mock()
        repo.path = Path("/sandbox/repo")
        repo.remote_url.return_value = "git@github.com:apache/example-project.git"
        seen_script_path: Path | None = None

        def fake_run_logged_command(
            command: Sequence[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[str]:
            nonlocal seen_script_path
            self.assertEqual(
                [
                    "git",
                    "-C",
                    "/sandbox/repo",
                    "push",
                    "https://github.com/apache/example-project.git",
                    ":refs/buildish/test",
                ],
                command,
            )
            env = cast(Mapping[str, str], kwargs["env"])
            seen_script_path = Path(env["GIT_ASKPASS"])
            self.assertTrue(seen_script_path.is_file())
            return subprocess.CompletedProcess(list(command), 0, "", "")

        with (
            mock.patch.dict(os.environ, {"GH_TOKEN": "gh-secret-token"}, clear=False),
            mock.patch(
                "buildish_release_tooling.release.git_materialization.run_logged_command",
                side_effect=fake_run_logged_command,
            ),
        ):
            actual = delete_remote_ref_best_effort(
                repo,
                repository_slug="apache/example-project",
                ref_name="refs/buildish/test",
            )

        self.assertEqual("deleted", actual)
        self.assertIsNotNone(seen_script_path)
        if seen_script_path is None:
            self.fail("expected askpass helper path to be captured")
        self.assertFalse(seen_script_path.exists())
