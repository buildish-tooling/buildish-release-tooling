# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Built-in mutable tool behaviors for the harness shim entrypoint."""

from __future__ import annotations

import json
import hashlib
import shutil
import sys
from pathlib import Path

from pydantic import Field

from buildish_release_tooling.docs.documentation import RuntimeDerivedModel
from buildish_release_tooling.docs.documentation import SchemaExportSpecification
from buildish_release_tooling.harness.models import (
    HarnessBuiltinGhRelease,
    HarnessBuiltinGhReleaseAsset,
    HarnessBuiltinGhTagObject,
    HarnessShimState,
    ToolBehaviorResult,
)
from buildish_release_tooling.harness.process import run_harness_command


class HarnessBuiltinGhRefMutationPayload(RuntimeDerivedModel):
    """Synthetic GitHub tag-ref mutation payload consumed by the harness shim."""

    ref: str | None = Field(
        default=None,
        description="Git ref name observed or created during the related operation.",
    )
    sha: str | None = Field(
        default=None,
        description="Git object SHA associated with one synthetic harness GitHub ref mutation payload.",
    )


def handle_builtin_tool(
    tool_name: str,
    argv: list[str],
    state: HarnessShimState,
) -> ToolBehaviorResult | None:
    """Handle built-in shim side effects for tools that need local mutable-state emulation."""

    if tool_name == "gh":
        return _handle_builtin_gh(argv, state)
    return None


def _handle_builtin_gh(
    argv: list[str],
    state: HarnessShimState,
) -> ToolBehaviorResult | None:
    """Handle the small GitHub CLI subset that must mutate local Git state in harness runs."""

    if argv[:2] == ["release", "upload"]:
        return _handle_release_upload(argv, state)
    if argv[:2] == ["release", "download"]:
        return _handle_release_download(argv, state)
    parsed = _parse_gh_api_request(argv)
    if parsed is None:
        return None
    method, endpoint = parsed
    if method == "GET" and "/git/ref/tags/" in endpoint:
        return _read_builtin_gh_tag_ref(state, endpoint)
    if method == "GET" and "/git/tags/" in endpoint:
        return _read_builtin_gh_tag_object(state, endpoint)
    if method == "POST" and endpoint.endswith("/git/tags"):
        stdin_text = sys.stdin.read()
        tag_object_payload = HarnessBuiltinGhTagObject.model_validate(
            json.loads(stdin_text or "{}")
        )
        fake_sha = _store_builtin_gh_tag_object(state, tag_object_payload)
        return ToolBehaviorResult(stdout=json.dumps({"sha": fake_sha}))
    if method == "POST" and endpoint.endswith("/git/refs"):
        ref_payload = _load_ref_mutation_payload()
        _apply_builtin_gh_tag_ref(state, endpoint, ref_payload, force=False)
        return ToolBehaviorResult(stdout=json.dumps({"ref": ref_payload.ref or ""}))
    if method == "PATCH" and "/git/refs/tags/" in endpoint:
        ref_payload = _load_ref_mutation_payload()
        _apply_builtin_gh_tag_ref(state, endpoint, ref_payload, force=True)
        return ToolBehaviorResult(
            stdout=json.dumps({"ref": f"refs/tags/{endpoint.rsplit('/', 1)[-1]}"})
        )
    if method == "GET" and "/releases?" in endpoint:
        return ToolBehaviorResult(
            stdout=json.dumps(
                [
                    _release_api_payload(release)
                    for release in state.gh_releases.values()
                ]
            )
        )
    if method == "POST" and endpoint.endswith("/releases"):
        return _create_builtin_gh_release(state, endpoint)
    if method == "PATCH" and "/releases/" in endpoint:
        return _update_builtin_gh_release(state, endpoint)
    if method == "GET" and "/releases/assets/" in endpoint:
        return _download_builtin_gh_release_asset(state, endpoint)
    return None


