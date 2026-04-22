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

"""Shared progress-reporting helpers for long-running release commands."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import TextIO

_ANSI_RESET = "\033[0m"


class ProgressReporter:
    """Emit human-readable progress lines to stderr-like streams."""

    def __init__(
        self,
        *,
        enabled: bool,
        color_enabled: bool,
        stream: TextIO,
        mirror_stream: TextIO | None = None,
        prefix: str = "progress: ",
        interval_seconds: float = 1.0,
        time_source: Callable[[], float] = monotonic,
    ) -> None:
        self.enabled = enabled
        self.color_enabled = color_enabled
        self._stream = stream
        self._mirror_stream = mirror_stream
        self._prefix = prefix
        self._interval_seconds = interval_seconds
        self._time_source = time_source
        self._last_output_time: float | None = None
        self._last_output_message: str | None = None
        self._lock = Lock()

    @classmethod
    def from_mode(
        cls,
        mode: str,
        *,
        stream: TextIO | None = None,
        mirror_stream: TextIO | None = None,
        color_mode: str = "auto",
        prefix: str = "progress: ",
        interval_seconds: float = 1.0,
        is_tty: bool | None = None,
        time_source: Callable[[], float] = monotonic,
    ) -> ProgressReporter:
        output_stream = sys.stderr if stream is None else stream
        enabled = _progress_enabled(mode, output_stream=output_stream, is_tty=is_tty)
        color_enabled = enabled and _color_enabled(
            color_mode,
            output_stream=output_stream,
            is_tty=is_tty,
        )
        return cls(
            enabled=enabled,
            color_enabled=color_enabled,
            stream=output_stream,
            mirror_stream=mirror_stream,
            prefix=prefix,
            interval_seconds=interval_seconds,
            time_source=time_source,
        )

    def emit(self, message: str) -> None:
        """Write one progress line immediately."""

        if not self.enabled and self._mirror_stream is None:
            return
        with self._lock:
            self._write(message, styled_message=message)
            self._last_output_time = self._time_source()
            self._last_output_message = message

    def emit_styled(self, message: str, *, sgr: str | None = None) -> None:
        """Write one progress line immediately, coloring stderr only when enabled."""

        if not self.enabled and self._mirror_stream is None:
            return
        with self._lock:
            self._write(
                message,
                styled_message=_styled_message(message, sgr=sgr) if self.color_enabled else message,
            )
            self._last_output_time = self._time_source()
            self._last_output_message = message

    def update(self, message: str) -> None:
        """Write one progress line when the rate limit allows and the message changed."""

        if not self.enabled and self._mirror_stream is None:
            return
        with self._lock:
            if message == self._last_output_message:
                return
            now = self._time_source()
            if self._last_output_time is not None and now - self._last_output_time < self._interval_seconds:
                return
            self._write(message, styled_message=message)
            self._last_output_time = now
            self._last_output_message = message

    def _write(self, message: str, *, styled_message: str) -> None:
        plain_rendered = f"{self._prefix}{message}\n"
        styled_rendered = f"{self._prefix}{styled_message}\n"
        if self.enabled:
            self._stream.write(styled_rendered)
            self._stream.flush()
        if self._mirror_stream is not None and self._mirror_stream is not self._stream:
            self._mirror_stream.write(plain_rendered)
            self._mirror_stream.flush()


def _progress_enabled(
    mode: str,
    *,
    output_stream: TextIO,
    is_tty: bool | None,
) -> bool:
    if mode == "on":
        return True
    if mode == "off":
        return False
    if mode != "auto":
        raise ValueError(f"unsupported progress mode: {mode}")
    if is_tty is not None:
        return is_tty
    return _stream_isatty(output_stream)


def _color_enabled(
    mode: str,
    *,
    output_stream: TextIO,
    is_tty: bool | None,
) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    if mode != "auto":
        raise ValueError(f"unsupported color mode: {mode}")
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("CLICOLOR_FORCE") == "1":
        return True
    if os.environ.get("CLICOLOR") == "0":
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if is_tty is not None:
        return is_tty
    return _stream_isatty(output_stream)


def _stream_isatty(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _styled_message(message: str, *, sgr: str | None) -> str:
    if not sgr:
        return message
    return f"\033[{sgr}m{message}{_ANSI_RESET}"
