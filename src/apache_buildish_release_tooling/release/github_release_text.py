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

"""GitHub Release title and body rendering."""

from __future__ import annotations

from apache_buildish_release_tooling.release.models import ComponentConfig, PrepareRcState
from apache_buildish_release_tooling.release.release_text import incubator_disclaimer_section


def _append_optional_section(lines: list[str], section: str) -> None:
    if not section:
        return
    lines.extend(["", section])


def _draft_metadata_lines(component_config: ComponentConfig, state: PrepareRcState) -> list[str]:
    return [
        f"RC tag: {state.rc_tag}",
        f"Final tag: {state.final_tag}",
        f"Resolved source ref: {state.resolved_source_ref}",
        f"ASF SVN staging URL: {state.staging_url}",
        f"Final tag mode: {component_config.final_tag_mode}",
    ]


def render_draft_github_release_body(
    component_config: ComponentConfig,
    *,
    state: PrepareRcState,
) -> str:
    """Render the initial draft GitHub Release body."""

    lines = [
        f"Draft GitHub Release placeholder for {component_config.vote_release_name} {state.final_tag.removeprefix('v')}.",
    ]
    _append_optional_section(
        lines,
        incubator_disclaimer_section(component_config, heading="## Incubating Disclaimer"),
    )
    lines.extend(
        [
            "",
            *_draft_metadata_lines(component_config, state),
            "",
            "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
        ]
    )
    return "\n".join(lines)


def render_finalized_draft_github_release_body(
    component_config: ComponentConfig,
    *,
    state: PrepareRcState,
    authoritative_manifest_url: str,
    bootstrap_script_url: str,
    bootstrap_invoker: str,
) -> str:
    """Render the draft GitHub Release body after RC vote materials exist."""

    lines = [
        f"Draft GitHub Release placeholder for {component_config.vote_release_name} {state.final_tag.removeprefix('v')}.",
    ]
    _append_optional_section(
        lines,
        incubator_disclaimer_section(component_config, heading="## Incubating Disclaimer"),
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
