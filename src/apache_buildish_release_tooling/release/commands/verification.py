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

import os
import re
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from typing import Literal, cast

from apache_buildish_release_tooling.release.command_logging import command_log_sink
from apache_buildish_release_tooling.release.config import (
    load_component_config,
    load_verify_rc_override_config,
    validate_release_target_base_urls,
)
from apache_buildish_release_tooling.release.contracts import (
    InspectionBundleSection,
)
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
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
from apache_buildish_release_tooling.release.verification.inspect_repro import inspect_repro_report
from apache_buildish_release_tooling.release.verification.inspection import (
    inspect_repro_report_json,
)
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    INSPECTION_BUNDLE_MANIFEST_FILENAME,
    write_inspection_bundle_manifest,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    prompt_for_candidate_code_execution,
    validate_rebuild_profile_overrides,
)
from apache_buildish_release_tooling.release.verification.schemas import VerifyRcReportV1

from apache_buildish_release_tooling.release.commands._shared import _append_github_outputs

_SAFE_REPORT_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def run_verify_rc(args: Namespace) -> None:
    """Run the Phase 1a read-only verifier against one signed RC vote manifest."""

    component_config = _optional_component_config(args)
    profile_overrides = _optional_profile_overrides(args, component_config=component_config)
    work_dir = _work_dir(args)
    log_path = _log_path(args, work_dir)
    inspection_bundle_path = _requested_inspection_bundle_path(args, work_dir)
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
            requested_mode=cast(
                Literal["auto", "integrity-only", "full"],
                getattr(args, "mode", "auto"),
            ),
            interactive_input_enabled=sys.stdin.isatty() and sys.stdout.isatty(),
            confirm_candidate_code_execution=prompt_for_candidate_code_execution,
            inspection_bundle_path=inspection_bundle_path,
            profile_overrides=profile_overrides,
        )
        report_json_path = _report_json_path(args, result)
        report_md_path = _report_md_path(args, result)
        finalized_inspection_bundle_path = _finalize_inspection_bundle_path(
            args,
            result,
            requested_path=inspection_bundle_path,
        )
        report_payload, report_markdown = _finalized_report_outputs(
            result,
            report_json_path=report_json_path,
            inspection_bundle_path=finalized_inspection_bundle_path,
        )
        if finalized_inspection_bundle_path is not None:
            write_inspection_bundle_manifest(
                finalized_inspection_bundle_path,
                report_payload=report_payload,
            )
        write_manifest(report_json_path, report_payload)
        report_md_path.parent.mkdir(parents=True, exist_ok=True)
        report_md_path.write_text(report_markdown, encoding="utf-8")
        try:
            SummaryWriter.from_environment().append_markdown(report_markdown)
        except ValueError:
            pass
        github_outputs: dict[str, Path | str] = {
            "report_json_path": report_json_path,
            "report_md_path": report_md_path,
            "log_path": log_path,
        }
        if finalized_inspection_bundle_path is not None:
            github_outputs["inspection_bundle_path"] = finalized_inspection_bundle_path
        if result.rc_tag is not None:
            github_outputs["rc_tag"] = result.rc_tag
        if result.source_commit_sha is not None:
            github_outputs["source_commit_sha"] = result.source_commit_sha
        if result.source_date_epoch is not None:
            github_outputs["source_date_epoch"] = str(result.source_date_epoch)
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
        if finalized_inspection_bundle_path is not None:
            emit_detail(progress_reporter, "Inspection bundle", str(finalized_inspection_bundle_path))
            emit_detail(
                progress_reporter,
                "Inspect reproducibility",
                f"buildish-release-tooling inspect-repro {report_json_path}",
            )
    if result.verdict != "verified":
        if not progress_reporter.enabled:
            failure_summary = " | ".join(failure.message for failure in result.failures)
            raise ValueError(
                f"verify-rc failed with {len(result.failures)} issue(s): {failure_summary}; "
                f"see {report_md_path} and {log_path}"
            )
        raise SystemExit(1)


