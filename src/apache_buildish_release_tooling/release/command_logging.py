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

"""Sanitized command-line logging helpers for shell-outs."""

from __future__ import annotations

import os
import shlex
import sys
from collections.abc import Iterable, Sequence

_SECRET_ENV_NAMES = (
    "BUILDISH_GIT_ASKPASS_TOKEN",
    "BUILDISH_SVN_DEV_USERNAME",
    "BUILDISH_SVN_DEV_PASSWORD",
    "BUILDISH_GPG_PRIVATE_KEY",
    "BUILDISH_GPG_PASSPHRASE",
    "DOCKERHUB_USER",
    "DOCKERHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)
_REDACTED_OPTION_NAMES = {"--username", "--password", "--passphrase", "--token", "--oauth-token"}


def redacted_token() -> str:
    """Return the placeholder used for sanitized command arguments."""

    return "***"


def _secret_values(extra_values: Iterable[str] | None = None) -> list[str]:
    values = [value for name in _SECRET_ENV_NAMES if (value := os.environ.get(name))]
    if extra_values is not None:
        values.extend(value for value in extra_values if value)
    return values


def sanitize_argument(argument: str, extra_secret_values: Iterable[str] | None = None) -> str:
    """Replace secret material embedded in a single argument."""

    sanitized = argument
    for secret_value in _secret_values(extra_secret_values):
        sanitized = sanitized.replace(secret_value, redacted_token())
    return sanitized


def format_command(
    command: Sequence[str], extra_secret_values: Iterable[str] | None = None
) -> str:
    """Return a shell-escaped command line with credential values redacted."""

    sanitized_arguments: list[str] = []
    redact_next = False
    for argument in command:
        if redact_next:
            sanitized_arguments.append(redacted_token())
            redact_next = False
            continue
        if argument in _REDACTED_OPTION_NAMES:
            sanitized_arguments.append(argument)
            redact_next = True
            continue
        sanitized_arguments.append(sanitize_argument(argument, extra_secret_values))
    return shlex.join(sanitized_arguments)


def print_command(command: Sequence[str], extra_secret_values: Iterable[str] | None = None) -> None:
    """Emit a sanitized shell trace line to stderr."""

    sys.stderr.write(f"+ {format_command(command, extra_secret_values)}\n")
