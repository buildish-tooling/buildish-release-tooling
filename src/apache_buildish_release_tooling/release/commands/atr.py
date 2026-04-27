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

"""Optional ATR publication and check-reporting commands."""

from __future__ import annotations

import json
import os
import re
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.models import AtrConfig, CommandContext, PrepareRcState
from apache_buildish_release_tooling.release.process import run_logged_command
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.rc_vote_verification import (
    required_rc_vote_manifest_file_names,
    required_source_release_file_names,
)
from apache_buildish_release_tooling.release.summary import SummaryWriter

from apache_buildish_release_tooling.release.commands._shared import (
    _append_github_outputs,
    _context,
    _manifest_path,
    _resolve_prepare_rc_state_from_args,
    _temporary_build_dir,
)


@dataclass(frozen=True)
class AtrRuntimeConfig:
    """Resolved non-secret and secret runtime ATR client settings."""

    base_url: str
    host: str
    committee: str
    project_key: str
    asf_uid: str
    pat: str
    strict_checking: bool


@dataclass(frozen=True)
class AtrCheckSummary:
    """Parsed ATR check-status output for one revision."""

    output: str
    revision: str | None
    total_checks: int
    counts: dict[str, int]

    @property
    def hard_failure_count(self) -> int:
        return self.counts.get("failure", 0) + self.counts.get("exception", 0)


def _required_atr_config(context: CommandContext) -> AtrConfig:
    atr = context.component_config.atr
    if atr is None or not atr.enabled:
        raise ValueError("ATR integration is not enabled for this component configuration")
    return atr


def _atr_host_from_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme:
        if not parsed.netloc:
            raise ValueError(f"ATR base_url must include a network location: {base_url}")
        return parsed.netloc
    if "/" in base_url.strip("/"):
        raise ValueError(f"ATR base_url must be an https:// URL or a bare host: {base_url}")
    return base_url.strip()


def _resolve_atr_runtime_config(context: CommandContext) -> AtrRuntimeConfig:
    atr = _required_atr_config(context)
    asf_uid = os.environ.get("BUILDISH_ATR_ASF_UID") or os.environ.get("ATR_ASF_UID")
    if not asf_uid:
        raise ValueError(
            "ATR authentication requires BUILDISH_ATR_ASF_UID or ATR_ASF_UID in the environment"
        )
    pat = os.environ.get("BUILDISH_ATR_PAT") or os.environ.get("ATR_PAT")
    if not pat:
        raise ValueError("ATR authentication requires BUILDISH_ATR_PAT or ATR_PAT in the environment")
    if atr.base_url is None or atr.committee is None or atr.product_line is None:
        raise ValueError("ATR config is incomplete for an enabled component")
    return AtrRuntimeConfig(
        base_url=atr.base_url.rstrip("/"),
        host=_atr_host_from_base_url(atr.base_url),
        committee=atr.committee,
        project_key=atr.product_line,
        asf_uid=asf_uid,
        pat=pat,
        strict_checking=atr.strict_checking,
    )


def _write_atr_client_config(config_path: Path, runtime: AtrRuntimeConfig) -> None:
    payload = {
        "atr": {
            "host": runtime.host,
        },
        "asf": {
            "uid": runtime.asf_uid,
        },
        "tokens": {
            "pat": runtime.pat,
        },
    }
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _atr_env(config_path: Path) -> dict[str, str]:
    return {
        "ATR_CLIENT_CONFIG_PATH": str(config_path),
    }


def _parse_json_output(stdout: str, *, source: str) -> dict[str, object]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError(f"{source} did not return a JSON object payload")
    return payload


def _atr_release_start_or_reuse(
    runtime: AtrRuntimeConfig,
    *,
    version: str,
    env: dict[str, str],
) -> tuple[dict[str, object], str]:
    command = ["atr", "release", "start", runtime.project_key, version]
    start_completed = run_logged_command(command, env=env, check=False)
    if start_completed.returncode == 0:
        return (
            _parse_json_output(start_completed.stdout, source="atr release start"),
            "created",
        )

    info_completed = run_logged_command(
        ["atr", "release", "info", runtime.project_key, version],
        env=env,
        check=False,
    )
    if info_completed.returncode == 0:
        return (
            _parse_json_output(info_completed.stdout, source="atr release info"),
            "reused",
        )

    start_detail = (start_completed.stderr or start_completed.stdout or "").strip()
    info_detail = (info_completed.stderr or info_completed.stdout or "").strip()
    raise ValueError(
        "ATR release could not be created or reused: "
        f"release start: {start_detail or f'exit code {start_completed.returncode}'}; "
        f"release info: {info_detail or f'exit code {info_completed.returncode}'}"
    )


