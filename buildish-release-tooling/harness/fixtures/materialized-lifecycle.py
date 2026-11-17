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

"""Trusted harness driver for separate generated-build and publication jobs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
FILES = ROOT / ".fixture"
MODE = os.environ["MATERIALIZED_LIFECYCLE"]
REPOSITORY = "buildish-tooling/materialized-fixture"
CONFIG = FILES / "config.json"
ACTION_PATHS = [
    f"dist/github/{ecosystem}/{phase}/index.cjs"
    for ecosystem in ("gradle", "maven")
    for phase in ("main", "post")
]


def command(
    argv: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv, cwd=cwd, env=env, text=True, capture_output=True, check=False
    )
    if (result.returncode == 0) != success:
        raise RuntimeError(
            f"{argv}: unexpected exit {result.returncode}\n{result.stdout}\n{result.stderr}"
        )
    return result


def git(*args: str, cwd: Path = ROOT) -> str:
    return command(["git", *args], cwd=cwd).stdout.strip()


def cli(action: str, *args: str, cwd: Path = ROOT, success: bool = True) -> Path:
    output = FILES / f"{action}.json"
    command(
        [
            sys.executable,
            "-m",
            "buildish_release_tooling.release",
            action,
            "--component-config",
            str(CONFIG),
            *args,
        ],
        cwd=cwd,
        env={**os.environ, "MANIFEST_PATH": str(output)},
        success=success,
    )
    return output


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare() -> None:
    git("remote", "add", "origin", f"https://github.com/{REPOSITORY}.git")
    origin = ROOT / ".buildish-release-harness/git-origins/self"
    origin.parent.mkdir(parents=True, exist_ok=True)
    command(["git", "clone", "--bare", "--no-local", str(ROOT), str(origin)])
    git("config", "user.name", "Fixture", cwd=origin)
    git("config", "user.email", "fixture@example.invalid", cwd=origin)
    git(
        "config",
        f"url.{origin.as_uri()}.insteadOf",
        f"https://github.com/{REPOSITORY}.git",
    )
    config = {
        "component": {
            "id": "materialized-fixture",
            "display_name": "Materialized Fixture",
        },
        "source": {
            "selection": "explicit-ref",
            "snapshot": {"mode": "platform-generated"},
        },
        "lifecycle": {"mode": MODE},
        "publication": {
            "authoritative": {"kind": "github-release", "repository": REPOSITORY},
            "secondary": [{"kind": "github-action"}],
        },
        "tags": {
            "final_mode": "detached-materialization-commit",
            "materialized_paths": ["dist"],
            "moving": ["major", "minor"],
        },
    }
    if MODE == "candidate":
        config["candidate"] = {
            "label": "rc",
            "start_number": 1,
            "visibility": "public-prerelease",
            "retention": "retain-published",
        }
    CONFIG.write_text(json.dumps(config))
    action = "resolve-candidate" if MODE == "candidate" else "resolve-direct-release"
    source = git("rev-parse", "HEAD")
    cli(action, "1.2.3", source)
    (FILES / "source.txt").write_text(source)
    (FILES / "original-state-sha256.txt").write_text(digest(FILES / f"{action}.json"))


def build() -> None:
    # This job stands for component-owned selected-source execution. No write/signing credentials.
    for name in list(os.environ):
        if name in {"GH_TOKEN", "GITHUB_TOKEN"} or name.startswith(
            "BUILDISH_RELEASE_GPG_"
        ):
            os.environ.pop(name)
    producer = FILES / "producer"
    command(
        [
            "git",
            "clone",
            "--no-local",
            "--depth=1",
            "--no-tags",
            ROOT.as_uri(),
            str(producer),
        ]
    )
    for relative in ACTION_PATHS:
        path = producer / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"console.log({relative!r});\n")
    git("add", "--force", "dist", cwd=producer)
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Generated Action payload",
        cwd=producer,
    )
    materialized = git("rev-parse", "HEAD", cwd=producer)
    state_name = (
        "resolve-candidate" if MODE == "candidate" else "resolve-direct-release"
    )
    flag = "--candidate-state" if MODE == "candidate" else "--release-state"
    state = cli(
        "bind-materialization",
        flag,
        str(FILES / f"{state_name}.json"),
        "--materialized-commit",
        materialized,
        "--bundle-output",
        str(FILES / "payload.bundle"),
        cwd=producer,
    )
    # Stand-ins for independent job outputs, not digests read from downloaded artifact content.
    (FILES / "producer-outputs.json").write_text(
        json.dumps(
            {
                "state_sha256": digest(state),
                "bundle_sha256": digest(FILES / "payload.bundle"),
            }
        )
    )


def publish() -> None:
    source = (FILES / "source.txt").read_text()
    bound = FILES / "bind-materialization.json"
    producer_outputs = json.loads((FILES / "producer-outputs.json").read_text())
    if digest(bound) != producer_outputs["state_sha256"]:
        raise RuntimeError("producer state checksum mismatch")
    flag = "--candidate-state" if MODE == "candidate" else "--release-state"
    original = FILES / (
        "resolve-candidate.json"
        if MODE == "candidate"
        else "resolve-direct-release.json"
    )
    if digest(original) != (FILES / "original-state-sha256.txt").read_text():
        raise RuntimeError("original source-state checksum mismatch")
    cli(
        "import-materialization",
        flag,
        str(bound),
        "--source-state",
        str(original),
        "--bundle",
        str(FILES / "payload.bundle"),
        "--bundle-sha256",
        producer_outputs["bundle_sha256"],
    )
    if git("rev-parse", "HEAD") != source or (ROOT / "dist").exists():
        raise RuntimeError("privileged import changed checked-out source")
    cwd = ROOT
    final_state = bound
    if MODE == "candidate":
        candidate = json.loads(bound.read_text())["candidate"]["tag"]["name"]
        cli("create-candidate-tag", flag, str(bound))
        stage = cli("stage-github-candidate", flag, str(bound))
        manifest = cli(
            "create-candidate-manifest", flag, str(bound), "--stage-result", str(stage)
        )
        # The stable asset requires its canonical filename.
        canonical = FILES / "candidate-manifest.json"
        shutil.copyfile(manifest, canonical)
        candidate_digest = digest(canonical)
        cli(
            "attach-github-candidate-manifest",
            flag,
            str(bound),
            "--candidate-manifest",
            str(canonical),
        )
        cli(
            "finalize-github-candidate",
            "--candidate-tag",
            candidate,
            "--candidate-manifest-digest",
            candidate_digest,
        )
        cli(
            "verify-github-candidate",
            "--candidate-tag",
            candidate,
            "--candidate-manifest-digest",
            candidate_digest,
        )
        # A fresh shallow workflow checkout has S and no M; promotion recovers retained objects.
        cwd = FILES / "promotion"
        command(
            [
                "git",
                "clone",
                "--no-local",
                "--no-tags",
                "--depth=1",
                "--branch",
                "main",
                ROOT.as_uri(),
                str(cwd),
            ]
        )
        # Clone does not inherit the source repository's local identity.
        git("config", "user.name", "Fixture", cwd=cwd)
        git("config", "user.email", "fixture@example.invalid", cwd=cwd)
        git(
            "remote",
            "set-url",
            "origin",
            f"https://github.com/{REPOSITORY}.git",
            cwd=cwd,
        )
        origin = ROOT / ".buildish-release-harness/git-origins/self"
        git(
            "config",
            f"url.{origin.as_uri()}.insteadOf",
            f"https://github.com/{REPOSITORY}.git",
            cwd=cwd,
        )
        final_state = cli(
            "resolve-promotion",
            "1.2.3",
            "--candidate-tag",
            candidate,
            "--candidate-manifest",
            str(canonical),
            "--candidate-manifest-digest",
            candidate_digest,
            cwd=cwd,
        )
        cli(
            "import-materialization",
            "--promotion-state",
            str(final_state),
            "--bundle",
            str(FILES / "payload.bundle"),
            "--bundle-sha256",
            producer_outputs["bundle_sha256"],
            cwd=cwd,
        )
        flag = "--promotion-state"
    cli("create-final-tag", flag, str(final_state), cwd=cwd)
    stage = cli(
        "stage-github-final-release", "--release-state", str(final_state), cwd=cwd
    )
    manifest = cli(
        "create-release-manifest",
        "--release-state",
        str(final_state),
        "--publication-result",
        str(stage),
        cwd=cwd,
    )
    canonical = FILES / "release-manifest-v1.json"
    shutil.copyfile(manifest, canonical)
    cli(
        "attach-github-release-manifest",
        "--release-state",
        str(final_state),
        "--release-manifest",
        str(canonical),
        cwd=cwd,
    )
    sealed_digest = digest(canonical)
    for _ in range(2):
        cli(
            "publish-github-final-release",
            "--release-state",
            str(final_state),
            "--require-manifest-digest",
            sealed_digest,
            cwd=cwd,
        )
        cli("verify-github-final-release", "--release-state", str(final_state), cwd=cwd)
    cli("update-moving-tags", "1.2.3", cwd=cwd)
    state = json.loads(final_state.read_text())
    target = state["materialization"]["commit_sha"]
    for ref in ("v1.2.3", "v1", "v1.2"):
        origin = ROOT / ".buildish-release-harness/git-origins/self"
        if git("rev-parse", f"{ref}^{{commit}}", cwd=origin) != target:
            raise RuntimeError(f"{ref} did not retain M")
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node is required for the tagged Action consumer rehearsal")
    for path in ACTION_PATHS:
        code = git("show", f"v1.2.3:{path}", cwd=cwd)
        output = command([node, "--eval", code]).stdout.strip()
        if output != path:
            raise RuntimeError("tagged Action entry point failed")
    forbidden = FILES / "forbidden-after-publication.json"
    forbidden.write_text("{}\n")
    command(
        ["gh", "release", "upload", "v1.2.3", str(forbidden), "-R", REPOSITORY],
        success=False,
    )
    final_manifest = json.loads(canonical.read_text())
    if final_manifest["materialization"] != state["materialization"]:
        raise RuntimeError("sealed manifest changed materialization binding")
    (FILES / "result.json").write_text(
        json.dumps(
            {
                "source": source,
                "materialized": target,
                "sealed_digest": sealed_digest,
                "mode": MODE,
            }
        )
    )


if __name__ == "__main__":
    {"prepare": prepare, "build": build, "publish": publish}[sys.argv[1]]()