def _read_builtin_gh_tag_ref(
    state: HarnessShimState,
    endpoint: str,
) -> ToolBehaviorResult:
    """Return one annotated-tag ref from the harness-owned Git repository."""

    tag_name = endpoint.split("/git/ref/tags/", 1)[1]
    repository = Path(state.workspace_root)
    tag_object = run_harness_command(
        ["git", "-C", str(repository), "rev-parse", f"refs/tags/{tag_name}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return ToolBehaviorResult(
        stdout=json.dumps(
            {
                "ref": f"refs/tags/{tag_name}",
                "object": {"type": "tag", "sha": tag_object},
            }
        )
    )


def _read_builtin_gh_tag_object(
    state: HarnessShimState,
    endpoint: str,
) -> ToolBehaviorResult:
    """Return the commit targeted by one harness-owned annotated tag object."""

    tag_object = endpoint.split("/git/tags/", 1)[1]
    repository = Path(state.workspace_root)
    target_commit = run_harness_command(
        ["git", "-C", str(repository), "rev-parse", f"{tag_object}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return ToolBehaviorResult(
        stdout=json.dumps({"object": {"type": "commit", "sha": target_commit}})
    )


def _create_builtin_gh_release(
    state: HarnessShimState,
    endpoint: str,
) -> ToolBehaviorResult:
    """Create one synthetic GitHub Release from an API request payload."""

    payload = json.loads(sys.stdin.read() or "{}")
    repository = endpoint.removeprefix("repos/").removesuffix("/releases")
    tag_name = str(payload.get("tag_name") or "")
    if not tag_name or tag_name in state.gh_releases:
        return ToolBehaviorResult(exit_code=1, stderr="GitHub Release already exists\n")
    release_id = state.gh_next_release_id
    state.gh_next_release_id += 1
    release = HarnessBuiltinGhRelease(
        id=release_id,
        repository=repository,
        tag_name=tag_name,
        name=str(payload.get("name") or ""),
        body=str(payload.get("body") or ""),
        draft=payload.get("draft") is True,
        prerelease=payload.get("prerelease") is True,
        html_url=f"https://github.com/{repository}/releases/tag/{tag_name}",
        url=f"https://api.github.com/repos/{repository}/releases/{release_id}",
    )
    state.gh_releases[tag_name] = release
    return ToolBehaviorResult(stdout=json.dumps(_release_api_payload(release)))


def _update_builtin_gh_release(
    state: HarnessShimState,
    endpoint: str,
) -> ToolBehaviorResult:
    """Update one synthetic GitHub Release by immutable release id."""

    release_id_text = endpoint.rsplit("/", 1)[-1]
    if not release_id_text.isdigit():
        return ToolBehaviorResult(exit_code=1, stderr="invalid GitHub Release id\n")
    release = next(
        (
            item
            for item in state.gh_releases.values()
            if item.id == int(release_id_text)
        ),
        None,
    )
    if release is None:
        return ToolBehaviorResult(exit_code=1, stderr="GitHub Release does not exist\n")
    payload = json.loads(sys.stdin.read() or "{}")
    old_tag = release.tag_name
    new_tag = str(payload.get("tag_name", old_tag))
    updated = release.model_copy(
        update={
            "tag_name": new_tag,
            "name": str(payload.get("name", release.name)),
            "body": str(payload.get("body", release.body)),
            "draft": bool(payload.get("draft", release.draft)),
            "prerelease": bool(payload.get("prerelease", release.prerelease)),
            "html_url": f"https://github.com/{release.repository}/releases/tag/{new_tag}",
        }
    )
    if new_tag != old_tag:
        del state.gh_releases[old_tag]
    state.gh_releases[new_tag] = updated
    return ToolBehaviorResult(stdout=json.dumps(_release_api_payload(updated)))


def _handle_release_upload(
    argv: list[str],
    state: HarnessShimState,
) -> ToolBehaviorResult:
    """Attach exact local files to one synthetic GitHub Release without clobbering."""

    if len(argv) < 4:
        return ToolBehaviorResult(
            exit_code=2, stderr="invalid gh release upload invocation\n"
        )
    tag_name = argv[2]
    release = state.gh_releases.get(tag_name)
    if release is None:
        return ToolBehaviorResult(exit_code=1, stderr="GitHub Release does not exist\n")
    clobber = "--clobber" in argv
    paths: list[Path] = []
    index = 3
    while index < len(argv):
        argument = argv[index]
        if argument in {"-R", "--repo"}:
            index += 2
            continue
        if argument == "--clobber":
            index += 1
            continue
        paths.append(Path(argument))
        index += 1
    assets = {asset.name: asset for asset in release.assets}
    asset_root = (
        Path(state.workspace_root)
        / ".buildish-release-harness"
        / "github-release-assets"
    )
    asset_root.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.is_file():
            return ToolBehaviorResult(
                exit_code=1, stderr=f"release asset does not exist: {path}\n"
            )
        if path.name in assets and not clobber:
            return ToolBehaviorResult(
                exit_code=1, stderr=f"release asset already exists: {path.name}\n"
            )
        asset_id = (
            assets[path.name].id if path.name in assets else state.gh_next_asset_id
        )
        if path.name not in assets:
            state.gh_next_asset_id += 1
        stored_path = asset_root / str(asset_id)
        shutil.copyfile(path, stored_path)
        data = stored_path.read_bytes()
        assets[path.name] = HarnessBuiltinGhReleaseAsset(
            id=asset_id,
            name=path.name,
            size=len(data),
            digest=f"sha256:{hashlib.sha256(data).hexdigest()}",
            stored_path=str(stored_path.relative_to(Path(state.workspace_root))),
        )
    state.gh_releases[tag_name] = release.model_copy(
        update={"assets": sorted(assets.values(), key=lambda item: item.name)}
    )
    return ToolBehaviorResult()


def _handle_release_download(
    argv: list[str],
    state: HarnessShimState,
) -> ToolBehaviorResult:
    """Materialize selected synthetic release assets into a workflow directory."""

    if len(argv) < 3:
        return ToolBehaviorResult(
            exit_code=2, stderr="invalid gh release download invocation\n"
        )
    release = state.gh_releases.get(argv[2])
    if release is None:
        return ToolBehaviorResult(exit_code=1, stderr="GitHub Release does not exist\n")
    patterns: list[str] = []
    destination = Path.cwd()
    index = 3
    while index < len(argv):
        argument = argv[index]
        if argument in {"--pattern", "-p"} and index + 1 < len(argv):
            patterns.append(argv[index + 1])
            index += 2
            continue
        if argument in {"--dir", "-D"} and index + 1 < len(argv):
            destination = Path(argv[index + 1])
            index += 2
            continue
        if argument in {"-R", "--repo"}:
            index += 2
            continue
        index += 1
    selected = [
        asset for asset in release.assets if not patterns or asset.name in patterns
    ]
    if patterns and {asset.name for asset in selected} != set(patterns):
        return ToolBehaviorResult(
            exit_code=1, stderr="requested GitHub Release asset is absent\n"
        )
    destination.mkdir(parents=True, exist_ok=True)
    for asset in selected:
        source = Path(state.workspace_root) / asset.stored_path
        shutil.copyfile(source, destination / asset.name)
    return ToolBehaviorResult()


def _download_builtin_gh_release_asset(
    state: HarnessShimState,
    endpoint: str,
) -> ToolBehaviorResult:
    """Return one text release asset through the synthetic GitHub API."""

    asset_id_text = endpoint.rsplit("/", 1)[-1]
    if not asset_id_text.isdigit():
        return ToolBehaviorResult(
            exit_code=1, stderr="invalid GitHub Release asset id\n"
        )
    asset = next(
        (
            item
            for release in state.gh_releases.values()
            for item in release.assets
            if item.id == int(asset_id_text)
        ),
        None,
    )
    if asset is None:
        return ToolBehaviorResult(
            exit_code=1, stderr="GitHub Release asset does not exist\n"
        )
    path = Path(state.workspace_root) / asset.stored_path
    return ToolBehaviorResult(stdout=path.read_text(encoding="utf-8"))


def _release_api_payload(release: HarnessBuiltinGhRelease) -> dict[str, object]:
    """Render one synthetic release in GitHub's API response shape."""

    return {
        "id": release.id,
        "tag_name": release.tag_name,
        "name": release.name,
        "body": release.body,
        "draft": release.draft,
        "prerelease": release.prerelease,
        "html_url": release.html_url,
        "url": release.url,
        "assets": [
            {
                "id": asset.id,
                "name": asset.name,
                "size": asset.size,
                "digest": asset.digest,
            }
            for asset in release.assets
        ],
    }


def _load_ref_mutation_payload() -> HarnessBuiltinGhRefMutationPayload:
    """Load one synthetic GitHub tag-ref mutation payload from stdin."""

    return HarnessBuiltinGhRefMutationPayload.model_validate(
        json.loads(sys.stdin.read() or "{}")
    )


def _parse_gh_api_request(argv: list[str]) -> tuple[str, str] | None:
    """Parse a subset of `gh api` arguments into `(method, endpoint)`."""

    if not argv or argv[0] != "api":
        return None
    method = "GET"
    endpoint = ""
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument == "-X" and index + 1 < len(argv):
            method = argv[index + 1]
            index += 2
            continue
        if argument == "-H" and index + 1 < len(argv):
            index += 2
            continue
        if argument == "--input" and index + 1 < len(argv):
            index += 2
            continue
        if argument.startswith("repos/"):
            endpoint = argument
        index += 1
    if not endpoint:
        return None
    return method, endpoint


def _store_builtin_gh_tag_object(
    state: HarnessShimState,
    payload: HarnessBuiltinGhTagObject,
) -> str:
    """Persist one synthetic GitHub tag object payload in shim state."""

    tag_objects = state.gh_tag_objects
    fake_sha = f"harness-tag-object-{len(tag_objects) + 1}"
    tag_objects[fake_sha] = payload
    return fake_sha


def _apply_builtin_gh_tag_ref(
    state: HarnessShimState,
    endpoint: str,
    payload: HarnessBuiltinGhRefMutationPayload,
    *,
    force: bool,
) -> None:
    """Create or update a local annotated Git tag from a synthetic GitHub ref mutation."""

    ref_name = payload.ref or f"refs/tags/{endpoint.rsplit('/', 1)[-1]}"
    tag_name = ref_name.removeprefix("refs/tags/")
    target_sha = payload.sha or ""
    tag_payload = state.gh_tag_objects.get(target_sha) or HarnessBuiltinGhTagObject()
    target_commit = str(tag_payload.object or "")
    if not tag_name or not target_commit:
        raise SystemExit(
            "buildish-release-harness: builtin gh tag ref mutation is missing tag metadata"
        )
    message = str(tag_payload.message or tag_name)
    for repository in builtin_gh_mutated_repositories(state):
        command = ["git", "-C", str(repository), "tag"]
        if force:
            command.append("-f")
        command.extend(["-a", tag_name, "-m", message, target_commit])
        run_harness_command(command, check=True, capture_output=True, text=True)


def builtin_gh_mutated_repositories(state: HarnessShimState) -> list[Path]:
    """Return the local repositories that should reflect synthetic GitHub tag mutations."""

    workspace_root = Path(state.workspace_root)
    origin_root = workspace_root / ".buildish-release-harness" / "git-origins" / "self"
    return [workspace_root, origin_root]


HarnessBuiltinGhRefMutationPayload.schema_export = SchemaExportSpecification(
    filename="harness-builtin-gh-ref-mutation-payload.schema.json",
    audience="internal",
    stability="stable",
    summary="Harness shim builtin payload describing a synthetic GitHub ref mutation request.",
)
