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

"""Validate detached Git content without checking it out or executing its files."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from buildish_release_tooling.shared.io import hash_file

from buildish_release_tooling.release.config import ReleaseConfig
from buildish_release_tooling.release.core.materialization import (
    MaterializationBinding,
    normalized_materialized_paths,
)
from buildish_release_tooling.release.core.state import (
    CandidateReleaseState,
    DirectReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.process import run_logged_command

MaterializedState = DirectReleaseState | CandidateReleaseState | PromotionState


def git_output(repo: GitRepository, *arguments: str) -> str:
    """Read Git object data using trusted local repository configuration."""
    return run_logged_command(
        ["git", "--no-replace-objects", "-C", str(repo.path), *arguments], cwd=repo.path
    ).stdout


def validate_materialized_commit(
    repo: GitRepository,
    *,
    source: str,
    commit: str,
    paths: list[str],
    tree: str | None = None,
) -> str:
    """Require one direct child of S, changing regular files only under permitted paths."""
    permitted = normalized_materialized_paths(paths)
    if not permitted:
        raise ValueError(
            "detached materialization requires trusted tags.materialized_paths"
        )
    if (
        git_output(repo, "rev-parse", "--verify", f"{source}^{{commit}}").strip()
        != source
        or git_output(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
        != commit
    ):
        raise ValueError("materialization requires exact commit identities")
    # Revision traversal hides parents at shallow boundaries; the object does not.
    header = git_output(repo, "cat-file", "commit", commit).split("\n\n", 1)[0]
    parents = [
        line.removeprefix("parent ")
        for line in header.splitlines()
        if line.startswith("parent ")
    ]
    if parents != [source]:
        raise ValueError(
            "materialized commit must have exactly the selected source as its sole parent"
        )
    actual_tree = git_output(repo, "rev-parse", f"{commit}^{{tree}}").strip()
    if tree is not None and actual_tree != tree:
        raise ValueError("materialized tree does not match its binding")
    changes = git_output(
        repo,
        "diff-tree",
        "--no-commit-id",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--ignore-submodules=none",
        "-r",
        "--raw",
        "-z",
        source,
        commit,
        "--",
    ).split("\0")
    if changes == [""]:
        raise ValueError("materialized commit must change generated content")
    for index in range(0, len(changes) - 1, 2):
        metadata, path = changes[index : index + 2]
        if not any(path == root or path.startswith(root + "/") for root in permitted):
            raise ValueError(
                f"materialization changes a path outside trusted policy: {path}"
            )
        fields = metadata.split()
        if len(fields) != 5 or fields[1] not in {"000000", "100644", "100755"}:
            raise ValueError(
                f"materialized content must contain regular files, not symlinks or submodules: {path}"
            )
    return actual_tree


def validate_materialized_state(
    repo: GitRepository, config: ReleaseConfig, state: MaterializedState
) -> None:
    """Enforce trusted policy and local object checks before publication/verification."""
    binding = state.materialization
    if binding is None:
        if config.tags.final_mode == "detached-materialization-commit":
            raise ValueError(
                "detached materialization requires a bound materialized state"
            )
        return
    require_materialization_policy(config, binding)
    if state.source.commit_sha != binding.source_commit_sha:
        raise ValueError("materialization does not bind the selected source")
    validate_materialized_commit(
        repo,
        source=state.source.commit_sha,
        commit=binding.commit_sha,
        paths=binding.paths,
        tree=binding.tree_sha,
    )


def materialized_target(source: str, binding: MaterializationBinding | None) -> str:
    """Return the bound tag target, preserving reviewed source as a separate identity."""
    return source if binding is None else binding.commit_sha


def require_materialization_policy(
    config: ReleaseConfig, binding: MaterializationBinding
) -> None:
    """Check authorization before importing producer objects into a trusted checkout."""
    if config.tags.final_mode != "detached-materialization-commit":
        raise ValueError("materialization is not permitted by the configured tag mode")
    if normalized_materialized_paths(config.tags.materialized_paths) != binding.paths:
        raise ValueError(
            "materialized paths do not match trusted tags.materialized_paths"
        )


def export_materialization(
    repo: GitRepository,
    config: ReleaseConfig,
    state: MaterializedState,
    *,
    commit: str,
    bundle: Path,
) -> MaterializationBinding:
    """Export one generated commit without running a build or publishing any refs."""
    if config.tags.final_mode != "detached-materialization-commit":
        raise ValueError("materialization is not permitted by the configured tag mode")
    commit = git_output(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
    tree = validate_materialized_commit(
        repo,
        source=state.source.commit_sha,
        commit=commit,
        paths=config.tags.materialized_paths,
    )
    if state.materialization is not None:
        validate_materialized_state(repo, config, state)
        if state.materialization.commit_sha != commit:
            raise ValueError("cannot replace a retained materialized commit")
        if (
            not bundle.is_file()
            or hash_file(bundle, algorithm="sha256")
            != state.materialization.bundle_sha256
        ):
            raise ValueError("retain the original materialization bundle for recovery")
        return state.materialization
    bundle = bundle.resolve()
    if bundle.exists():
        raise ValueError(
            "bundle output already exists; retain its bound state or choose an empty output path"
        )
    bundle.parent.mkdir(parents=True, exist_ok=True)
    ref = f"refs/buildish/materialized/{commit}"
    existing = git_output(repo, "for-each-ref", "--format=%(objectname)", ref).strip()
    if existing and existing != commit:
        raise ValueError("materialization transport ref has conflicting content")
    if not existing:
        git_output(repo, "update-ref", ref, commit, "")
    try:
        git_output(
            repo, "bundle", "create", str(bundle), ref, f"^{state.source.commit_sha}"
        )
    finally:
        if not existing:
            git_output(repo, "update-ref", "-d", ref, commit)
    return MaterializationBinding(
        source_commit_sha=state.source.commit_sha,
        commit_sha=commit,
        tree_sha=tree,
        paths=config.tags.materialized_paths,
        bundle_sha256=hash_file(bundle, algorithm="sha256"),
    )


def import_materialization(
    repo: GitRepository,
    config: ReleaseConfig,
    state: MaterializedState,
    *,
    bundle: Path,
    expected_sha256: str,
) -> None:
    """Import digest-bound Git data, checking policy before any object transfer."""
    binding = state.materialization
    if binding is None:
        raise ValueError("import requires a bound materialized state")
    require_materialization_policy(config, binding)
    if expected_sha256 != binding.bundle_sha256:
        raise ValueError("producer bundle digest does not match materialization state")
    # Fetch exactly the private copy we hashed, not a mutable producer path.
    with tempfile.TemporaryDirectory(prefix="buildish-materialization-") as temporary:
        retained = Path(temporary) / "materialized.bundle"
        shutil.copyfile(bundle, retained)
        if hash_file(retained, algorithm="sha256") != expected_sha256:
            raise ValueError(
                "materialization bundle bytes do not match producer SHA-256"
            )
        ref = f"refs/buildish/materialized/{binding.commit_sha}"
        heads = git_output(repo, "bundle", "list-heads", str(retained)).splitlines()
        if len(heads) != 1 or heads[0].split() != [binding.commit_sha, ref]:
            raise ValueError(
                "materialization bundle does not carry exactly the bound commit ref"
            )
        git_output(repo, "bundle", "verify", str(retained))
        git_output(
            repo,
            "-c",
            "fetch.fsckObjects=true",
            "fetch",
            "--no-tags",
            "--no-recurse-submodules",
            "--no-write-fetch-head",
            "--",
            str(retained),
            ref,
        )
    validate_materialized_state(repo, config, state)


def validate_original_state(
    state: MaterializedState, original: MaterializedState
) -> None:
    """A producer may add M, but cannot alter the original trusted release/source state."""
    if type(state) is not type(original) or original.materialization is not None:
        raise ValueError("materialization requires its original trusted source state")
    payload = state.model_dump(mode="json")
    payload["materialization"] = None
    if isinstance(state, CandidateReleaseState):
        payload["candidate"]["tag"]["target_commit"] = state.source.commit_sha
        payload["final_tag_identity"]["target_commit"] = state.source.commit_sha
    else:
        payload["final_tag"]["target_commit"] = state.source.commit_sha
    if payload != original.model_dump(mode="json"):
        raise ValueError("materialization changed the original trusted source state")


def publish_materialized_objects(
    repo: GitRepository,
    config: ReleaseConfig,
    state: MaterializedState,
    *,
    repository: str,
    tag: str,
) -> None:
    """Make validated generated objects available remotely before invoking the tag API."""
    if state.materialization is None:
        return
    from buildish_release_tooling.release.git_materialization import (
        publish_materialized_ref,
    )

    validate_materialized_state(repo, config, state)
    target = state.materialization.commit_sha
    if repo.tag_exists(tag) and repo.resolve_commit(tag) != target:
        raise ValueError("existing local tag conflicts with materialized commit")
    publish_materialized_ref(
        repo, repository_slug=repository, commit_sha=target, tag_name=tag
    )
