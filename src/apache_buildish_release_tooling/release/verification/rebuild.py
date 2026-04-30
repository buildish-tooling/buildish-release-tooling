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

"""Host-direct rebuild helpers used by later reproducibility verification steps."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcProfileConfig
from apache_buildish_release_tooling.release.process import run_logged_command

_SCRUBBED_ENV_NAMES = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "BUILDISH_GIT_ASKPASS_TOKEN",
    "BUILDISH_GPG_PASSPHRASE",
    "BUILDISH_GPG_PRIVATE_KEY",
    "BUILDISH_SVN_DEV_PASSWORD",
    "BUILDISH_SVN_DEV_USERNAME",
    "CI",
    "CLOUDSDK_AUTH_ACCESS_TOKEN",
    "GITHUB_ACTIONS",
    "GITHUB_OUTPUT",
    "GITHUB_STEP_SUMMARY",
    "GIT_ASKPASS",
    "GNUPGHOME",
    "GPG_AGENT_INFO",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "KUBECONFIG",
    "NODE_AUTH_TOKEN",
    "NPM_TOKEN",
    "SSH_AGENT_PID",
    "SSH_AUTH_SOCK",
    "TWINE_PASSWORD",
    "TWINE_USERNAME",
}
_SCRUBBED_ENV_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GITHUB_",
    "GH_",
    "GOOGLE_",
)


@dataclass(frozen=True)
class HostDirectBuildResult:
    """Observed output from one host-direct reproducibility recipe execution."""

    profile_id: str
    profile_kind: str
    command: tuple[str, ...]
    cwd: Path
    output_paths: tuple[Path, ...]
    environment: dict[str, str]


@dataclass(frozen=True)
class ReproducibilityModeDecision:
    """Resolved verify-rc policy for build-based reproducibility checks."""

    requested_mode: Literal["auto", "integrity-only", "full"]
    effective_mode: Literal["integrity-only", "full"]
    prompt_used: bool
    prompt_confirmed: bool | None
    build_checks_allowed: bool
    build_checks_skipped_reason: str | None


def resolve_rebuild_profile(
    component_config: ComponentConfig,
    profile_id: str,
    *,
    expected_kinds: Collection[str],
) -> VerifyRcProfileConfig:
    """Resolve one configured reproducibility profile and validate its declared kind."""

    verify_rc = component_config.verify_rc
    if verify_rc is None:
        raise ValueError("component config does not define any verify_rc reproducibility profiles")
    try:
        profile = verify_rc.profiles[profile_id]
    except KeyError as exc:
        raise ValueError(
            f"component config does not define verify_rc profile_id {profile_id!r}"
        ) from exc
    if profile.kind not in expected_kinds:
        expected = ", ".join(sorted(expected_kinds))
        raise ValueError(
            f"verify_rc profile {profile_id!r} declares incompatible kind {profile.kind!r}; "
            f"expected one of: {expected}"
        )
    return profile


def decide_reproducibility_mode(
    *,
    requested_mode: Literal["auto", "integrity-only", "full"],
    has_build_candidates: bool,
    is_interactive: bool,
    confirm_callback: Callable[[], bool] | None = None,
) -> ReproducibilityModeDecision:
    """Resolve whether build-based reproducibility checks may run for this invocation."""

    if requested_mode == "full":
        return ReproducibilityModeDecision(
            requested_mode=requested_mode,
            effective_mode="full",
            prompt_used=False,
            prompt_confirmed=None,
            build_checks_allowed=has_build_candidates,
            build_checks_skipped_reason=(
                None if has_build_candidates else "no build-based reproducibility profiles were selected"
            ),
        )
    if requested_mode == "integrity-only":
        return ReproducibilityModeDecision(
            requested_mode=requested_mode,
            effective_mode="integrity-only",
            prompt_used=False,
            prompt_confirmed=None,
            build_checks_allowed=False,
            build_checks_skipped_reason="build-based reproducibility checks were disabled by --mode integrity-only",
        )
    if not has_build_candidates:
        return ReproducibilityModeDecision(
            requested_mode=requested_mode,
            effective_mode="integrity-only",
            prompt_used=False,
            prompt_confirmed=None,
            build_checks_allowed=False,
            build_checks_skipped_reason="no build-based reproducibility profiles were selected",
        )
    if not is_interactive:
        return ReproducibilityModeDecision(
            requested_mode=requested_mode,
            effective_mode="integrity-only",
            prompt_used=False,
            prompt_confirmed=None,
            build_checks_allowed=False,
            build_checks_skipped_reason="auto mode stayed integrity-only because stdin/stdout are not interactive",
        )
    if confirm_callback is None:
        return ReproducibilityModeDecision(
            requested_mode=requested_mode,
            effective_mode="integrity-only",
            prompt_used=False,
            prompt_confirmed=None,
            build_checks_allowed=False,
            build_checks_skipped_reason="interactive confirmation callback was not provided",
        )
    confirmed = confirm_callback()
    return ReproducibilityModeDecision(
        requested_mode=requested_mode,
        effective_mode="full" if confirmed else "integrity-only",
        prompt_used=True,
        prompt_confirmed=confirmed,
        build_checks_allowed=confirmed,
        build_checks_skipped_reason=(
            None if confirmed else "interactive confirmation declined build-based reproducibility checks"
        ),
    )


def build_host_direct_environment(
    *,
    project_root: Path,
    work_dir: Path,
    source_date_epoch: int | None,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a compatible but scrubbed subprocess environment for host-direct rebuilds."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in _SCRUBBED_ENV_NAMES
        and not any(key.startswith(prefix) for prefix in _SCRUBBED_ENV_PREFIXES)
    }
    tmp_dir = work_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    environment["TMPDIR"] = str(tmp_dir)
    environment["BUILDISH_PROJECT_ROOT"] = str(project_root)
    environment["BUILDISH_WORK_DIR"] = str(work_dir)
    if source_date_epoch is not None:
        epoch_text = str(source_date_epoch)
        environment["SOURCE_DATE_EPOCH"] = epoch_text
        environment["BUILDISH_SOURCE_DATE_EPOCH"] = epoch_text
    if extra_env is not None:
        environment.update(extra_env)
    return environment


def ensure_detached_source_checkout(project_root: Path, commit_sha: str) -> None:
    """Checkout the verified source tree at one detached commit for local rebuild steps."""

    run_logged_command(
        ["git", "-C", str(project_root), "checkout", "--quiet", "--detach", commit_sha],
        log_command=False,
    )


def collect_profile_output_paths(project_root: Path, output_globs: Collection[str]) -> tuple[Path, ...]:
    """Resolve one profile's configured output globs relative to the verified project root."""

    matches: set[Path] = set()
    for pattern in output_globs:
        for path in project_root.glob(pattern):
            if path.is_file():
                matches.add(path.resolve())
    return tuple(sorted(matches))


