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

"""Command handlers for read-only RC verification."""

from __future__ import annotations

import sys
import tempfile
from argparse import Namespace
from pathlib import Path

from apache_buildish_release_tooling.release.command_logging import command_log_sink
from apache_buildish_release_tooling.release.config import load_component_config, validate_release_target_base_urls
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.summary import SummaryWriter
from apache_buildish_release_tooling.release.verification import VerifyRcPhase1Result, verify_rc_phase1
from apache_buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_failure,
    emit_section,
    emit_success,
    emit_title,
)

from apache_buildish_release_tooling.release.commands._shared import _append_github_outputs


def run_verify_rc(args: Namespace) -> None:
    """Run the Phase 1a read-only verifier against one signed RC vote manifest."""

    component_config = _optional_component_config(args)
    work_dir = _work_dir(args)
    log_path = _log_path(args, work_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_handle, command_log_sink(
        log_handle,
        echo_to_stderr=getattr(args, "verbose", False),
    ):
        progress_reporter = ProgressReporter.from_mode(
            getattr(args, "progress", "auto"),
            stream=sys.stderr,
            mirror_stream=log_handle,
            color_mode=getattr(args, "color", "auto"),
            prefix="",
            is_tty=sys.stderr.isatty(),
        )
        emit_title(progress_reporter, "Verify RC")
        emit_detail(progress_reporter, "Work directory", str(work_dir))
        emit_detail(progress_reporter, "Manifest URL", args.rc_vote_manifest_url)
        emit_detail(progress_reporter, "KEYS URL", args.keys_url)
        emit_detail(progress_reporter, "Transcript log", str(log_path))
        result = verify_rc_phase1(
            manifest_url=args.rc_vote_manifest_url,
            keys_url=args.keys_url,
            component_config=component_config,
            allow_non_production_release_targets=args.allow_non_production_release_targets,
            work_dir=work_dir,
            progress_reporter=progress_reporter,
        )
        report_json_path = _report_json_path(args, result)
        report_md_path = _report_md_path(args, result)
        write_manifest(report_json_path, result.report_payload)
        report_md_path.parent.mkdir(parents=True, exist_ok=True)
        report_md_path.write_text(result.report_markdown, encoding="utf-8")
        try:
            SummaryWriter.from_environment().append_markdown(result.report_markdown)
        except ValueError:
            pass
        github_outputs: dict[str, Path | str] = {
            "report_json_path": report_json_path,
            "report_md_path": report_md_path,
            "log_path": log_path,
        }
        if result.rc_tag is not None:
            github_outputs["rc_tag"] = result.rc_tag
        if result.source_commit_sha is not None:
            github_outputs["source_commit_sha"] = result.source_commit_sha
        _append_github_outputs(github_outputs)
        emit_section(progress_reporter, "Outcome")
        if result.verdict == "verified":
            emit_success(
                progress_reporter,
                f"Verified RC: {result.component_id} {result.version} ({result.rc_tag})",
            )
        else:
            emit_failure(
                progress_reporter,
                f"Verification failed with {len(result.failures)} issue(s)",
            )
        emit_detail(progress_reporter, "Report JSON", str(report_json_path))
        emit_detail(progress_reporter, "Report Markdown", str(report_md_path))
        emit_detail(progress_reporter, "Transcript log", str(log_path))
    if result.verdict != "verified":
        if not progress_reporter.enabled:
            failure_summary = " | ".join(failure.message for failure in result.failures)
            raise ValueError(
                f"verify-rc failed with {len(result.failures)} issue(s): {failure_summary}; "
                f"see {report_md_path} and {log_path}"
            )
        raise SystemExit(1)


def _optional_component_config(args: Namespace) -> ComponentConfig | None:
    config_path = getattr(args, "component_config", None)
    if not config_path:
        return None
    component_config = load_component_config(config_path)
    validate_release_target_base_urls(
        component_config,
        allow_non_production_release_targets=getattr(
            args, "allow_non_production_release_targets", False
        ),
    )
    return component_config


def _work_dir(args: Namespace) -> Path:
    explicit_work_dir = getattr(args, "work_dir", None)
    if explicit_work_dir:
        work_dir = Path(explicit_work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir
    build_dir = Path.cwd() / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="verify-rc.", dir=build_dir))


def _report_base_name(component_id: str | None, version: str | None, rc_tag: str | None) -> str:
    if component_id is not None and rc_tag is not None:
        return f"verify-rc-report-{component_id}-{rc_tag.replace('/', '-')}"
    if component_id is None or version is None:
        return "verify-rc-report"
    return f"verify-rc-report-{component_id}-{version}"


def _report_json_path(args: Namespace, result: VerifyRcPhase1Result) -> Path:
    explicit_path = getattr(args, "report_json", None)
    if explicit_path:
        return Path(explicit_path)
    return result.work_dir / f"{_report_base_name(result.component_id, result.version, result.rc_tag)}.json"


def _report_md_path(args: Namespace, result: VerifyRcPhase1Result) -> Path:
    explicit_path = getattr(args, "report_md", None)
    if explicit_path:
        return Path(explicit_path)
    return result.work_dir / f"{_report_base_name(result.component_id, result.version, result.rc_tag)}.md"


def _log_path(args: Namespace, work_dir: Path) -> Path:
    explicit_path = getattr(args, "log_path", None)
    if explicit_path:
        return Path(explicit_path)
    return work_dir / "verify-rc.log"