def run_inspect_repro(args: Namespace) -> str | None:
    """Inspect one saved verify-rc report plus its curated reproducibility bundle."""

    if bool(getattr(args, "json", False)):
        if bool(getattr(args, "compact", False)):
            raise ValueError("--compact is only supported for the human inspect-repro transcript")
        payload = inspect_repro_report_json(
            Path(args.report_json),
            artifact_ids=tuple(getattr(args, "artifact_ids", [])),
            failure_classes=tuple(getattr(args, "failure_classes", [])),
            summary_only=bool(getattr(args, "summary_only", False)),
        )
        return payload.model_dump_json(indent=2, exclude_none=True)
    progress_reporter = ProgressReporter.from_mode(
        "on",
        stream=sys.stderr,
        color_mode=getattr(args, "color", "auto"),
        prefix="",
        is_tty=sys.stderr.isatty(),
    )
    inspect_repro_report(
        Path(args.report_json),
        progress_reporter=progress_reporter,
        artifact_ids=tuple(getattr(args, "artifact_ids", [])),
        failure_classes=tuple(getattr(args, "failure_classes", [])),
        summary_only=bool(getattr(args, "summary_only", False)),
        compact=bool(getattr(args, "compact", False)),
    )
    return None


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


def _optional_profile_overrides(
    args: Namespace,
    *,
    component_config: ComponentConfig | None,
) -> VerifyRcOverrideConfig | None:
    override_file = getattr(args, "repro_override_file", None)
    if not override_file:
        return None
    if component_config is None:
        raise ValueError("--repro-override-file requires --component-config")
    profile_overrides = load_verify_rc_override_config(override_file)
    validate_rebuild_profile_overrides(component_config, profile_overrides)
    return profile_overrides


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
        return (
            "verify-rc-report-"
            f"{_safe_report_component(component_id)}-{_safe_report_component(rc_tag)}"
        )
    if component_id is None or version is None:
        return "verify-rc-report"
    return f"verify-rc-report-{_safe_report_component(component_id)}-{_safe_report_component(version)}"


def _safe_report_component(value: str) -> str:
    raw_parts = re.split(r"[/\\]+", value.strip())
    path_safe_value = "-".join(part for part in raw_parts if part not in {"", ".", ".."})
    normalized = _SAFE_REPORT_COMPONENT_PATTERN.sub("-", path_safe_value).strip(".-")
    return normalized or "unknown"


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


def _requested_inspection_bundle_path(args: Namespace, work_dir: Path) -> Path:
    explicit_path = getattr(args, "inspection_bundle", None)
    if explicit_path:
        return Path(explicit_path)
    return work_dir / ".verify-rc-inspection"


def _inspection_bundle_base_name(
    component_id: str | None,
    version: str | None,
    rc_tag: str | None,
) -> str:
    report_base_name = _report_base_name(component_id, version, rc_tag)
    return report_base_name.replace("verify-rc-report-", "verify-rc-inspection-", 1)


def _finalize_inspection_bundle_path(
    args: Namespace,
    result: VerifyRcPhase1Result,
    *,
    requested_path: Path,
) -> Path | None:
    if not requested_path.exists():
        return None
    explicit_path = getattr(args, "inspection_bundle", None)
    if explicit_path:
        return requested_path
    final_path = result.work_dir / _inspection_bundle_base_name(
        result.component_id,
        result.version,
        result.rc_tag,
    )
    if final_path == requested_path:
        return final_path
    if final_path.exists():
        raise ValueError(f"inspection bundle path already exists: {final_path}")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    requested_path.rename(final_path)
    return final_path


def _finalized_report_outputs(
    result: VerifyRcPhase1Result,
    *,
    report_json_path: Path,
    inspection_bundle_path: Path | None,
) -> tuple[VerifyRcReportV1, str]:
    if inspection_bundle_path is None:
        return result.report_payload, result.report_markdown
    relative_bundle_path = os.path.relpath(
        inspection_bundle_path,
        start=report_json_path.parent,
    )
    report_payload = result.report_payload.model_copy(
        update={
            "inspection_bundle": InspectionBundleSection(
                relative_path_from_report=relative_bundle_path,
                bundle_schema_version="1",
                manifest_relative_path=INSPECTION_BUNDLE_MANIFEST_FILENAME,
            )
        }
    )
    report_markdown = (
        f"{result.report_markdown}\n\n### Inspection Bundle\n\n"
        f"- Relative path from report: `{relative_bundle_path}`\n"
        f"- Bundle schema version: `1`\n"
        f"- Bundle manifest: `{INSPECTION_BUNDLE_MANIFEST_FILENAME}`\n"
    )
    return report_payload, report_markdown
