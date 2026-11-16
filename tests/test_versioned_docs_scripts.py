#
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

"""Exercise developer scripts using real, disposable Git repositories."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import unittest
from tempfile import TemporaryDirectory

SCRIPTS = Path(__file__).resolve().parents[1] / "tools/versioned-docs"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def run(
    repo: Path, command: str, *args: str, success: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(SCRIPTS / f"{command}.sh"), "--source", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if (result.returncode == 0) != success:
        raise AssertionError(result.stdout + result.stderr)
    return result


def commit(repo: Path) -> None:
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "fixture")


def release(repo: Path, version: str, content: str = "release docs\n") -> None:
    (repo / "docs/_index.md").write_text(content)
    commit(repo)
    git(repo, "tag", f"v{version}")


class VersionedDocsScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp_path = Path(temporary.name)
        tmp_path = self.tmp_path
        repo = tmp_path / "source with spaces"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        (repo / "docs").mkdir()
        (repo / ".gitignore").write_text("docs/releases/\n")
        release(repo, "0.1.2", "incomplete\n")
        release(repo, "0.1.3")
        git(repo, "tag", "v0.1.4-rc1")
        self.source = repo

    def test_create_import_and_incremental(self) -> None:
        source = self.source
        run(source, "checkout", "--create")
        worktree = source / "docs/releases"
        self.assertFalse((worktree / "docs").exists())
        run(source, "import")
        self.assertEqual((worktree / "0.1.3/_index.md").read_text(), "release docs\n")
        self.assertTrue((worktree / "0.1.2").is_dir())
        self.assertFalse((worktree / "0.1.4-rc1").exists())
        snapshot = json.loads((worktree / "provider-snapshot.json").read_text())
        self.assertEqual(
            next(
                record for record in snapshot["records"] if record["version"] == "0.1.3"
            )["commitSha"],
            git(source, "rev-parse", "v0.1.3^{commit}"),
        )
        # Imports are deliberately left for review, without an automatic commit.
        self.assertTrue(git(worktree, "status", "--porcelain"))
        commit(worktree)
        original = (worktree / "provider-snapshot.json").read_bytes()
        run(source, "import")
        self.assertEqual((worktree / "provider-snapshot.json").read_bytes(), original)
        release(source, "0.1.4", "new docs\n")
        run(source, "import")
        self.assertEqual((worktree / "0.1.3/_index.md").read_text(), "release docs\n")
        self.assertEqual((worktree / "0.1.4/_index.md").read_text(), "new docs\n")
        self.assertFalse(git(source, "status", "--porcelain"))

    def test_dirty_refused_and_full_rebuild_scope(self) -> None:
        source = self.source
        run(source, "checkout", "--create")
        worktree = source / "docs/releases"
        run(source, "import", "--version", "0.1.2", "--version", "0.1.3")
        commit(worktree)
        (worktree / "README.md").write_text("Keep this\n")
        run(source, "import", "--full-rebuild", success=False)
        commit(worktree)
        run(source, "import", "--full-rebuild", "--version", "0.1.3")
        self.assertTrue((worktree / "0.1.2").is_dir())
        self.assertTrue((worktree / "0.1.3/_index.md").is_file())
        self.assertEqual((worktree / "README.md").read_text(), "Keep this\n")

    def test_curated_metadata_survives_incremental_and_full_rebuild(self) -> None:
        source = self.source
        run(source, "checkout", "--create")
        worktree = source / "docs/releases"
        run(source, "import")
        path = worktree / "provider-snapshot.json"
        snapshot = json.loads(path.read_text())
        withdrawn = snapshot["records"][0]
        self.assertEqual(withdrawn["version"], "0.1.2")
        withdrawn["publicationState"] = "withdrawn"
        withdrawn["supportStatus"] = "unsupported"
        withdrawn["urls"] = {"explanation": "https://example.org/incomplete-release"}
        path.write_text(json.dumps(snapshot, indent=2) + "\n")
        # Rebuild restores docs, while retaining the curated inventory entry.
        (worktree / "0.1.2/_index.md").write_text("manual docs change\n")
        commit(worktree)
        release(source, "0.1.4", "new docs\n")
        for options in (
            (),
            ("--full-rebuild", "--version", "0.1.3"),
            ("--full-rebuild",),
        ):
            with self.subTest(options=options):
                run(source, "import", *options)
                current = json.loads(path.read_text())
                self.assertEqual(current["records"][0], withdrawn)
                self.assertEqual(len(current["records"]), 3)
                if git(worktree, "status", "--porcelain"):
                    commit(worktree)
        self.assertEqual((worktree / "0.1.2/_index.md").read_text(), "incomplete\n")

    def test_optional_minimum_version_filters_discovery(self) -> None:
        source = self.source
        run(source, "checkout", "--create")
        run(source, "import", "--minimum-version", "0.1.3")
        self.assertFalse((source / "docs/releases/0.1.2").exists())

    def test_invalid_export_does_not_remove_existing_docs(self) -> None:
        source = self.source
        run(source, "checkout", "--create")
        worktree = source / "docs/releases"
        run(source, "import")
        commit(worktree)
        (source / "docs/_index.md").unlink()
        commit(source)
        git(source, "tag", "v0.1.4")
        run(source, "import", "--full-rebuild", success=False)
        self.assertTrue((worktree / "0.1.3/_index.md").is_file())
        self.assertFalse(git(worktree, "status", "--porcelain"))

    def test_changed_tag_and_unowned_directory_refused(self) -> None:
        source = self.source
        run(source, "checkout", "--create")
        worktree = source / "docs/releases"
        run(source, "import")
        commit(worktree)
        git(source, "tag", "-f", "v0.1.3", "v0.1.2")
        result = run(source, "import", success=False)
        self.assertIn("Tag changed", result.stderr)
        (worktree / "0.1.4").mkdir()
        (worktree / "0.1.4/_index.md").write_text("hand authored\n")
        commit(worktree)
        release(source, "0.1.4", "real docs\n")
        result = run(source, "import", "--version", "0.1.4", success=False)
        self.assertIn("unowned", result.stderr)
        self.assertEqual((worktree / "0.1.4/_index.md").read_text(), "hand authored\n")

    def test_checkout_remote_update_and_divergence(self) -> None:
        source = self.source
        tmp_path = self.tmp_path
        # This local repository plays the role of the HTTPS remote; no network used.
        remote = tmp_path / "remote"
        git(tmp_path, "clone", str(source), str(remote))
        run(remote, "checkout", "--create")
        remote_docs = remote / "docs/releases"
        (remote_docs / "README.md").write_text("first\n")
        commit(remote_docs)
        run(source, "checkout", "--remote", str(remote))
        worktree = source / "docs/releases"
        self.assertEqual((worktree / "README.md").read_text(), "first\n")
        (remote_docs / "README.md").write_text("second\n")
        commit(remote_docs)
        run(source, "update", "--remote", str(remote))
        self.assertEqual((worktree / "README.md").read_text(), "second\n")
        (worktree / "README.md").write_text("local\n")
        run(source, "update", "--remote", str(remote), success=False)
        commit(worktree)
        (remote_docs / "README.md").write_text("third\n")
        commit(remote_docs)
        head = git(worktree, "rev-parse", "HEAD")
        run(source, "update", "--remote", str(remote), success=False)
        self.assertEqual(git(worktree, "rev-parse", "HEAD"), head)
        self.assertEqual((worktree / "README.md").read_text(), "local\n")

    def test_rejects_symlink_docs_and_wrong_worktree(self) -> None:
        source = self.source
        run(source, "checkout", "--create")
        run(source, "import", "--worktree", str(source), success=False)
        (source / "docs/link").symlink_to("/etc/passwd")
        release(source, "0.1.4", "new docs\n")
        result = run(source, "import", success=False)
        self.assertIn("symlink", result.stderr)
        self.assertFalse((source / "docs/releases/0.1.3").exists())
