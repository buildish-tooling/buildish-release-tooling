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
from typing import Any
from typing import Literal

from apache_buildish_release_tooling.release.models import (
    ComponentConfig,
    VerifyRcBuildConfig,
    VerifyRcBuildOverrideConfig,
    VerifyRcOverrideConfig,
    VerifyRcProfileConfig,
)
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
    injected_environment_keys: tuple[str, ...]
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


@dataclass(frozen=True)
class ResolvedRebuildProfile:
    """One canonical or locally overridden rebuild profile ready for execution."""

    profile_id: str
    canonical_profile: VerifyRcProfileConfig
    profile: VerifyRcProfileConfig
    recipe_source: Literal["canonical-profile", "local-override"]
    override_fields: tuple[str, ...]
    build_override: VerifyRcBuildOverrideConfig | None = None


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


def resolve_effective_rebuild_profile(
    component_config: ComponentConfig,
    profile_id: str,
    *,
    expected_kinds: Collection[str],
    profile_overrides: VerifyRcOverrideConfig | None = None,
) -> ResolvedRebuildProfile:
    """Resolve one canonical profile and merge any explicit local override for this run."""

    profile = resolve_rebuild_profile(
        component_config,
        profile_id,
        expected_kinds=expected_kinds,
    )
    if profile_overrides is None:
        return ResolvedRebuildProfile(
            profile_id=profile_id,
            canonical_profile=profile,
            profile=profile,
            recipe_source="canonical-profile",
            override_fields=(),
        )
    override = profile_overrides.profile_overrides.get(profile_id)
    if override is None:
        return ResolvedRebuildProfile(
            profile_id=profile_id,
            canonical_profile=profile,
            profile=profile,
            recipe_source="canonical-profile",
            override_fields=(),
        )
    merged_profile, override_fields = _merged_profile_override(profile, override.build)
    return ResolvedRebuildProfile(
        profile_id=profile_id,
        canonical_profile=profile,
        profile=merged_profile,
        recipe_source="local-override",
        override_fields=override_fields,
        build_override=override.build,
    )


def validate_rebuild_profile_overrides(
    component_config: ComponentConfig,
    profile_overrides: VerifyRcOverrideConfig,
) -> None:
    """Validate that all local override profile_ids exist in the canonical component config."""

    verify_rc = component_config.verify_rc
    if verify_rc is None:
        raise ValueError("component config does not define any verify_rc reproducibility profiles")
    known_profile_ids = set(verify_rc.profiles)
    unknown_profile_ids = sorted(set(profile_overrides.profile_overrides) - known_profile_ids)
    if unknown_profile_ids:
        joined_profile_ids = ", ".join(unknown_profile_ids)
        raise ValueError(
            f"reproducibility override file references unknown verify_rc profile_id values: {joined_profile_ids}"
        )


def _merged_profile_override(
    profile: VerifyRcProfileConfig,
    build_override: VerifyRcBuildOverrideConfig,
) -> tuple[VerifyRcProfileConfig, tuple[str, ...]]:
    command = profile.build.command
    working_dir = profile.build.working_dir
    env = dict(profile.build.env)
    output_globs = profile.build.output_globs
    override_fields: list[str] = []
    override_command = build_override.command
    if override_command is not None:
        command = list(override_command)
        override_fields.append("build.command")
    override_working_dir = build_override.working_dir
    if override_working_dir is not None:
        working_dir = override_working_dir
        override_fields.append("build.working_dir")
    override_env = build_override.env
    if override_env:
        env.update(override_env)
        override_fields.extend(f"build.env.{key}" for key in sorted(override_env))
    override_output_globs = build_override.output_globs
    if override_output_globs is not None:
        output_globs = list(override_output_globs)
        override_fields.append("build.output_globs")
    merged_build = VerifyRcBuildConfig(
        command=command,
        working_dir=working_dir,
        env=env,
        output_globs=output_globs,
    )
    return (
        profile.model_copy(update={"build": merged_build}, deep=True),
        tuple(override_fields),
    )


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
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Build a compatible but scrubbed subprocess environment for host-direct rebuilds."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in _SCRUBBED_ENV_NAMES
        and not any(key.startswith(prefix) for prefix in _SCRUBBED_ENV_PREFIXES)
    }
    injected_keys = [
        "TMPDIR",
        "BUILDISH_PROJECT_ROOT",
        "BUILDISH_WORK_DIR",
    ]
    tmp_dir = work_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    environment["TMPDIR"] = str(tmp_dir)
    environment["BUILDISH_PROJECT_ROOT"] = str(project_root)
    environment["BUILDISH_WORK_DIR"] = str(work_dir)
    if source_date_epoch is not None:
        epoch_text = str(source_date_epoch)
        environment["SOURCE_DATE_EPOCH"] = epoch_text
        environment["BUILDISH_SOURCE_DATE_EPOCH"] = epoch_text
        injected_keys.extend(["SOURCE_DATE_EPOCH", "BUILDISH_SOURCE_DATE_EPOCH"])
    if extra_env is not None:
        environment.update(extra_env)
        injected_keys.extend(extra_env)
    return environment, tuple(sorted(set(injected_keys)))


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
    environment, injected_environment_keys = build_host_direct_environment(
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
        injected_environment_keys=injected_environment_keys,
        output_paths=collect_profile_output_paths(project_root, profile.build.output_globs),
        environment=environment,
    )


