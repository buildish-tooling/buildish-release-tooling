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

"""Small ASF SVN abstraction used by the release-tooling CLI."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from apache_buildish_release_tooling.process import run_logged_command


def url_join(base_url: str, *parts: str) -> str:
    """Join and normalize an SVN base URL with child path segments."""

    joined = base_url
    for part in parts:
        joined = f"{joined.rstrip('/')}/{part.lstrip('/')}"
    return joined


@dataclass(slots=True)
class AsfSvnClient:
    """Helper for authenticated non-interactive SVN operations."""

    username: str | None = None
    password: str | None = None

    @classmethod
    def from_environment(cls) -> AsfSvnClient:
        """Construct an SVN client from the expected Buildish credential variables."""

        return cls(
            username=os.environ.get("BUILDISH_SVN_DEV_USERNAME"),
            password=os.environ.get("BUILDISH_SVN_DEV_PASSWORD"),
        )

    def _auth_args(self) -> list[str]:
        if not self.username or not self.password:
            return []
        return [
            "--non-interactive",
            "--no-auth-cache",
            "--username",
            self.username,
            "--password",
            self.password,
        ]

    def _run(self, *args: str, capture_output: bool = True, check: bool = True) -> str:
        completed = run_logged_command(
            ["svn", *self._auth_args(), *args],
            capture_output=capture_output,
            check=check,
            extra_secret_values=[self.username or "", self.password or ""],
        )
        return (completed.stdout or "").strip()

    def path_exists(self, target: str) -> bool:
        """Return whether an SVN URL or working-copy path exists."""

        try:
            self._run("info", target, capture_output=False)
        except Exception:  # noqa: BLE001
            return False
        return True

    def require_working_copy_root(self, start_path: Path) -> Path:
        """Resolve the root directory of an SVN working copy."""

        try:
            return Path(self._run("info", "--show-item", "wc-root", str(start_path)))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"path is not inside an SVN working copy: {start_path}") from exc

    def _assert_working_copy(self, working_copy_path: Path) -> None:
        self.require_working_copy_root(working_copy_path)

    def checkout_url(self, repo_url: str, working_copy_path: Path) -> None:
        """Check out an SVN URL into a detached working copy."""

        self._run("checkout", repo_url, str(working_copy_path), capture_output=False)

    def list_entries(self, target: str, *, recursive: bool = False) -> list[str]:
        """List entries from an SVN URL or working-copy path."""

        arguments = ["list"]
        if recursive:
            arguments.append("-R")
        arguments.append(target)
        output = self._run(*arguments)
        return [line for line in output.splitlines() if line]

    def mkdir_url(self, repo_url: str, commit_message: str) -> None:
        """Create a directory in SVN by URL."""

        self._run("mkdir", "-m", commit_message, repo_url, capture_output=False)

    def delete_url(self, repo_url: str, commit_message: str) -> None:
        """Delete a repository path in SVN by URL."""

        self._run("delete", "-m", commit_message, repo_url, capture_output=False)

    def copy_url(self, source_url: str, target_url: str, commit_message: str) -> None:
        """Copy one repository URL to another within SVN."""

        self._run("copy", "-m", commit_message, source_url, target_url, capture_output=False)

    def working_copy_put_file(
        self, working_copy_path: Path, source_file: Path, destination_relpath: str
    ) -> None:
        """Copy a file into an SVN working copy and schedule it for addition."""

        self._assert_working_copy(working_copy_path)
        destination_path = working_copy_path / destination_relpath.lstrip("./")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_path)
        self._run("add", "--parents", "--force", str(destination_path), capture_output=False)

    def working_copy_delete_path(self, working_copy_path: Path, target_relpath: str) -> None:
        """Delete an SVN working-copy path when it exists locally or in metadata."""

        self._assert_working_copy(working_copy_path)
        target_path = working_copy_path / target_relpath.lstrip("./")
        if target_path.exists() or self.path_exists(str(target_path)):
            self._run("delete", str(target_path), capture_output=False)

    def commit_working_copy(self, working_copy_path: Path, commit_message: str) -> None:
        """Commit pending changes from an SVN working copy."""

        self._assert_working_copy(working_copy_path)
        self._run("commit", "-m", commit_message, str(working_copy_path), capture_output=False)
