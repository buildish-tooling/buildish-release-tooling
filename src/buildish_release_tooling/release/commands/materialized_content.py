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

"""Modern digest-bound materialization commands; builds remain component-owned."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from buildish_release_tooling.release.commands._shared import (
    _context,
    _manifest_path,
    _append_github_outputs,
)
from buildish_release_tooling.release.core.state import (
    DirectReleaseState,
    CandidateReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.materialized_content import (
    MaterializedState,
    export_materialization,
    import_materialization,
    validate_original_state,
)
from buildish_release_tooling.release.summary import SummaryWriter
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_pydantic_json_file_bounded,
)


def _state(args: Namespace) -> MaterializedState:
    for key, model in (
        ("candidate_state", CandidateReleaseState),
        ("release_state", DirectReleaseState),
        ("promotion_state", PromotionState),
    ):
        path = getattr(args, key, None)
        if path:
            state = read_pydantic_json_file_bounded(
                model, Path(path), max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES
            )
            if not isinstance(
                state, (DirectReleaseState, CandidateReleaseState, PromotionState)
            ):
                raise ValueError("unsupported materialization state")
            config = _context(args).release_config
            expected = (
                "direct" if isinstance(state, DirectReleaseState) else "candidate"
            )
            if (
                config.component.id != state.release.component.id
                or config.lifecycle.mode != expected
            ):
                raise ValueError(
                    "materialization state component/lifecycle does not match trusted configuration"
                )
            return state
    raise ValueError("materialization requires an exact release state")


def run_bind_materialization(args: Namespace) -> Path:
    """Bind producer-generated M to S and export objects; never build or push."""
    state = _state(args)
    config = _context(args).release_config
    repo = GitRepository.from_current_worktree()
    binding = export_materialization(
        repo,
        config,
        state,
        commit=args.materialized_commit,
        bundle=Path(args.bundle_output),
    )
    payload = state.model_dump(mode="json")
    payload["materialization"] = binding.model_dump(mode="json")
    if isinstance(state, CandidateReleaseState):
        payload["candidate"]["tag"]["target_commit"] = binding.commit_sha
        payload["final_tag_identity"]["target_commit"] = binding.commit_sha
    else:
        payload["final_tag"]["target_commit"] = binding.commit_sha
    state = type(state).model_validate(payload)
    result_path = _manifest_path(state.release.component.id, "bind-materialization")
    write_manifest(result_path, state, exclude_none=True)
    _append_github_outputs(
        {
            "materialized_commit_sha": binding.commit_sha,
            "bundle_sha256": binding.bundle_sha256,
        }
    )
    summary = SummaryWriter.from_environment()
    summary.append_heading("Bind materialized Git content")
    summary.append_plaintext_block("Reviewed source", state.source.commit_sha)
    summary.append_plaintext_block("Materialized commit", binding.commit_sha)
    summary.append_plaintext_block("Git bundle SHA-256", binding.bundle_sha256)
    return result_path


def run_import_materialization(args: Namespace) -> Path:
    """Import a producer bundle into the trusted checkout without executing content."""
    state = _state(args)
    if isinstance(state, PromotionState) and args.source_state:
        raise ValueError(
            "promotion imports bind to the approved candidate manifest, not --source-state"
        )
    if not isinstance(state, PromotionState):
        if not args.source_state:
            raise ValueError(
                "import requires --source-state from the original trusted resolution job"
            )
        original = read_pydantic_json_file_bounded(
            type(state),
            Path(args.source_state),
            max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
        )
        validate_original_state(state, original)
    import_materialization(
        GitRepository.from_current_worktree(),
        _context(args).release_config,
        state,
        bundle=Path(args.bundle),
        expected_sha256=args.bundle_sha256,
    )
    result_path = _manifest_path(state.release.component.id, "import-materialization")
    write_manifest(result_path, state, exclude_none=True)
    return result_path
