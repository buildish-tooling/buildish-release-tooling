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

"""ASF-style email template rendering for release workflow summaries."""

from __future__ import annotations

from dataclasses import dataclass
from string import Template
from textwrap import dedent
from typing import Any, cast

from apache_buildish_release_tooling.release.models import ComponentConfig, PrepareRcState


@dataclass(frozen=True)
class RenderedEmail:
    """Fully rendered subject/body pair for one human-sent release email."""

    subject: str
    body: str


def _display_version(component_config: ComponentConfig, version: str) -> str:
    """Render the human-facing release version label for one component."""

    if component_config.incubator_vote_enabled:
        return f"{version}-incubating"
    return version


def _release_display_name(component_config: ComponentConfig, version: str) -> str:
    """Render the full human-facing release name used in emails."""

    return f"{component_config.vote_release_name} {_display_version(component_config, version)}"


def _rc_label(rc_number: int) -> str:
    """Render the human-facing RC label used in email subjects."""

    return f"RC{rc_number}"


def _render_template(template_text: str, values: dict[str, str]) -> str:
    """Render one strict stdlib template and trim leading/trailing blank lines."""

    return Template(dedent(template_text).strip()).substitute(values)


def _string_field(payload: dict[str, Any], key: str) -> str:
    """Resolve one required string field from a manifest-style payload."""

    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"expected non-empty string field: {key}")
    return value


def _mapping_field(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Resolve one required mapping field from a manifest-style payload."""

    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"expected mapping field: {key}")
    return cast(dict[str, Any], value)


def _list_field(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Resolve one required list-of-mappings field from a manifest-style payload."""

    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"expected list field: {key}")
    mappings: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"expected list item mapping in field: {key}")
        mappings.append(cast(dict[str, Any], item))
    return mappings


def _artifact_block(label: str, artifacts: list[dict[str, Any]]) -> str:
    """Render one artifact-group section for a plain-text ASF email."""

    lines = [f"{label}:"]
    if not artifacts:
        lines.append("* <none>")
        return "\n".join(lines)
    for artifact in artifacts:
        filename = str(artifact.get("filename") or artifact.get("uri") or "<unnamed artifact>")
        lines.append(f"* {filename}")
        artifact_uri = artifact.get("uri")
        if isinstance(artifact_uri, str) and artifact_uri:
            lines.append(f"  URL: {artifact_uri}")
        checksums = artifact.get("checksums")
        if isinstance(checksums, dict):
            for algorithm, checksum_payload in checksums.items():
                if not isinstance(checksum_payload, dict):
                    continue
                checksum_value = checksum_payload.get("value")
                checksum_uri = checksum_payload.get("uri")
                if isinstance(checksum_value, str) and checksum_value:
                    lines.append(f"  {algorithm.upper()}: {checksum_value}")
                if isinstance(checksum_uri, str) and checksum_uri:
                    lines.append(f"  {algorithm.upper()} file: {checksum_uri}")
        signatures = artifact.get("signatures")
        if isinstance(signatures, list):
            for signature in signatures:
                if not isinstance(signature, dict):
                    continue
                signature_uri = signature.get("uri")
                if isinstance(signature_uri, str) and signature_uri:
                    lines.append(f"  Signature: {signature_uri}")
    return "\n".join(lines)


def _draft_release_block(draft_release_url: str) -> str:
    """Render the optional draft GitHub Release section for RC vote emails."""

    if not draft_release_url:
        return "Draft GitHub Release mirror:\n* <none>"
    return "\n".join(
        [
            "Draft GitHub Release mirror:",
            f"* {draft_release_url}",
            "  Draft-only convenience metadata. Do not publish the GitHub Release until the ASF vote passes.",
        ]
    )


def _verification_bootstrap_block(
    *,
    bootstrap_script_url: str | None,
    bootstrap_invoker: str | None,
) -> str:
    """Render the optional verification-bootstrap section for plain-text templates."""

    if not bootstrap_script_url or not bootstrap_invoker:
        return ""
    indented_invoker = "\n".join(f"  {line}" for line in bootstrap_invoker.splitlines())
    return "\n".join(
        [
            "Verification bootstrap convenience:",
            f"* Bootstrap script: {bootstrap_script_url}",
            "* Example invoker:",
            indented_invoker,
        ]
    )