def _atr_release_info(
    runtime: AtrRuntimeConfig,
    *,
    version: str,
    env: dict[str, str],
) -> dict[str, object]:
    completed = run_logged_command(
        ["atr", "release", "info", runtime.project_key, version],
        env=env,
    )
    return _parse_json_output(completed.stdout, source="atr release info")


def _atr_upload_file(
    runtime: AtrRuntimeConfig,
    *,
    version: str,
    relpath: str,
    local_path: Path,
    env: dict[str, str],
) -> dict[str, object]:
    completed = run_logged_command(
        [
            "atr",
            "upload",
            runtime.project_key,
            version,
            relpath,
            str(local_path),
        ],
        env=env,
    )
    return _parse_json_output(completed.stdout, source="atr upload")


def _atr_wait_for_checks(
    runtime: AtrRuntimeConfig,
    *,
    version: str,
    env: dict[str, str],
    revision: str | None,
    timeout_seconds: int,
    interval_ms: int,
) -> None:
    command = [
        "atr",
        "check",
        "wait",
        runtime.project_key,
        version,
        "--timeout",
        str(timeout_seconds),
        "--interval",
        str(interval_ms),
    ]
    if revision is not None:
        command.extend(["--revision", revision])
    run_logged_command(command, env=env, capture_output=True)


def _atr_check_status(
    runtime: AtrRuntimeConfig,
    *,
    version: str,
    env: dict[str, str],
    revision: str | None,
    verbose: bool,
) -> AtrCheckSummary:
    command = [
        "atr",
        "check",
        "status",
        runtime.project_key,
        version,
    ]
    if revision is not None:
        command.extend(["--revision", revision])
    if verbose:
        command.append("--verbose")
    completed = run_logged_command(command, env=env)
    output = completed.stdout.strip()
    total_checks = 0
    counts: dict[str, int] = {}
    total_match = re.search(r"(?m)^Total checks:\s+(?P<count>[0-9]+)\s*$", output)
    if total_match is not None:
        total_checks = int(total_match.group("count"))
    for status_match in re.finditer(r"(?m)^\s+(?P<status>[a-z_]+):\s+(?P<count>[0-9]+)", output):
        counts[status_match.group("status")] = int(status_match.group("count"))
    return AtrCheckSummary(
        output=output,
        revision=revision,
        total_checks=total_checks,
        counts=counts,
    )


def _staged_candidate_file_urls(context: CommandContext, state: PrepareRcState, version: str) -> list[tuple[str, str]]:
    staging_root = state.staging_url.rstrip("/")
    file_names = [
        *required_source_release_file_names(
            context.component_config.source_artifact_prefix,
            version,
        ),
        *required_rc_vote_manifest_file_names(),
    ]
    return [(file_name, f"{staging_root}/{file_name}") for file_name in file_names]


def _download_staged_candidate_files(
    context: CommandContext,
    state: PrepareRcState,
    *,
    version: str,
    download_root: Path,
) -> list[Path]:
    download_root.mkdir(parents=True, exist_ok=True)
    local_paths: list[Path] = []
    for file_name, file_url in _staged_candidate_file_urls(context, state, version):
        local_path = download_root / file_name
        local_path.write_bytes(read_uri_bytes(file_url))
        local_paths.append(local_path)
    return local_paths


def _release_latest_revision(release_payload: dict[str, object]) -> str | None:
    latest_revision = release_payload.get("latest_revision_number")
    if latest_revision is None:
        return None
    if not isinstance(latest_revision, str):
        raise ValueError("ATR release info returned a non-string latest_revision_number")
    return latest_revision


