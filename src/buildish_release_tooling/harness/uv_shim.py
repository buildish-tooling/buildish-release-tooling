# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared `uv` shim rendering for harness backends."""

from __future__ import annotations

import shlex
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class UvShimConfig:
    """Configuration for one generated `uv` shim script."""

    shim_python_executable: str
    passthrough_python_install: bool = False
    real_cli_commands: tuple[str, ...] = ()
    real_cli_module: str = "buildish_release_tooling.release"
    real_cli_python_executable: str = "python3"
    shim_entrypoint_module: str = "buildish_release_tooling.harness.shim_entrypoint"


def render_uv_shim_script(config: UvShimConfig) -> str:
    """Return a generated `uv` shim script for one harness workspace."""

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
    ]
    if _requires_real_uv_resolution(config):
        lines.extend(
            [
                'original_args=("$@")',
                *_resolve_real_uv_lines(),
            ]
        )
    lines.extend(_python_install_lines(config))
    lines.extend(
        [
            'if [[ "${1:-}" != "run" ]]; then',
            '  printf "buildish-release-harness: unsupported uv invocation: %s\\n" "$*" >&2',
            "  exit 2",
            "fi",
            "shift",
            'while [[ $# -gt 0 ]]; do',
            '  case "$1" in',
            '    --project)',
            "      shift 2",
            "      ;;",
            '    --frozen)',
            "      shift",
            "      ;;",
            '    buildish-release-tooling)',
            "      shift",
            '      command_name="${1:-}"',
            '      if [[ "$command_name" == "--test-target-mode" ]]; then',
            '        command_name="${2:-}"',
            "      fi",
            '      if [[ -z "$command_name" ]]; then',
            '        printf "buildish-release-harness: missing buildish-release-tooling command\\n" >&2',
            "        exit 2",
            "      fi",
            *_real_cli_passthrough_lines(config),
            '      filtered_args=()',
            '      while [[ $# -gt 0 ]]; do',
            '        case "$1" in',
            '          --test-target-mode)',
            "            shift",
            "            ;;",
            '          --component-config)',
            "            shift 2",
            "            ;;",
            "          *)",
            '            filtered_args+=("$1")',
            "            shift",
            "            ;;",
            "        esac",
            "      done",
            (
                f'      exec {shlex.quote(config.shim_python_executable)} -m '
                f'{config.shim_entrypoint_module} buildish-release-tooling "${{filtered_args[@]}}"'
            ),
            "      ;;",
            "    *)",
            '      printf "buildish-release-harness: unexpected uv arguments: %s\\n" "$*" >&2',
            "      exit 2",
            "      ;;",
            "  esac",
            "done",
            'printf "buildish-release-harness: uv did not receive a command\\n" >&2',
            "exit 2",
        ]
    )
    return "\n".join(lines) + "\n"


def _requires_real_uv_resolution(config: UvShimConfig) -> bool:
    """Return whether the shim may need to find and exec the real `uv` binary."""

    return config.passthrough_python_install or bool(config.real_cli_commands)


def _resolve_real_uv_lines() -> list[str]:
    """Return the shell function that locates the non-shim `uv` binary."""

    return [
        'resolve_real_uv() {',
        '  local shim_dir resolved_path joined_path',
        '  local -a path_parts=()',
        '  local -a search_parts=()',
        '  shim_dir="$(cd "$(dirname "$0")" && pwd)"',
        '  IFS=: read -r -a path_parts <<<"${PATH:-}"',
        '  for part in "${path_parts[@]}"; do',
        '    if [[ -n "$part" && "$part" != "$shim_dir" ]]; then',
        '      search_parts+=("$part")',
        "    fi",
        "  done",
        '  joined_path="$(IFS=:; printf "%s" "${search_parts[*]}")"',
        '  resolved_path="$(PATH="$joined_path" command -v uv || true)"',
        '  if [[ -n "$resolved_path" ]]; then',
        '    printf "%s\\n" "$resolved_path"',
        "  fi",
        "}",
    ]


def _python_install_lines(config: UvShimConfig) -> list[str]:
    """Return the `uv python install` handling block."""

    if config.passthrough_python_install:
        return [
            'if [[ "${1:-}" == "python" && "${2:-}" == "install" ]]; then',
            '  if resolved_uv="$(resolve_real_uv)"; then',
            '    exec "$resolved_uv" "${original_args[@]}"',
            "  fi",
            "  exit 0",
            "fi",
        ]
    return [
        'if [[ "${1:-}" == "python" && "${2:-}" == "install" ]]; then',
        "  exit 0",
        "fi",
    ]


def _real_cli_passthrough_lines(config: UvShimConfig) -> list[str]:
    """Return the case block that lets selected commands use the real CLI."""

    if not config.real_cli_commands:
        return []
    real_cli_case = "|".join(config.real_cli_commands)
    return [
        '      case "$command_name" in',
        f"        {real_cli_case})",
        '          if resolved_uv="$(resolve_real_uv)"; then',
        '            exec "$resolved_uv" "${original_args[@]}"',
        "          fi",
        f'          exec {shlex.quote(config.real_cli_python_executable)} -m {config.real_cli_module} "$@"',
        "          ;;",
        "      esac",
    ]


def uv_shim_config(
    *,
    shim_python_executable: str,
    real_cli_commands: Iterable[str] = (),
    passthrough_python_install: bool = False,
) -> UvShimConfig:
    """Build a normalized `UvShimConfig` from convenient call-site values."""

    return UvShimConfig(
        shim_python_executable=shim_python_executable,
        real_cli_commands=tuple(real_cli_commands),
        passthrough_python_install=passthrough_python_install,
    )
