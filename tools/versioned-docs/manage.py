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

"""Repository-local Git worktree and tagged documentation maintenance."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_REMOTE = "https://github.com/buildish-tooling/buildish-release-tooling.git"
ROOT = Path(__file__).resolve().parents[2]
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )
    return result.stdout.decode().strip()


def clean(worktree: Path) -> None:
    if git(worktree, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError(
            f"Worktree has local changes; commit or move them first: {worktree}"
        )


def checked_worktree(args: argparse.Namespace) -> Path:
    path = args.worktree.absolute()
    # A parent checkout must never accidentally pass as the requested worktree.
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f"Expected a real docs worktree: {path}")
    if Path(git(path, "rev-parse", "--show-toplevel")).resolve() != path.resolve():
        raise ValueError(f"Not a worktree root: {path}")
    if git(path, "symbolic-ref", "--short", "HEAD") != args.branch:
        raise ValueError(f"Worktree must be on branch {args.branch}")
    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    expected = git(
        args.source, "rev-parse", "--path-format=absolute", "--git-common-dir"
    )
    if Path(common).resolve() != Path(expected).resolve():
        raise ValueError("Docs worktree belongs to another repository")
    clean(path)
    return path


def checkout(args: argparse.Namespace) -> None:
    path = args.worktree.absolute()
    if path.exists() or path.is_symlink():
        checked_worktree(args)
        sys.stdout.write(f"Already checked out: {path}\n")
        return
    branch_ref = f"refs/heads/{args.branch}"
    git(args.source, "check-ref-format", branch_ref)
    local = git(args.source, "for-each-ref", "--format=%(refname)", branch_ref)
    if args.create:
        if local:
            raise ValueError(f"Branch already exists: {args.branch}; omit --create")
        # Orphan checkout contains no source history or source-tree files.
        git(args.source, "worktree", "add", "--orphan", "-b", args.branch, str(path))
    elif local:
        git(args.source, "worktree", "add", str(path), args.branch)
    else:
        git(args.source, "fetch", "--no-tags", "--", args.remote, branch_ref)
        git(args.source, "worktree", "add", "-b", args.branch, str(path), "FETCH_HEAD")
    sys.stdout.write(f"Docs worktree ready: {path}\n")


def update(args: argparse.Namespace) -> None:
    path = checked_worktree(args)
    git(
        args.source,
        "fetch",
        "--no-tags",
        "--",
        args.remote,
        f"refs/heads/{args.branch}",
    )
    commit = git(args.source, "rev-parse", "FETCH_HEAD^{commit}")
    git(path, "merge", "--ff-only", commit)
    sys.stdout.write(f"Updated {path} (fast-forward only; nothing pushed)\n")


def version_key(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError(f"Expected a stable X.Y.Z version: {value}")
    return tuple(int(part) for part in value.split("."))


def load_snapshot(path: Path) -> dict:
    if not path.exists():
        return {"schemaVersion": 1, "providers": [], "records": []}
    if path.is_symlink():
        raise ValueError("Snapshot must not be a symlink")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise ValueError("Unsupported provider snapshot")
    for key in ("providers", "records"):
        if not isinstance(data.setdefault(key, []), list):
            raise ValueError("Unsupported provider snapshot")
    versions = set()
    for record in data["records"]:
        version = record["version"]
        version_key(version)
        if (
            record.get("componentSlug") != "release-tooling"
            or record.get("artifactKey") != "release-tooling"
            or record.get("provider") != "release-tooling-tags"
            or record.get("kind") != "released"
            or version in versions
        ):
            raise ValueError("Snapshot contains foreign or duplicate records")
        versions.add(version)
    if data["providers"] and [p["key"] for p in data["providers"]] != [
        "release-tooling-tags"
    ]:
        raise ValueError("Snapshot contains foreign providers")
    return data


def artifact_facts(snapshot: dict) -> dict:
    """Retain operator decisions; an initial import makes no latest recommendation."""
    artifacts = snapshot.setdefault("artifacts", [])
    if not isinstance(artifacts, list) or len(artifacts) > 1:
        raise ValueError("Snapshot must contain only the release-tooling artifact")
    if not artifacts:
        artifacts.append(
            {"componentSlug": "release-tooling", "artifactKey": "release-tooling"}
        )
    artifact = artifacts[0]
    if not isinstance(artifact, dict) or (
        artifact.get("componentSlug") != "release-tooling"
        or artifact.get("artifactKey") != "release-tooling"
    ):
        raise ValueError("Snapshot contains a foreign artifact")
    return artifact


def docs_source(commit: str) -> dict[str, str]:
    return {
        "repository": DEFAULT_REMOTE.removesuffix(".git"),
        "root": "docs",
        "ref": commit,
    }


def docs_bytes(root: Path) -> dict[Path, bytes]:
    """Compare retained files before asserting their original source mapping."""
    if root.is_symlink():
        raise ValueError(f"Docs directory must not be a symlink: {root}")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Docs entry must not be a symlink: {path}")
        if path.is_file():
            files[path.relative_to(root)] = path.read_bytes()
    return files


def export_docs(source: Path, tag: str, destination: Path) -> None:
    listing = subprocess.run(
        ["git", "-C", str(source), "ls-tree", "-rz", tag, "--", "docs/"],
        check=True,
        capture_output=True,
    ).stdout
    entries = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        relative = Path(raw_path.decode()).relative_to("docs")
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[0] == "releases"
        ):
            raise ValueError(f"Unexpected docs path in {tag}: {relative}")
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError(
                f"Unsupported docs entry in {tag}: {relative} (symlink/submodule?)"
            )
        entries.append((relative, blob))
    if not entries or not any(path == Path("_index.md") for path, _ in entries):
        raise ValueError(f"Tag {tag} has no docs/_index.md")
    destination.mkdir()
    for relative, blob in entries:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            subprocess.run(
                ["git", "-C", str(source), "cat-file", "blob", blob],
                check=True,
                capture_output=True,
            ).stdout
        )


def import_docs(args: argparse.Namespace) -> None:
    worktree = checked_worktree(args)
    snapshot_path = worktree / "provider-snapshot.json"
    snapshot = load_snapshot(snapshot_path)
    original = json.dumps(snapshot, sort_keys=True)
    artifact = artifact_facts(snapshot)
    if args.release_line and args.release_line not in {
        line["key"] for line in (artifact.get("releaseLines") or [])
    }:
        raise ValueError(
            "--release-line must name an explicitly curated artifact release line"
        )
    previous = {record["version"]: record for record in snapshot["records"]}
    minimum = version_key(args.minimum_version) if args.minimum_version else None
    if args.version:
        selected = sorted(set(args.version), key=version_key)
    else:
        tags = git(args.source, "tag", "--list", "v*").splitlines()
        selected = sorted(
            (
                tag[1:]
                for tag in tags
                if VERSION.fullmatch(tag[1:])
                and (minimum is None or version_key(tag[1:]) >= minimum)
            ),
            key=version_key,
        )
    if not selected:
        raise ValueError(
            "No matching local stable tags; fetch tags or use --version X.Y.Z"
        )
    records = {version: dict(record) for version, record in previous.items()}
    exports = []
    migrations = []
    commits = {}
    for version in selected:
        tag = f"v{version}"
        commit = git(
            args.source, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"
        )
        commits[version] = commit
        old = previous.get(version)
        if old and (old.get("commitSha") != commit or old.get("tag") != tag):
            raise ValueError(
                f"Tag changed for existing snapshot {version}; investigate before rebuilding"
            )
        target = worktree / version
        if target.is_symlink() or (target.exists() and version not in previous):
            raise ValueError(f"Refusing to replace unowned path: {target}")
        record = records.setdefault(
            version,
            {
                "provider": "release-tooling-tags",
                "kind": "released",
                "componentSlug": "release-tooling",
                "artifactKey": "release-tooling",
                "version": version,
                "tag": tag,
                "commitSha": commit,
                "externalId": f"git:buildish-release-tooling:{tag}",
                "externalUrl": f"https://github.com/buildish-tooling/buildish-release-tooling/releases/tag/{tag}",
            },
        )
        if args.release_line:
            if record.get("releaseLine") not in (None, args.release_line):
                raise ValueError(
                    f"Refusing to replace curated release line for {version}"
                )
            record["releaseLine"] = args.release_line
        if old and not args.full_rebuild:
            if not (target / "_index.md").is_file():
                raise ValueError(
                    f"Missing docs for {version}; use --full-rebuild to restore"
                )
            if args.migrate and record.get("docsSource") is None:
                migrations.append(version)
                record["docsSource"] = docs_source(commit)
            continue
        expected_source = docs_source(commit)
        if record.get("docsSource") not in (None, expected_source):
            raise ValueError(f"Rebuild would replace curated docsSource for {version}")
        record["docsSource"] = expected_source
        exports.append(version)
    # Audit/export all selected trees before modifying any retained files or metadata.
    with tempfile.TemporaryDirectory(
        prefix="versioned-docs-", dir=worktree.parent
    ) as temp:
        staging = Path(temp)
        for version in exports + migrations:
            export_docs(args.source, commits[version], staging / version)
        for version in migrations:
            if docs_bytes(staging / version) != docs_bytes(worktree / version):
                raise ValueError(
                    f"Retained docs differ from recorded source for {version}; cannot add docsSource"
                )
        if args.full_rebuild:
            for version in exports:
                target = worktree / version
                if target.is_symlink() or (target.exists() and not target.is_dir()):
                    raise ValueError(f"Expected managed directory: {target}")
            for version in exports:
                if (worktree / version).exists():
                    shutil.rmtree(worktree / version)
        for version in exports:
            (staging / version).rename(worktree / version)
        if exports:
            snapshot["providers"] = [
                {
                    **(snapshot["providers"][0] if snapshot["providers"] else {}),
                    "key": "release-tooling-tags",
                    "type": "git-tags",
                    "displayName": "Release Tooling Git tags",
                    "baseUrl": DEFAULT_REMOTE.removesuffix(".git"),
                    "fetchedAt": datetime.now(UTC).isoformat(),
                }
            ]
        snapshot["records"] = [records[v] for v in sorted(records, key=version_key)]
        if json.dumps(snapshot, sort_keys=True) == original:
            sys.stdout.write("Release docs already up to date\n")
            return
        snapshot_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    sys.stdout.write(
        f"Imported {len(exports)} version(s) into {worktree}; review and commit separately\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("checkout", "update", "import"):
        command = commands.add_parser(name)
        command.add_argument(
            "--source", type=Path, default=ROOT, help="Source Git repository"
        )
        command.add_argument(
            "--worktree", type=Path, help="Default: <source>/docs/releases"
        )
        command.add_argument("--branch", default="versioned-docs")
        if name != "import":
            command.add_argument(
                "--remote",
                default=DEFAULT_REMOTE,
                help="Remote URL or name; no remotes are configured",
            )
        if name == "checkout":
            command.add_argument(
                "--create",
                action="store_true",
                help="Create a new local orphan branch; no fetch/commit/push",
            )
        if name == "import":
            command.add_argument(
                "--version",
                action="append",
                help="Import only this version; repeatable, overrides minimum",
            )
            command.add_argument(
                "--minimum-version",
                help="Optional minimum stable version for tag discovery; default scans all stable tags",
            )
            command.add_argument(
                "--migrate",
                action="store_true",
                help="Audit retained selected docs before adding missing original-source mappings",
            )
            command.add_argument(
                "--release-line",
                help="Assign selected records to this already curated primary release line; never changes latest",
            )
            command.add_argument(
                "--full-rebuild",
                action="store_true",
                help="Rebuild selected docs directories, preserving existing inventory metadata",
            )
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.worktree = args.worktree or args.source / "docs/releases"
    try:
        {"checkout": checkout, "update": update, "import": import_docs}[args.command](
            args
        )
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        message = (
            error.stderr.decode().strip()
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        sys.stderr.write(f"versioned-docs: {message}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
