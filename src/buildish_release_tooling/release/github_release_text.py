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

"""GitHub Release title and body rendering."""

from __future__ import annotations

from buildish_release_tooling.release.contracts import (
    IncubatorDisclaimer,
    RcVoteManifestV1,
)
from buildish_release_tooling.release.models import (
    ComponentConfig,
    PrepareRcState,
)
from buildish_release_tooling.release.release_text import (
    incubator_disclaimer_section,
)


def _append_optional_section(lines: list[str], section: str) -> None:
    if not section:
        return
    lines.extend(["", section])


def _draft_metadata_lines(
    component_config: ComponentConfig, state: PrepareRcState
) -> list[str]:
    return [
        f"Candidate tag: {state.rc_tag}",
        f"Final tag: {state.final_tag}",
        f"Resolved source ref: {state.resolved_source_ref}",
        f"ASF SVN staging URL: {state.staging_url}",
        f"Final tag mode: {component_config.final_tag_mode}",
    ]


def _release_url(component_config: ComponentConfig, version: str) -> str:
    return f"{component_config.asf_dist_release_base.rstrip('/')}/{version}/"


def _source_release_lines(
    component_config: ComponentConfig, version: str, vote_manifest: RcVoteManifestV1
) -> list[str]:
    source_artifact = vote_manifest.vote_materials.source_artifacts[0]
    source_url = f"{_release_url(component_config, version)}{source_artifact.filename}"
    return [
        "Source artifact:",
        f"- {source_url}",
        f"- {source_url}.sha512",
        f"- {source_url}.asc",
    ]


def render_draft_github_release_body(
    component_config: ComponentConfig,
    *,
    state: PrepareRcState,
    incubator_disclaimer: IncubatorDisclaimer | None,
    candidate_visibility: str = "draft",
) -> str:
    """Render the initial candidate GitHub Release body."""

    lines = [
        f"Candidate GitHub Release placeholder for {component_config.vote_release_name} {state.final_tag.removeprefix('v')}.",
    ]
    _append_optional_section(
        lines,
        incubator_disclaimer_section(
            incubator_disclaimer, heading="## Incubating Disclaimer"
        ),
    )
    lines.extend(
        [
            "",
            *_draft_metadata_lines(component_config, state),
            "",
        ]
    )
    if candidate_visibility == "draft":
        lines.append(
            "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes."
        )
    elif candidate_visibility == "public-prerelease":
        lines.append(
            "This public candidate GitHub Release is convenience metadata only. "
            "It is not an official ASF release and must be marked as a GitHub pre-release."
        )
    else:
        raise ValueError(f"unsupported candidate visibility: {candidate_visibility}")
    return "\n".join(lines)


def render_final_github_release_body(
    component_config: ComponentConfig,
    *,
    version: str,
    vote_manifest: RcVoteManifestV1,
) -> str:
    """Render the public GitHub Release body for a finalized release."""

    lines = [
        f"{component_config.vote_release_name} {version}",
    ]
    _append_optional_section(
        lines,
        incubator_disclaimer_section(
            vote_manifest.incubator_disclaimer,
            heading="## Incubating Disclaimer",
        ),
    )
    lines.extend(
        [
            "",
            "Candidate tag:",
            f"- {vote_manifest.rc_tag}",
            "",
            "## Authoritative Source Release",
            "",
            "The authoritative ASF source release is available from:",
            f"- {_release_url(component_config, version)}",
            "",
            *_source_release_lines(component_config, version, vote_manifest),
            "",
            "KEYS:",
            f"- {component_config.asf_keys_url}",
            "",
            "Release verification guide:",
            f"- {component_config.release_verification_guide_url}",
            "",
            "## GitHub Release",
            "",
            (
                "This GitHub Release is provided as convenience metadata only. "
                "GitHub release assets are convenience artifacts and are not the authoritative ASF release."
            ),
        ]
    )
    return "\n".join(lines)


def render_finalized_draft_github_release_body(
    component_config: ComponentConfig,
    *,
    state: PrepareRcState,
    incubator_disclaimer: IncubatorDisclaimer | None,
    authoritative_manifest_url: str,
    bootstrap_script_url: str,
    bootstrap_invoker: str,
) -> str:
    """Render the draft GitHub Release body after RC vote materials exist."""

    lines = [
        f"Candidate GitHub Release placeholder for {component_config.vote_release_name} {state.final_tag.removeprefix('v')}.",
    ]
    _append_optional_section(
        lines,
        incubator_disclaimer_section(
            incubator_disclaimer, heading="## Incubating Disclaimer"
        ),
    )
    lines.extend(
        [
            "",
            *_draft_metadata_lines(component_config, state),
            "",
            "Authoritative RC vote manifest:",
            f"- {authoritative_manifest_url}",
            f"- {authoritative_manifest_url}.sha512",
            f"- {authoritative_manifest_url}.asc",
            "",
            "Verification bootstrap convenience:",
            f"- {bootstrap_script_url}",
            f"- {bootstrap_script_url}.sha512",
            f"- {bootstrap_script_url}.asc",
            "",
            "Verify RC bootstrap one-liner:",
            "",
            "```sh",
            bootstrap_invoker,
            "```",
            "",
            "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
        ]
    )
    return "\n".join(lines)