def _project_vote_binding_text(component_config: ComponentConfig) -> str:
    """Render the binding-vote guidance for a project vote email."""

    if component_config.incubator_vote_enabled:
        return (
            "Only PPMC members and mentors have binding votes, but other community\n"
            "members are encouraged to cast non-binding votes. This vote will pass if\n"
            "there are 3 binding +1 votes and more binding +1 votes than -1 votes."
        )
    return (
        "Only PMC members have binding votes, but other community\n"
        "members are encouraged to cast non-binding votes. This vote will pass if\n"
        "there are 3 binding +1 votes and more binding +1 votes than -1 votes."
    )


def _incubator_vote_binding_text() -> str:
    """Render the binding-vote guidance for a podling IPMC vote request."""

    return (
        "Only IPMC members have binding votes, but other community\n"
        "members are encouraged to cast non-binding votes. This vote will pass if\n"
        "there are 3 binding +1 votes and more binding +1 votes than -1 votes."
    )


def render_project_rc_vote_email(
    *,
    component_config: ComponentConfig,
    state: PrepareRcState,
    rc_tag_target_commit: str,
    manifest_payload: dict[str, Any],
    draft_release_url: str,
    bootstrap_script_url: str | None = None,
    bootstrap_invoker: str | None = None,
) -> RenderedEmail:
    """Render the project mailing-list RC vote email from authoritative RC state."""

    trust_roots = _mapping_field(manifest_payload, "trust_roots")
    asf_keys = _mapping_field(trust_roots, "asf_keys")
    vote_materials = _mapping_field(manifest_payload, "vote_materials")
    verification = _mapping_field(manifest_payload, "verification")
    authoritative_manifest = _mapping_field(verification, "authoritative_manifest")
    source_artifacts = _list_field(vote_materials, "source_artifacts")
    secondary_artifacts = _list_field(vote_materials, "secondary_artifacts")
    version = state.final_tag.removeprefix("v")
    release_display_name = _release_display_name(component_config, version)
    source_commit_lines = [f"* Git tag target commit SHA: {rc_tag_target_commit}"]
    if rc_tag_target_commit != state.resolved_source_ref:
        source_commit_lines.append(f"* Source commit SHA: {state.resolved_source_ref}")
    body = _render_template(
        """
        Hi all,

        I propose that we release the following RC as the official ${release_display_name} release.

        Provenance information:
        * Git tag: ${rc_tag}
        ${source_commit_lines}
        * Release branch: ${release_branch}
        * Final Git tag after approval: ${final_tag}

        ASF SVN RC staging:
        * ${staging_url}

        ${source_artifacts_block}

        ${secondary_artifacts_block}

        KEYS:
        * ${keys_url}

        Buildish RC vote-manifest:
        * ${manifest_url}
          SHA512 file: ${manifest_sha512_url}
          Signature: ${manifest_signature_url}

        ${draft_release_block}
        ${verification_bootstrap_block}

        Please download, verify, and test according to the release verification guide, which can be found at:
        ${release_verification_guide_url}

        Please vote in the next 72 hours.

        [ ] +1 Release this as ${release_display_name}
        [ ] +0
        [ ] -1 Do not release this because...

        ${binding_vote_text}

        Thanks,
        <name>
        """,
        {
            "release_display_name": release_display_name,
            "rc_tag": state.rc_tag,
            "source_commit_lines": "\n".join(source_commit_lines),
            "release_branch": state.resolved_release_branch,
            "final_tag": state.final_tag,
            "staging_url": state.staging_url,
            "source_artifacts_block": _artifact_block("Source artifacts", source_artifacts),
            "secondary_artifacts_block": _artifact_block(
                "Secondary artifacts under vote",
                secondary_artifacts,
            ),
            "keys_url": _string_field(asf_keys, "uri"),
            "manifest_url": _string_field(authoritative_manifest, "uri"),
            "manifest_sha512_url": _string_field(
                _mapping_field(authoritative_manifest, "checksum_uris"),
                "sha512",
            ),
            "manifest_signature_url": _string_field(
                _list_field(authoritative_manifest, "signatures")[0],
                "uri",
            ),
            "draft_release_block": _draft_release_block(draft_release_url),
            "verification_bootstrap_block": _verification_bootstrap_block(
                bootstrap_script_url=bootstrap_script_url,
                bootstrap_invoker=bootstrap_invoker,
            ),
            "release_verification_guide_url": component_config.release_verification_guide_url,
            "binding_vote_text": _project_vote_binding_text(component_config),
        },
    )
    return RenderedEmail(
        subject=f"[VOTE] Release {release_display_name} ({_rc_label(state.rc_number)})",
        body=body,
    )


