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

"""Generated Action payload fixtures, using object plumbing without source checkout."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ACTION_PATHS = tuple(
    f"dist/github/{ecosystem}/{phase}/index.cjs"
    for ecosystem in ("gradle", "maven")
    for phase in ("main", "post")
)


def generated_action_commit(repo: Path, source: str) -> str:
    with tempfile.TemporaryDirectory() as temporary:
        env = {
            **os.environ,
            "GIT_INDEX_FILE": str(Path(temporary) / "index"),
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": "2026-11-17T12:00:00Z",
            "GIT_COMMITTER_DATE": "2026-11-17T12:00:00Z",
        }

        def git(*args: str, text: str | None = None) -> str:
            return subprocess.run(
                ["git", "--no-replace-objects", "-C", str(repo), *args],
                input=text,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()

        git("read-tree", source)
        for path in ACTION_PATHS:
            blob = git("hash-object", "-w", "--stdin", text=f"console.log({path!r});\n")
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}")
        tree = git("write-tree")
        return git(
            "-c",
            "commit.gpgsign=false",
            "commit-tree",
            tree,
            "-p",
            source,
            text="Generated Action fixture\n",
        )


def local_materialization_remote(
    repo: Path, origin: Path, repository: str = "apache/example-project"
) -> None:
    """Keep authenticated Git transport in lifecycle tests entirely on the local fixture."""
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "config",
            f"url.{origin.as_uri()}.insteadOf",
            f"https://github.com/{repository}.git",
        ],
        check=True,
        capture_output=True,
    )
