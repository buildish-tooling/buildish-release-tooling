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

"""Tests for optional source-bound release notes."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from pydantic import ValidationError

from buildish_release_tooling.release.candidate_release import resolve_promotion_state
from buildish_release_tooling.release.config import ReleaseConfig
from buildish_release_tooling.release.core.models import (
    MAX_RELEASE_NOTES_BYTES,
    ReleaseNotes,
    ToolingInvocationProvenance,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.manifests import CandidateManifestV1
from buildish_release_tooling.release.platforms.github.text import (
    render_candidate_release_body,
    render_direct_final_release_body,
)
from buildish_release_tooling.release.release_notes import resolve_release_notes

from tests.release.state_support import candidate_release_state
from tests.support import (
    cleanup_sandbox,
    create_build_test_sandbox,
    init_git_origin_and_clone,
    run_quiet,
)


def _candidate_config(*, notes_path: str | None) -> ReleaseConfig:
    payload: dict[str, object] = {
        "component": {
            "id": "example-project",
            "display_name": "Apache Example Project",
        },
        "source": {
            "selection": "explicit-ref-or-default-branch",
            "default_branch": "main",
            "snapshot": {"mode": "platform-generated"},
        },
        "lifecycle": {"mode": "candidate"},
        "candidate": {},
        "publication": {
            "authoritative": {
                "kind": "github-release",
                "repository": "apache/example-project",
            }
        },
    }
    if notes_path is not None:
        payload["release_notes"] = {"path_template": notes_path}
    return ReleaseConfig.model_validate(payload)


def _manifest(notes: ReleaseNotes | None) -> CandidateManifestV1:
    state = candidate_release_state()
    return CandidateManifestV1(
        release=state.release,
        candidate=state.candidate,
        source=state.source,
        release_notes=notes,
        candidate_tag=state.candidate.tag,
        source_date_epoch=state.source_date_epoch,
        tooling=ToolingInvocationProvenance(version="0.1.0"),
        created_at="2026-08-05T09:00:00Z",
    )


class ReleaseNotesTest(unittest.TestCase):
    """Verify configured notes are exact, bounded, and candidate-bound."""

    def setUp(self) -> None:
        self.sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, self.sandbox_dir)
        _origin, self.clone_dir = init_git_origin_and_clone(self.sandbox_dir)
        self.repo = GitRepository(self.clone_dir)

    def _commit_notes(self, payload: bytes) -> tuple[str, Path]:
        path = self.clone_dir / "release-notes" / "1.2.3.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        run_quiet(
            ["git", "-C", str(self.clone_dir), "add", "release-notes/1.2.3.md"],
            check=True,
        )
        run_quiet(
            ["git", "-C", str(self.clone_dir), "commit", "-m", "add release notes"],
            check=True,
        )
        return self.repo.current_head_commit(), path

    def test_absent_config_keeps_release_notes_optional(self) -> None:
        self.assertIsNone(
            resolve_release_notes(
                self.repo,
                _candidate_config(notes_path=None),
                version="1.2.3",
                commit_sha=self.repo.current_head_commit(),
            )
        )

    def test_notes_are_read_from_selected_commit_not_dirty_worktree(self) -> None:
        payload = b"A reviewed release-note fragment.\n"
        commit_sha, path = self._commit_notes(payload)
        path.write_text("Unreviewed working-tree drift.\n", encoding="utf-8")

        notes = resolve_release_notes(
            self.repo,
            _candidate_config(notes_path="release-notes/{version}.md"),
            version="1.2.3",
            commit_sha=commit_sha,
        )

        if notes is None:
            self.fail("expected configured release notes")
        self.assertEqual(payload.decode("utf-8"), notes.markdown)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), notes.sha256)
        self.assertEqual("release-notes/1.2.3.md", notes.source_path)

    def test_missing_configured_notes_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not exist"):
            resolve_release_notes(
                self.repo,
                _candidate_config(notes_path="release-notes/{version}.md"),
                version="1.2.3",
                commit_sha=self.repo.current_head_commit(),
            )

    def test_empty_invalid_utf8_and_oversized_notes_fail(self) -> None:
        cases = (
            (b" \n\t", "must not be empty"),
            (b"\xff", "valid UTF-8"),
            (b"x" * (MAX_RELEASE_NOTES_BYTES + 1), "exceeds"),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                sandbox = create_build_test_sandbox()
                self.addCleanup(cleanup_sandbox, sandbox)
                _origin, clone = init_git_origin_and_clone(sandbox)
                repo = GitRepository(clone)
                path = clone / "release-notes" / "1.2.3.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                run_quiet(
                    ["git", "-C", str(clone), "add", "release-notes/1.2.3.md"],
                    check=True,
                )
                run_quiet(
                    ["git", "-C", str(clone), "commit", "-m", "add notes"],
                    check=True,
                )
                with self.assertRaisesRegex(ValueError, message):
                    resolve_release_notes(
                        repo,
                        _candidate_config(notes_path="release-notes/{version}.md"),
                        version="1.2.3",
                        commit_sha=repo.current_head_commit(),
                    )

    def test_invalid_template_and_digest_fail_validation(self) -> None:
        for template in (
            "release-notes/current.md",
            "release-notes/{component}.md",
            "../release-notes/{version}.md",
            "/release-notes/{version}.md",
            "release-notes//{version}.md",
            "release-notes/./{version}.md",
            "release-notes/{version}.md/",
            "release-notes/{version!r}.md",
        ):
            with self.subTest(template=template):
                with self.assertRaises(ValidationError):
                    _candidate_config(notes_path=template)

        with self.assertRaisesRegex(ValidationError, "does not match"):
            ReleaseNotes(
                source_path="release-notes/1.2.3.md",
                sha256="a" * 64,
                markdown="reviewed notes\n",
            )

    def test_promotion_inherits_notes_and_rejects_config_path_drift(self) -> None:
        markdown = "Reviewed candidate notes.\n"
        notes = ReleaseNotes(
            source_path="release-notes/1.2.3.md",
            sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            markdown=markdown,
        )
        manifest = _manifest(notes)

        promotion = resolve_promotion_state(
            _candidate_config(notes_path="release-notes/{version}.md"),
            manifest,
            version="1.2.3",
            candidate_tag="v1.2.3-rc2",
            candidate_manifest_digest="a" * 64,
        )
        self.assertEqual(notes, promotion.release_notes)
        candidate_body = render_candidate_release_body(
            candidate_release_state().model_copy(update={"release_notes": notes}),
            [],
        )
        final_body = render_direct_final_release_body(promotion)
        self.assertIn(f"## Release notes\n\n{markdown}", candidate_body)
        self.assertIn(f"## Release notes\n\n{markdown}", final_body)

        with self.assertRaisesRegex(ValueError, "path does not match"):
            resolve_promotion_state(
                _candidate_config(notes_path="notes/{version}.md"),
                manifest,
                version="1.2.3",
                candidate_tag="v1.2.3-rc2",
                candidate_manifest_digest="a" * 64,
            )

        with self.assertRaisesRegex(ValueError, "missing"):
            resolve_promotion_state(
                _candidate_config(notes_path="release-notes/{version}.md"),
                _manifest(None),
                version="1.2.3",
                candidate_tag="v1.2.3-rc2",
                candidate_manifest_digest="a" * 64,
            )


if __name__ == "__main__":
    unittest.main()