def canonical_recipe_payload(
    resolved_profile: ResolvedRebuildProfile | None,
) -> dict[str, Any] | None:
    """Return one structured canonical recipe payload for reporting."""

    if resolved_profile is None:
        return None
    canonical_build = resolved_profile.canonical_profile.build
    return {
        "build": {
            "command": list(canonical_build.command),
            "working_directory": canonical_build.working_dir or ".",
            "output_globs": list(canonical_build.output_globs),
            # Environment variable names only. Values are intentionally omitted
            # from reports so reproducibility output cannot leak secrets or
            # machine-local credentials.
            "env_keys": sorted(canonical_build.env),
        }
    }


def effective_execution_payload(
    *,
    build_result: HostDirectBuildResult | None,
    project_root: Path | None,
    output_paths: list[str] | None = None,
) -> dict[str, Any] | None:
    """Return one structured effective-execution payload for reporting."""

    if build_result is None or project_root is None:
        return None
    working_directory = str(build_result.cwd.relative_to(project_root))
    if working_directory == "":
        working_directory = "."
    effective_output_paths = output_paths
    if effective_output_paths is None:
        effective_output_paths = [
            str(path.relative_to(project_root)) for path in build_result.output_paths
        ]
    return {
        "backend": "host-direct",
        "build": {
            "command": list(build_result.command),
            "working_directory": working_directory,
            "output_paths": effective_output_paths,
            # Environment variable names only. Values are intentionally omitted
            # from reports so reproducibility output cannot leak secrets or
            # machine-local credentials.
            "injected_environment_keys": list(build_result.injected_environment_keys),
        },
    }


def override_payload(
    resolved_profile: ResolvedRebuildProfile | None,
) -> dict[str, Any]:
    """Return one sparse structured override payload for reporting."""

    if resolved_profile is None or resolved_profile.build_override is None:
        return {"applied": False}
    build_override = resolved_profile.build_override
    build_payload: dict[str, Any] = {}
    if build_override.command is not None:
        build_payload["command"] = list(build_override.command)
    if build_override.working_dir is not None:
        build_payload["working_directory"] = build_override.working_dir
    if build_override.output_globs is not None:
        build_payload["output_globs"] = list(build_override.output_globs)
    if build_override.env:
        # Environment variable names only. Values are intentionally omitted from
        # reports so reproducibility output cannot leak secrets or machine-local
        # credentials.
        build_payload["env_keys"] = sorted(build_override.env)
    return {
        "applied": True,
        "build": build_payload or None,
    }


def prompt_for_candidate_code_execution() -> bool:
    """Prompt on the controlling terminal before executing candidate build code."""

    sys.stderr.write(
        "Run build-based reproducibility checks? This executes candidate build code from the verified source tree. [y/N]: "
    )
    sys.stderr.flush()
    response = sys.stdin.readline().strip().lower()
    return response in {"y", "yes"}