def _release_phase(release_payload: dict[str, object]) -> str:
    phase = release_payload.get("phase")
    if phase is None:
        return ""
    if not isinstance(phase, str):
        raise ValueError("ATR release info returned a non-string phase")
    return phase


def _append_publish_atr_summary(
    summary: SummaryWriter,
    *,
    runtime: AtrRuntimeConfig,
    version: str,
    state: PrepareRcState,
    release_mode: str,
    uploaded_files: list[Path],
    latest_revision: str | None,
    phase: str,
    waited_for_checks: bool,
    status_summary: AtrCheckSummary | None,
) -> None:
    summary.append_heading("Publish ATR candidate")
    summary.append_key_value_table(
        "Technical details",
        [
            ("Project", runtime.project_key),
            ("Version", version),
            ("RC tag", state.rc_tag),
            ("ATR base URL", runtime.base_url),
            ("ATR committee", runtime.committee),
            ("ATR release mode", release_mode),
            ("ATR latest revision", latest_revision or "<none>"),
            ("ATR phase", phase or "<none>"),
            ("Waited for checks", "true" if waited_for_checks else "false"),
        ],
    )
    summary.append_bullet_list("Uploaded files", [path.name for path in uploaded_files])
    if status_summary is not None:
        summary.append_plaintext_block("ATR check status", status_summary.output)
    summary.append_plaintext_block(
        "Outcome",
        "The staged RC source-release files and RC vote-manifest files were published to ATR via the "
        "official atr client wrapper.",
    )


