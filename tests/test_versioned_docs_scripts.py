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

    def test_import_records_source_without_inventing_latest_policy(self) -> None:
        run(self.source, "checkout", "--create")
        run(self.source, "import")
        snapshot = json.loads(
            (self.source / "docs/releases/provider-snapshot.json").read_text()
        )
        self.assertEqual(
            [{"componentSlug": "release-tooling", "artifactKey": "release-tooling"}],
            snapshot["artifacts"],
        )
        for record in snapshot["records"]:
            self.assertNotIn("releaseLine", record)
            self.assertEqual(
                {
                    "repository": "https://github.com/buildish-tooling/buildish-release-tooling",
                    "root": "docs",
                    "ref": record["commitSha"],
                },
                record["docsSource"],
            )

    def test_import_into_artifact_only_inventory_preserves_explicit_policy(
        self,
    ) -> None:
        run(self.source, "checkout", "--create")
        worktree = self.source / "docs/releases"
        path = worktree / "provider-snapshot.json"
        policy = {
            "componentSlug": "release-tooling",
            "artifactKey": "release-tooling",
            "latestStable": "0.1.3",
            "releaseLines": [{"key": "0.1", "latest": "0.1.3"}],
        }
        path.write_text(json.dumps({"schemaVersion": 1, "artifacts": [policy]}))
        commit(worktree)
        run(self.source, "import", "--release-line", "0.1")
        snapshot = json.loads(path.read_text())
        self.assertEqual([policy], snapshot["artifacts"])
        self.assertEqual(2, len(snapshot["records"]))
        self.assertEqual("release-tooling-tags", snapshot["providers"][0]["key"])
        self.assertTrue(
            all(record["releaseLine"] == "0.1" for record in snapshot["records"])
        )

    def test_curated_line_graph_and_latest_survive_import_and_rebuild(self) -> None:
        run(self.source, "checkout", "--create")
        run(self.source, "import")
        worktree = self.source / "docs/releases"
        path = worktree / "provider-snapshot.json"
        snapshot = json.loads(path.read_text())
        policy = snapshot["artifacts"][0]
        policy.update(
            {
                "latestStable": "0.1.3",
                "releaseLines": [
                    {"key": "0", "latest": "0.1.3"},
                    {"key": "0.1", "parent": "0", "latest": "0.1.3"},
                ],
            }
        )
        for record in snapshot["records"]:
            record["releaseLine"] = "0.1"
        snapshot["records"][0]["publicationState"] = "hidden"
        hidden = snapshot["records"][0]
        path.write_text(json.dumps(snapshot))
        commit(worktree)
        release(self.source, "0.1.4", "new release\n")
        for options in (("--release-line", "0.1"), ("--full-rebuild",)):
            with self.subTest(options=options):
                run(self.source, "import", *options)
                current = json.loads(path.read_text())
                self.assertEqual(policy, current["artifacts"][0])
                self.assertEqual(hidden, current["records"][0])
                self.assertEqual("0.1", current["records"][-1]["releaseLine"])
                commit(worktree)
        original = path.read_bytes()
        for line in ("missing", "0"):
            result = run(
                self.source,
                "import",
                "--version",
                "0.1.3",
                "--release-line",
                line,
                success=False,
            )
            self.assertIn("release line", result.stderr)
            self.assertEqual(original, path.read_bytes())

    def test_legacy_migration_audits_bytes_and_preserves_curated_records(self) -> None:
        run(self.source, "checkout", "--create")
        run(self.source, "import")
        worktree = self.source / "docs/releases"
        path = worktree / "provider-snapshot.json"
        legacy = json.loads(path.read_text())
        del legacy["artifacts"]
        for record in legacy["records"]:
            del record["docsSource"]
        legacy["records"][0]["publicationState"] = "hidden"
        legacy["records"][0]["urls"] = {"explanation": "https://example.org/history"}
        path.write_text(json.dumps(legacy))
        commit(worktree)
        docs = {
            file.relative_to(worktree): file.read_bytes()
            for file in worktree.glob("*/_index.md")
        }
        run(self.source, "import", "--migrate")
        migrated = json.loads(path.read_text())
        self.assertEqual(legacy["providers"], migrated["providers"])
        for old, new in zip(legacy["records"], migrated["records"], strict=True):
            self.assertEqual(
                old, {key: value for key, value in new.items() if key != "docsSource"}
            )
            self.assertEqual(old["commitSha"], new["docsSource"]["ref"])
        for relative, content in docs.items():
            self.assertEqual(content, (worktree / relative).read_bytes())
        commit(worktree)
        original = path.read_bytes()
        run(self.source, "import", "--migrate")
        self.assertEqual(original, path.read_bytes())

    def test_migration_rejects_changed_or_extra_docs_before_metadata_writes(
        self,
    ) -> None:
        run(self.source, "checkout", "--create")
        run(self.source, "import")
        worktree = self.source / "docs/releases"
        path = worktree / "provider-snapshot.json"
        snapshot = json.loads(path.read_text())
        for record in snapshot["records"]:
            del record["docsSource"]
        path.write_text(json.dumps(snapshot))
        original_docs = (worktree / "0.1.3/_index.md").read_bytes()
        for case in ("changed", "extra"):
            with self.subTest(case=case):
                if case == "changed":
                    (worktree / "0.1.3/_index.md").write_text("curated docs\n")
                else:
                    (worktree / "0.1.3/_index.md").write_bytes(original_docs)
                    (worktree / "0.1.3/extra.md").write_text("extra file\n")
                commit(worktree)
                original = path.read_bytes()
                result = run(self.source, "import", "--migrate", success=False)
                self.assertIn("cannot add docsSource", result.stderr)
                self.assertEqual(original, path.read_bytes())
                self.assertFalse(git(worktree, "status", "--porcelain"))

    def test_rebuild_rejects_replacing_curated_source_mapping(self) -> None:
        run(self.source, "checkout", "--create")
        run(self.source, "import")
        worktree = self.source / "docs/releases"
        path = worktree / "provider-snapshot.json"
        snapshot = json.loads(path.read_text())
        snapshot["records"][0]["docsSource"]["ref"] = "other-export"
        path.write_text(json.dumps(snapshot))
        commit(worktree)
        result = run(self.source, "import", "--full-rebuild", success=False)
        self.assertIn("curated docsSource", result.stderr)
        self.assertFalse(git(worktree, "status", "--porcelain"))

    def test_foreign_artifact_is_not_replaced(self) -> None:
        run(self.source, "checkout", "--create")
        run(self.source, "import")
        worktree = self.source / "docs/releases"
        path = worktree / "provider-snapshot.json"
        snapshot = json.loads(path.read_text())
        snapshot["artifacts"][0]["artifactKey"] = "other-artifact"
        path.write_text(json.dumps(snapshot))
        commit(worktree)
        result = run(self.source, "import", success=False)
        self.assertIn("foreign artifact", result.stderr)
        self.assertFalse(git(worktree, "status", "--porcelain"))

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
