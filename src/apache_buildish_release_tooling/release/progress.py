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

"""Shared progress-reporting helpers for long-running release commands."""

from __future__ import annotations

import sys
from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import TextIO


class ProgressReporter:
    """Emit human-readable progress lines to stderr-like streams."""

    def __init__(
        self,
        *,
        enabled: bool,
        stream: TextIO,
        interval_seconds: float = 1.0,
        time_source: Callable[[], float] = monotonic,
    ) -> None:
        self.enabled = enabled
        self._stream = stream
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
        interval_seconds: float = 1.0,
        is_tty: bool | None = None,
        time_source: Callable[[], float] = monotonic,
    ) -> ProgressReporter:
        output_stream = sys.stderr if stream is None else stream
        enabled = _progress_enabled(mode, output_stream=output_stream, is_tty=is_tty)
        return cls(
            enabled=enabled,
            stream=output_stream,
            interval_seconds=interval_seconds,
            time_source=time_source,
        )

    def emit(self, message: str) -> None:
        """Write one progress line immediately."""

        if not self.enabled:
            return
        with self._lock:
            self._write(message)
            self._last_output_time = self._time_source()
            self._last_output_message = message

    def update(self, message: str) -> None:
        """Write one progress line when the rate limit allows and the message changed."""

        if not self.enabled:
            return
        with self._lock:
            if message == self._last_output_message:
                return
            now = self._time_source()
            if self._last_output_time is not None and now - self._last_output_time < self._interval_seconds:
                return
            self._write(message)
            self._last_output_time = now
            self._last_output_message = message

    def _write(self, message: str) -> None:
        self._stream.write(f"progress: {message}\n")
        self._stream.flush()


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


def _stream_isatty(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except OSError:
        return False