def run_publish_atr_candidate(args: Namespace) -> Path:
    """Publish the staged RC source bundle and vote manifest files into ATR."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    runtime = _resolve_atr_runtime_config(context)
    manifest_path = _manifest_path(context.component_config.component_id, "publish-atr-candidate")
    summary = SummaryWriter.from_environment()
    with _temporary_build_dir("publish-atr-candidate") as temp_root:
        atr_config_path = temp_root / "atr.yaml"
        _write_atr_client_config(atr_config_path, runtime)
        env = _atr_env(atr_config_path)
        downloaded_files = _download_staged_candidate_files(
            context,
            state,
            version=version,
            download_root=temp_root / "atr-upload",
        )
        _release_payload, release_mode = _atr_release_start_or_reuse(
            runtime,
            version=version,
            env=env,
        )
        for local_path in downloaded_files:
            _atr_upload_file(
                runtime,
                version=version,
                relpath=local_path.name,
                local_path=local_path,
                env=env,
            )
        latest_release_payload = _atr_release_info(runtime, version=version, env=env)
        latest_revision = _release_latest_revision(latest_release_payload)
        phase = _release_phase(latest_release_payload)
        status_summary = None
        if args.wait_for_checks:
            _atr_wait_for_checks(
                runtime,
                version=version,
                env=env,
                revision=latest_revision,
                timeout_seconds=args.check_timeout_seconds,
                interval_ms=args.check_interval_ms,
            )
            status_summary = _atr_check_status(
                runtime,
                version=version,
                env=env,
                revision=latest_revision,
                verbose=False,
            )
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "publish-atr-candidate",
            "version": version,
            "rc_tag": state.rc_tag,
            "atr_base_url": runtime.base_url,
            "atr_committee": runtime.committee,
            "atr_project": runtime.project_key,
            "atr_release_mode": release_mode,
            "atr_phase": phase,
            "atr_latest_revision": latest_revision or "",
            "uploaded_file_names": ",".join(path.name for path in downloaded_files),
            "waited_for_checks": "true" if args.wait_for_checks else "false",
            "atr_total_checks": str(status_summary.total_checks if status_summary is not None else 0),
            "atr_failure_count": str(status_summary.counts.get("failure", 0) if status_summary is not None else 0),
            "atr_exception_count": str(
                status_summary.counts.get("exception", 0) if status_summary is not None else 0
            ),
            "atr_warning_count": str(status_summary.counts.get("warning", 0) if status_summary is not None else 0),
        },
    )
    _append_github_outputs(
        {
            "atr_project": runtime.project_key,
            "atr_latest_revision": latest_revision or "",
            "atr_phase": phase,
        }
    )
    _append_publish_atr_summary(
        summary,
        runtime=runtime,
        version=version,
        state=state,
        release_mode=release_mode,
        uploaded_files=downloaded_files,
        latest_revision=latest_revision,
        phase=phase,
        waited_for_checks=args.wait_for_checks,
        status_summary=status_summary,
    )
    return manifest_path


def _append_report_atr_checks_summary(
    summary: SummaryWriter,
    *,
    runtime: AtrRuntimeConfig,
    version: str,
    rc_tag: str,
    latest_revision: str | None,
    phase: str,
    check_summary: AtrCheckSummary,
    strict_failure: bool,
) -> None:
    summary.append_heading("Report ATR checks")
    summary.append_key_value_table(
        "Technical details",
        [
            ("Project", runtime.project_key),
            ("Version", version),
            ("RC tag", rc_tag),
            ("ATR base URL", runtime.base_url),
            ("ATR latest revision", latest_revision or "<none>"),
            ("Reported revision", check_summary.revision or latest_revision or "<none>"),
            ("ATR phase", phase or "<none>"),
            ("Strict checking", "true" if runtime.strict_checking else "false"),
            ("Would block release", "true" if strict_failure else "false"),
        ],
    )
    summary.append_plaintext_block("ATR check status", check_summary.output)
    summary.append_plaintext_block(
        "Outcome",
        "This command reports ATR check status and, when strict checking is enabled, fails when ATR "
        "reports one or more hard failures or exceptions.",
    )


def run_report_atr_checks(args: Namespace) -> Path:
    """Report ATR check status and optionally fail when strict ATR checks are enabled."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version, state = _resolve_prepare_rc_state_from_args(args, context, repo)
    runtime = _resolve_atr_runtime_config(context)
    manifest_path = _manifest_path(context.component_config.component_id, "report-atr-checks")
    summary = SummaryWriter.from_environment()
    with _temporary_build_dir("report-atr-checks") as temp_root:
        atr_config_path = temp_root / "atr.yaml"
        _write_atr_client_config(atr_config_path, runtime)
        env = _atr_env(atr_config_path)
        release_payload = _atr_release_info(runtime, version=version, env=env)
        latest_revision = _release_latest_revision(release_payload)
        phase = _release_phase(release_payload)
        requested_revision = args.revision or latest_revision
        check_summary = _atr_check_status(
            runtime,
            version=version,
            env=env,
            revision=requested_revision,
            verbose=args.verbose_atr_output,
        )
    strict_failure = runtime.strict_checking and check_summary.hard_failure_count > 0
    write_manifest(
        manifest_path,
        {
            "component": context.component_config.component_id,
            "action": "report-atr-checks",
            "version": version,
            "rc_tag": state.rc_tag,
            "atr_base_url": runtime.base_url,
            "atr_committee": runtime.committee,
            "atr_project": runtime.project_key,
            "atr_phase": phase,
            "atr_latest_revision": latest_revision or "",
            "atr_reported_revision": requested_revision or "",
            "atr_total_checks": str(check_summary.total_checks),
            "atr_failure_count": str(check_summary.counts.get("failure", 0)),
            "atr_exception_count": str(check_summary.counts.get("exception", 0)),
            "atr_warning_count": str(check_summary.counts.get("warning", 0)),
            "atr_success_count": str(check_summary.counts.get("success", 0)),
            "strict_checking": "true" if runtime.strict_checking else "false",
            "would_block_release": "true" if strict_failure else "false",
        },
    )
    _append_github_outputs(
        {
            "atr_latest_revision": latest_revision or "",
            "atr_would_block_release": "true" if strict_failure else "false",
            "atr_failure_count": str(check_summary.counts.get("failure", 0)),
            "atr_exception_count": str(check_summary.counts.get("exception", 0)),
        }
    )
    _append_report_atr_checks_summary(
        summary,
        runtime=runtime,
        version=version,
        rc_tag=state.rc_tag,
        latest_revision=latest_revision,
        phase=phase,
        check_summary=check_summary,
        strict_failure=strict_failure,
    )
    if strict_failure:
        raise ValueError(
            "ATR strict checking is enabled and ATR reported hard check failures or exceptions"
        )
    return manifest_path
