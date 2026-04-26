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

"""Private shared helpers for grouped Buildish command modules."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import tempfile
from argparse import Namespace
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.asf_svn import AsfSvnClient
from apache_buildish_release_tooling.release.config import (
    load_component_config,
    validate_release_target_base_urls,
)
from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.github_checks import resolve_repository_slug
from apache_buildish_release_tooling.release.github_git_refs import (
    create_annotated_tag_object,
    create_ref,
    update_ref,
)
from apache_buildish_release_tooling.release.github_release_selection import selected_github_release
from apache_buildish_release_tooling.release.models import CommandContext, PrepareRcState, ReleaseVersionState
from apache_buildish_release_tooling.release.prepare_rc_state import resolve_prepare_rc_state
from apache_buildish_release_tooling.release.release_state import (
    compare_versions,
    derive_final_tag,
    derive_moving_tags,
    derive_specific_release_line,
    is_version_in_release_line,
    published_versions_from_entries,
    require_semantic_version,
    version_from_final_tag,
    versions_to_archive_for_line,
)


def _context(args: Namespace) -> CommandContext:
    config_path = args.component_config
    config = load_component_config(config_path)
    validate_release_target_base_urls(
        config,
        allow_non_production_release_targets=getattr(
            args, "allow_non_production_release_targets", False
        ),
    )
    return CommandContext(
        component_config=config,
        component_config_path=Path(config_path),
    )


def _manifest_path(component_id: str, action_name: str) -> Path:
    return Path(os.environ.get("MANIFEST_PATH", Path.cwd() / f"{component_id}-{action_name}.json"))


def _summary_code(value: str) -> str:
    """Render one inline-code value for Markdown tables."""

    return f"`{value}`"


def _summary_optional_code(value: str | None) -> str:
    """Render one optional inline-code value for Markdown tables."""

    if value is None or value == "":
        return "<none>"
    return _summary_code(value)


def _artifact_output_dir(component_id: str) -> Path:
    return Path.cwd() / "build" / "release-artifacts" / component_id


def _append_github_outputs(entries: Mapping[str, Any]) -> None:
    """Append one or more step outputs when running inside GitHub Actions."""

    output_path_text = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path_text:
        return
    output_path = Path(output_path_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for key, value in entries.items():
            rendered = "" if value is None else str(value)
            if "\n" not in rendered:
                handle.write(f"{key}={rendered}\n")
                continue
            delimiter = f"__BUILDISH_OUTPUT_{secrets.token_hex(8)}__"
            while delimiter in rendered:
                delimiter = f"__BUILDISH_OUTPUT_{secrets.token_hex(8)}__"
            handle.write(f"{key}<<{delimiter}\n{rendered}\n{delimiter}\n")


@contextmanager
def _temporary_build_dir(prefix: str) -> Iterator[Path]:
    """Yield one temporary build workspace rooted under `./build` and clean it up."""

    temp_parent = Path.cwd() / "build"
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f"{prefix}.", dir=temp_parent))
    try:
        yield temp_root
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _resolve_prepare_rc_state_from_args(
    args: Namespace,
    context: CommandContext,
    repo: GitRepository,
) -> tuple[str, PrepareRcState]:
    """Resolve one RC workflow state from common CLI arguments."""

    version = args.version
    return (
        version,
        resolve_prepare_rc_state(
            repo,
            context.component_config,
            version,
            getattr(args, "source_sha", None),
            getattr(args, "rc_tag", None),
        ),
    )


def _matching_dev_rc_entries(entries: Iterable[str], version: str) -> list[str]:
    """Return sorted RC directory entries for one exact version from `svn list` output."""

    pattern = re.compile(rf"{re.escape(version)}-rc[0-9]+")
    return sorted(
        entry.rstrip("/")
        for entry in entries
        if entry.endswith("/") and pattern.fullmatch(entry.rstrip("/")) is not None
    )


def _published_release_versions(context: CommandContext) -> list[str]:
    svn_client = AsfSvnClient.from_environment()
    release_base_url = context.component_config.asf_dist_release_base.rstrip("/")
    if not svn_client.path_exists(release_base_url):
        return []
    return published_versions_from_entries(svn_client.list_entries(release_base_url))


def _resolve_release_version_state(
    context: CommandContext,
    repo: GitRepository,
    version: str,
    expected_selected_rc_tag: str | None = None,
) -> tuple[str, ReleaseVersionState]:
    version = require_semantic_version(version)
    selected_release = selected_github_release(
        repo=repo,
        version=version,
        expected_selected_rc_tag=expected_selected_rc_tag,
    )
    release_line = derive_specific_release_line(version)
    published_versions = _published_release_versions(context)
    return (
        release_line,
        ReleaseVersionState(
            selected_rc_tag=selected_release.selected_rc_tag,
            final_tag=derive_final_tag(version),
            archive_versions=versions_to_archive_for_line(
                release_line, version, published_versions
            ),
            release_url=f"{context.component_config.asf_dist_release_base.rstrip('/')}/{version}/",
            moving_tags=derive_moving_tags(
                version,
                context.component_config.secondary_targets,
                context.component_config.moving_tags_enabled,
                context.component_config.latest_tag_enabled,
            ),
        ),
    )


def _latest_rc_directory_name(version: str, latest_rc_tag: str) -> str:
    expected_prefix = f"v{version}-rc"
    if not latest_rc_tag.startswith(expected_prefix):
        raise ValueError(f"latest RC tag does not match version {version}: {latest_rc_tag}")
    return latest_rc_tag.removeprefix("v")


def _release_name(context: CommandContext, version: str) -> str:
    return f"{context.component_config.vote_release_name} {version}"


def _repository_slug_or_none(repo: GitRepository) -> str | None:
    try:
        return resolve_repository_slug(repo.path)
    except ValueError:
        return None


def _create_or_reuse_annotated_tag(
    *,
    repo: GitRepository,
    repository_slug: str | None,
    tag_name: str,
    target_commit: str,
    message: str,
    allow_update: bool,
    reuse_if_same_target: bool = True,
) -> tuple[str, dict[str, object]]:
    """Create, update, or reuse an annotated Git tag for one target commit."""

    if repo.tag_exists(tag_name):
        existing_target_commit = repo.resolve_commit(tag_name)
        if existing_target_commit == target_commit:
            if not reuse_if_same_target:
                raise ValueError(f"tag already exists: {tag_name}")
            return "already-present", {"ref": f"refs/tags/{tag_name}"}
        if not allow_update:
            raise ValueError(f"tag already exists with a different target: {tag_name}")
        if repository_slug is None:
            repo.force_create_annotated_tag(tag_name, target_commit, message)
            return "local-git-force-update", {"ref": f"refs/tags/{tag_name}"}
        created_tag_object = create_annotated_tag_object(
            repository_slug,
            tag_name=tag_name,
            target_commit=target_commit,
            message=message,
        )
        tag_object_sha = created_tag_object.get("sha")
        if not isinstance(tag_object_sha, str) or not tag_object_sha:
            raise ValueError("GitHub tag-object creation response did not include a tag object sha")
        updated_ref = update_ref(
            repository_slug,
            ref_name=f"refs/tags/{tag_name}",
            target_sha=tag_object_sha,
            force=True,
        )
        return "github-api-force-update", updated_ref

    if repository_slug is None:
        repo.create_annotated_tag(tag_name, target_commit, message)
        return "local-git", {"ref": f"refs/tags/{tag_name}"}
    created_tag_object = create_annotated_tag_object(
        repository_slug,
        tag_name=tag_name,
        target_commit=target_commit,
        message=message,
    )
    tag_object_sha = created_tag_object.get("sha")
    if not isinstance(tag_object_sha, str) or not tag_object_sha:
        raise ValueError("GitHub tag-object creation response did not include a tag object sha")
    created_ref = create_ref(
        repository_slug,
        ref_name=f"refs/tags/{tag_name}",
        target_sha=tag_object_sha,
    )
    return "github-api", created_ref


def _final_version_for_commit(repo: GitRepository, target_commit: str) -> str | None:
    """Resolve the immutable final release version whose tag points at one commit."""

    matching_versions: list[str] = []
    for tag_name in repo.list_tags():
        version = version_from_final_tag(tag_name)
        if version is None:
            continue
        if repo.resolve_commit(tag_name) == target_commit:
            matching_versions.append(version)
    if not matching_versions:
        return None
    matching_versions.sort(key=lambda item: tuple(int(piece) for piece in item.split(".")))
    return matching_versions[-1]


def _moving_tag_scope_release_line(alias: str) -> str | None:
    """Resolve the release-line scope encoded in one moving Git tag alias."""

    normalized_alias = alias.removeprefix("v")
    if normalized_alias == "latest":
        return None
    parts = normalized_alias.split(".")
    if len(parts) == 1 and parts[0].isdigit():
        return f"{parts[0]}.x"
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return f"{parts[0]}.{parts[1]}.x"
    raise ValueError(f"unsupported moving alias: {alias}")


def _should_move_alias(alias: str, candidate_version: str, current_version: str | None) -> bool:
    """Return whether a moving alias should advance to one candidate final version."""

    if current_version is None:
        return True
    scope_release_line = _moving_tag_scope_release_line(alias)
    if scope_release_line is None:
        return compare_versions(candidate_version, current_version) == 1
    if not is_version_in_release_line(scope_release_line, candidate_version):
        raise ValueError(f"candidate version {candidate_version} is outside alias scope {alias}")
    if not is_version_in_release_line(scope_release_line, current_version):
        raise ValueError(f"current alias target {current_version} is outside alias scope {alias}")
    return compare_versions(candidate_version, current_version) == 1


def _rc_tag_message(context: CommandContext, version: str, rc_tag: str) -> str:
    """Render the standard annotated-message text for one RC tag."""

    return (
        f"Release candidate {context.component_config.vote_release_name} "
        f"{version}-rc{rc_tag.removeprefix(f'v{version}-rc')}"
    )


def _rc_number_from_tag(version: str, rc_tag: str) -> int:
    """Parse the numeric RC suffix from one exact RC tag string."""

    expected_prefix = f"v{version}-rc"
    if not rc_tag.startswith(expected_prefix):
        raise ValueError(f"RC tag does not match version {version}: {rc_tag}")
    rc_suffix = rc_tag.removeprefix(expected_prefix)
    if not rc_suffix.isdigit():
        raise ValueError(f"RC tag does not end in a numeric suffix: {rc_tag}")
    return int(rc_suffix)