def render_incubator_rc_vote_email(
    *,
    component_config: ComponentConfig,
    state: PrepareRcState,
    manifest_payload: dict[str, Any],
    bootstrap_script_url: str | None = None,
    bootstrap_invoker: str | None = None,
) -> RenderedEmail:
    """Render the later-use IPMC vote request email for podling releases."""

    verification = _mapping_field(manifest_payload, "verification")
    authoritative_manifest = _mapping_field(verification, "authoritative_manifest")
    version = state.final_tag.removeprefix("v")
    release_display_name = _release_display_name(component_config, version)
    body = _render_template(
        """
        Hi all,

        The ${project_name} community has voted and approved the release of
        ${release_display_name} (${rc_label}). We now kindly request the IPMC members to review and vote for this release.

        ${project_name} community vote thread:
        * <TODO: add the project vote thread URL>

        Vote result thread:
        * <TODO: add the project vote result thread URL>

        RC vote-manifest:
        * ${manifest_url}

        ${verification_bootstrap_block}

        Please download, verify, and test according to the release verification guide, which can be found at:
        ${release_verification_guide_url}

        Please vote in the next 72 hours.

        [ ] +1 Release this as ${release_display_name}
        [ ] +0
        [ ] -1 Do not release this because...

        ${binding_vote_text}

        Thanks,
        <name>
        """,
        {
            "project_name": component_config.vote_release_name,
            "release_display_name": release_display_name,
            "rc_label": _rc_label(state.rc_number),
            "manifest_url": _string_field(authoritative_manifest, "uri"),
            "verification_bootstrap_block": _verification_bootstrap_block(
                bootstrap_script_url=bootstrap_script_url,
                bootstrap_invoker=bootstrap_invoker,
            ),
            "release_verification_guide_url": component_config.release_verification_guide_url,
            "binding_vote_text": _incubator_vote_binding_text(),
        },
    )
    return RenderedEmail(
        subject=f"[VOTE] Release {release_display_name} ({_rc_label(state.rc_number)})",
        body=body,
    )


def render_project_vote_result_email(
    *,
    component_config: ComponentConfig,
    version: str,
    rc_number: int,
) -> RenderedEmail:
    """Render the project vote-result email with human-fill vote-count placeholders."""

    release_display_name = _release_display_name(component_config, version)
    body = _render_template(
        """
        Thanks to everyone who participated in the vote for Release ${release_display_name} (${rc_label}).

        The vote result is:

        +1: <TODO: binding count> (binding), <TODO: non-binding count> (non-binding)
        +0: <TODO: +0 count or 'none'>
        -1: <TODO: -1 count or 'none'>

        <TODO: summarize the final vote outcome, for example: "No +0 or -1 votes were recorded, hence the release candidate passed.">

        We will proceed with publishing the approved artifacts and sending out the
        announcement soon.

        Best,
        <name>
        """,
        {
            "release_display_name": release_display_name,
            "rc_label": _rc_label(rc_number),
        },
    )
    return RenderedEmail(
        subject=f"[RESULT][VOTE] Release {release_display_name} ({_rc_label(rc_number)})",
        body=body,
    )


def render_announce_email(
    *,
    component_config: ComponentConfig,
    version: str,
) -> RenderedEmail:
    """Render the final ANNOUNCE email with a human-fill placeholder section."""

    release_display_name = _release_display_name(component_config, version)
    body = _render_template(
        """
        Hello everyone,

        The ${project_name} team is pleased to announce ${release_display_name}.

        <TODO: add release-specific announcement content>
        """,
        {
            "project_name": component_config.vote_release_name,
            "release_display_name": release_display_name,
        },
    )
    return RenderedEmail(
        subject=f"[ANNOUNCE] {release_display_name}",
        body=body,
    )