def run_host_direct_profile(
    *,
    profile_id: str,
    profile: VerifyRcProfileConfig,
    project_root: Path,
    work_dir: Path,
    source_date_epoch: int | None,
) -> HostDirectBuildResult:
    """Execute one configured reproducibility profile directly on the host."""

    cwd = project_root if profile.build.working_dir is None else project_root / profile.build.working_dir
    environment = build_host_direct_environment(
        project_root=project_root,
        work_dir=work_dir,
        source_date_epoch=source_date_epoch,
        extra_env=profile.build.env,
    )
    run_logged_command(
        profile.build.command,
        cwd=cwd,
        env=environment,
        inherit_parent_env=False,
    )
    return HostDirectBuildResult(
        profile_id=profile_id,
        profile_kind=profile.kind,
        command=tuple(profile.build.command),
        cwd=cwd,
        output_paths=collect_profile_output_paths(project_root, profile.build.output_globs),
        environment=environment,
    )


def prompt_for_candidate_code_execution() -> bool:
    """Prompt on the controlling terminal before executing candidate build code."""

    sys.stderr.write(
        "Run build-based reproducibility checks? This executes candidate build code from the verified source tree. [y/N]: "
    )
    sys.stderr.flush()
    response = sys.stdin.readline().strip().lower()
    return response in {"y", "yes"}
