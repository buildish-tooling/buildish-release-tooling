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

import tempfile
from argparse import Namespace
from pathlib import Path

from apache_buildish_release_tooling.release.config import load_component_config, validate_release_target_base_urls
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.summary import SummaryWriter
from apache_buildish_release_tooling.release.verification import VerifyRcPhase1Result, verify_rc_phase1

from apache_buildish_release_tooling.release.commands._shared import _append_github_outputs


def run_verify_rc(args: Namespace) -> Path:
    """Run the Phase 1a read-only verifier against one signed RC vote manifest."""

    component_config = _optional_component_config(args)
    work_dir = _work_dir(args)
    result = verify_rc_phase1(
        manifest_url=args.rc_vote_manifest_url,
        keys_url=args.keys_url,
        component_config=component_config,
        allow_non_production_release_targets=args.allow_non_production_release_targets,
        work_dir=work_dir,
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
    _append_github_outputs(
        {
            "report_json_path": report_json_path,
            "report_md_path": report_md_path,
            "rc_tag": result.rc_tag,
            "source_commit_sha": result.source_commit_sha,
        }
    )
    return report_json_path


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


def _report_base_name(component_id: str, version: str, rc_tag: str) -> str:
    return (
        f"verify-rc-report-{component_id}-{version}-{rc_tag.removeprefix('v').replace('/', '-')}"
    )


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
