# Copyright 2026 The Buildish Authors
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
import codecs
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Iterable, Iterator, Sequence
from threading import local
from typing import BinaryIO, TextIO

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
_STDERR_CONTROL_ENV_NAME = "BUILDISH_COMMAND_LOG_STDERR"
DEFAULT_LOG_OUTPUT_FILE_LIMIT_BYTES = 4 * 1024 * 1024
_LOG_OUTPUT_CHUNK_BYTES = 64 * 1024
_LOG_STATE = local()


@dataclass(frozen=True)
class _ActiveCommandLog:
    stream: TextIO
    echo_to_stderr: bool


def redacted_token() -> str:
    """Return the placeholder used for sanitized command arguments."""

    return "***"


def _stderr_enabled_by_default() -> bool:
    """Return whether command traces should be echoed to stderr outside one active log sink."""

    raw_value = os.environ.get(_STDERR_CONTROL_ENV_NAME)
    if raw_value is None:
        return True
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def _secret_values(extra_values: Iterable[str] | None = None) -> list[str]:
    values = [value for name in _SECRET_ENV_NAMES if (value := os.environ.get(name))]
    if extra_values is not None:
        values.extend(value for value in extra_values if value)
    return values


def sanitize_text(text: str, extra_secret_values: Iterable[str] | None = None) -> str:
    """Replace secret material embedded anywhere in one free-form text block."""

    sanitized = text
    for secret_value in _secret_values(extra_secret_values):
        sanitized = sanitized.replace(secret_value, redacted_token())
    return sanitized


def sanitize_argument(argument: str, extra_secret_values: Iterable[str] | None = None) -> str:
    """Replace secret material embedded in a single argument."""

    return sanitize_text(argument, extra_secret_values)


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


@contextmanager
def command_log_sink(stream: TextIO, *, echo_to_stderr: bool) -> Iterator[None]:
    """Capture low-level command traces in one side log, optionally teeing them to stderr."""

    previous = getattr(_LOG_STATE, "active_log", None)
    _LOG_STATE.active_log = _ActiveCommandLog(
        stream=stream,
        echo_to_stderr=echo_to_stderr,
    )
    try:
        yield
    finally:
        _LOG_STATE.active_log = previous


def print_command(
    command: Sequence[str],
    extra_secret_values: Iterable[str] | None = None,
    *,
    stderr_enabled: bool = True,
) -> None:
    """Emit a sanitized shell trace line."""

    _write_log_line(
        f"+ {format_command(command, extra_secret_values)}",
        extra_secret_values=extra_secret_values,
        stderr_enabled=stderr_enabled,
    )


def log_command_output_file(
    stream_name: str,
    file: BinaryIO,
    *,
    max_bytes: int = DEFAULT_LOG_OUTPUT_FILE_LIMIT_BYTES,
    extra_secret_values: Iterable[str] | None = None,
) -> bool:
    """Emit sanitized subprocess output from a file without loading it all."""

    file.seek(0)
    remaining = max_bytes
    pending = ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while remaining > 0:
        chunk = file.read(min(_LOG_OUTPUT_CHUNK_BYTES, remaining))
        if not chunk:
            break
        remaining -= len(chunk)
        text = decoder.decode(chunk, final=False)
        pending = _write_complete_output_lines(
            stream_name,
            pending + text,
            extra_secret_values=extra_secret_values,
        )
    pending += decoder.decode(b"", final=True)
    if pending:
        _write_log_line(
            f"{stream_name} | {sanitize_text(pending.rstrip(chr(10)).rstrip(chr(13)), extra_secret_values)}",
            extra_secret_values=extra_secret_values,
            stderr_enabled=False,
        )
    truncated = bool(file.read(1)) if remaining == 0 else False
    if truncated:
        _write_log_line(
            f"{stream_name} | ... output truncated after {max_bytes} bytes",
            extra_secret_values=extra_secret_values,
            stderr_enabled=False,
        )
    return truncated


def _write_complete_output_lines(
    stream_name: str,
    text: str,
    *,
    extra_secret_values: Iterable[str] | None,
) -> str:
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        pending = lines.pop()
    else:
        pending = ""
    for line in lines:
        _write_log_line(
            f"{stream_name} | {sanitize_text(line.rstrip(chr(10)).rstrip(chr(13)), extra_secret_values)}",
            extra_secret_values=extra_secret_values,
            stderr_enabled=False,
        )
    return pending


def _write_log_line(
    message: str,
    *,
    extra_secret_values: Iterable[str] | None,
    stderr_enabled: bool,
) -> None:
    active_log = getattr(_LOG_STATE, "active_log", None)
    rendered = f"{sanitize_text(message, extra_secret_values)}\n"
    if active_log is not None:
        active_log.stream.write(rendered)
        active_log.stream.flush()
    should_echo_to_stderr = (
        active_log.echo_to_stderr
        if active_log is not None
        else stderr_enabled and _stderr_enabled_by_default()
    )
    if should_echo_to_stderr:
        sys.stderr.write(rendered)
