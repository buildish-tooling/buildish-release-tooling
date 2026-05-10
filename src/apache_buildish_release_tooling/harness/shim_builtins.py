# Copyright 2026 The Apache Software Foundation
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
import sys
from pathlib import Path

from pydantic import Field

from apache_buildish_release_tooling.docs.documentation import RuntimeDerivedModel
from apache_buildish_release_tooling.docs.documentation import SchemaExportSpecification
from apache_buildish_release_tooling.harness.models import (
    HarnessBuiltinGhTagObject,
    HarnessShimState,
    ToolBehaviorResult,
)
from apache_buildish_release_tooling.harness.process import run_harness_command


class HarnessBuiltinGhRefMutationPayload(RuntimeDerivedModel):
    """Synthetic GitHub tag-ref mutation payload consumed by the harness shim."""

    ref: str | None = Field(default=None, description="Git ref name observed or created during the related operation.")
    sha: str | None = Field(default=None, description="Git object SHA associated with one synthetic harness GitHub ref mutation payload.")


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

    parsed = _parse_gh_api_request(argv)
    if parsed is None:
        return None
    method, endpoint = parsed
    if method == "POST" and endpoint.endswith("/git/tags"):
        stdin_text = sys.stdin.read()
        tag_object_payload = HarnessBuiltinGhTagObject.model_validate(json.loads(stdin_text or "{}"))
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
    return None


def _load_ref_mutation_payload() -> HarnessBuiltinGhRefMutationPayload:
    """Load one synthetic GitHub tag-ref mutation payload from stdin."""

    return HarnessBuiltinGhRefMutationPayload.model_validate(json.loads(sys.stdin.read() or "{}"))


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
        raise SystemExit("buildish-release-harness: builtin gh tag ref mutation is missing tag metadata")
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
