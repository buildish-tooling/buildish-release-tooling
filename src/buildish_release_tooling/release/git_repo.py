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

"""Git repository helpers used by the release-tooling commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from buildish_release_tooling.release.process import run_logged_command
from buildish_release_tooling.release.core.naming import (
    highest_existing_rc_number_or_zero,
    latest_rc_tag_from_tags,
    next_candidate_number_from_tags,
    next_rc_number_from_tags,
    resolve_release_branch,
)


def current_worktree_root(start_path: Path | None = None) -> Path:
    """Resolve the current Git worktree root for a path."""

    path = start_path or Path.cwd()
    completed = run_logged_command(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"], cwd=path
    )
    return Path(completed.stdout.strip())


def require_worktree_root(start_path: Path | None = None) -> Path:
    """Resolve the current worktree root and raise a stable error when not in Git."""

    path = start_path or Path.cwd()
    try:
        return current_worktree_root(path)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"current directory is not inside a Git worktree: {path}") from exc


@dataclass(slots=True)
class GitRepository:
    """Small abstraction over Git operations used by the release-tooling CLI."""

    path: Path

    @classmethod
    def from_current_worktree(cls, start_path: Path | None = None) -> GitRepository:
        """Resolve and construct a repository from the current Git worktree."""

        return cls(require_worktree_root(start_path))

    def _run(self, *args: str, capture_output: bool = True, check: bool = True) -> str:
        completed = run_logged_command(
            ["git", "-C", str(self.path), *args],
            cwd=self.path,
            capture_output=capture_output,
            check=check,
        )
        return (completed.stdout or "").strip()

    def list_local_branches(self) -> list[str]:
        """List local branch names."""

        output = self._run("for-each-ref", "--format=%(refname:short)", "refs/heads")
        return [line for line in output.splitlines() if line]

    def list_remote_branches(self) -> list[str]:
        """List remote-tracking branch names without the remote prefix."""

        output = self._run("for-each-ref", "--format=%(refname:short)", "refs/remotes")
        result: list[str] = []
        for line in output.splitlines():
            if not line or line.endswith("/HEAD"):
                continue
            _remote, _, short_name = line.partition("/")
            result.append(short_name)
        return result

    def list_known_branches(self) -> list[str]:
        """List local and remote-tracking branches without duplicates."""

        seen: dict[str, None] = {}
        for branch in [*self.list_local_branches(), *self.list_remote_branches()]:
            seen.setdefault(branch, None)
        return list(seen)

    def list_tags(self) -> list[str]:
        """List Git tags."""

        output = self._run("tag", "--list")
        return [line for line in output.splitlines() if line]

    def tags_pointing_at(self, ref: str) -> list[str]:
        """List tags whose target commit matches one supplied ref."""

        output = self._run("tag", "--points-at", ref)
        return [line for line in output.splitlines() if line]

    def current_head_commit(self) -> str:
        """Resolve `HEAD` to an exact commit SHA."""

        return self.resolve_commit("HEAD")

    def commit_timestamp_epoch(self, ref: str) -> int:
        """Resolve one ref to its commit timestamp in Unix epoch seconds."""

        resolved_ref = self.resolve_commit(ref)
        output = self._run("show", "-s", "--format=%ct", resolved_ref)
        if not output or not output.isdigit():
            raise ValueError(f"unable to resolve Git commit timestamp for ref: {ref}")
        return int(output)

    def current_symbolic_ref(self) -> str | None:
        """Return the symbolic ref for `HEAD` when one exists."""

        output = self._run("symbolic-ref", "-q", "HEAD", check=False)
        return output or None

    def remote_url(self, remote_name: str = "origin") -> str:
        """Return the configured URL for one Git remote."""

        output = self._run("remote", "get-url", remote_name, check=False)
        if not output:
            raise ValueError(f"remote does not exist: {remote_name}")
        return output

    def _first_remote_tracking_ref(self, ref_name: str) -> str | None:
        output = self._run(
            "for-each-ref", "--format=%(refname)", f"refs/remotes/*/{ref_name}", check=True
        )
        lines = [line for line in output.splitlines() if line]
        return lines[0] if lines else None

    def branch_exists(self, branch_name: str) -> bool:
        """Return whether a local branch exists."""

        try:
            self._run("show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}", check=True)
        except Exception:  # noqa: BLE001
            return False
        return True

    def tag_exists(self, tag_name: str) -> bool:
        """Return whether a tag exists."""

        try:
            self._run("show-ref", "--verify", "--quiet", f"refs/tags/{tag_name}", check=True)
        except Exception:  # noqa: BLE001
            return False
        return True

    def resolve_commit(self, ref: str) -> str:
        """Resolve a supported ref to an exact commit SHA."""

        direct_commit = self._run("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
        if direct_commit:
            return direct_commit
        if self.branch_exists(ref):
            return self._run("rev-parse", f"refs/heads/{ref}^{{commit}}")
        remote_ref = self._first_remote_tracking_ref(ref)
        if remote_ref is not None:
            return self._run("rev-parse", f"{remote_ref}^{{commit}}")
        raise ValueError(f"unable to resolve Git ref: {ref}")

    def create_branch(self, branch_name: str, source_ref: str) -> None:
        """Create a local branch from a source ref when it does not already exist."""

        if self.branch_exists(branch_name):
            raise ValueError(f"branch already exists: {branch_name}")
        self._run("branch", branch_name, self.resolve_commit(source_ref), capture_output=False)

    def create_annotated_tag(self, tag_name: str, target_ref: str, message: str) -> None:
        """Create an annotated tag when the tag does not already exist."""

        if self.tag_exists(tag_name):
            raise ValueError(f"tag already exists: {tag_name}")
        self._run("tag", "-a", tag_name, "-m", message, target_ref, capture_output=False)

    def force_create_annotated_tag(self, tag_name: str, target_ref: str, message: str) -> None:
        """Create or replace one annotated tag locally."""

        self._run("tag", "-f", "-a", tag_name, "-m", message, target_ref, capture_output=False)

    def highest_matching_rc_number_or_zero(self, version: str) -> int:
        """Find the highest RC number for a version from real repository tags."""

        return highest_existing_rc_number_or_zero(version, self.list_tags())

    def next_matching_rc_number(self, version: str) -> int:
        """Derive the next RC number for a version from real repository tags."""

        return next_rc_number_from_tags(version, self.list_tags())

    def next_matching_candidate_number(
        self,
        version: str,
        candidate_label: str,
        candidate_start_number: int,
    ) -> int:
        """Derive the next candidate number for a version and label from real tags."""

        return next_candidate_number_from_tags(
            version,
            candidate_label,
            candidate_start_number,
            self.list_tags(),
        )

    def latest_matching_rc_tag(self, version: str) -> str:
        """Resolve the latest RC tag for a version from real repository tags."""

        return latest_rc_tag_from_tags(version, self.list_tags())

    def resolve_release_branch_for_version(self, version: str) -> str:
        """Resolve the preferred release branch for a semantic version."""

        return resolve_release_branch(version, self.list_known_branches())
