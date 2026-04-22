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

"""Unit tests for shared progress-reporting helpers."""

from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import patch

from buildish_release_tooling.release.progress import ProgressReporter


class _FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current


class _FakeTtyStream(StringIO):
    def __init__(self, *, is_tty: bool) -> None:
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


class ProgressReporterUnitTest(unittest.TestCase):
    def test_from_mode_resolves_auto_on_and_off(self) -> None:
        tty_stream = _FakeTtyStream(is_tty=True)
        non_tty_stream = _FakeTtyStream(is_tty=False)

        self.assertTrue(ProgressReporter.from_mode("auto", stream=tty_stream).enabled)
        self.assertFalse(ProgressReporter.from_mode("auto", stream=non_tty_stream).enabled)
        self.assertTrue(ProgressReporter.from_mode("on", stream=non_tty_stream).enabled)
        self.assertFalse(ProgressReporter.from_mode("off", stream=tty_stream).enabled)

    def test_from_mode_resolves_auto_color_with_tty_and_common_env_vars(self) -> None:
        tty_stream = _FakeTtyStream(is_tty=True)
        non_tty_stream = _FakeTtyStream(is_tty=False)

        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(ProgressReporter.from_mode("auto", stream=tty_stream).color_enabled)
            self.assertFalse(ProgressReporter.from_mode("auto", stream=non_tty_stream).color_enabled)

        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=True):
            self.assertFalse(ProgressReporter.from_mode("auto", stream=tty_stream).color_enabled)

        with patch.dict("os.environ", {"CLICOLOR": "0"}, clear=True):
            self.assertFalse(ProgressReporter.from_mode("auto", stream=tty_stream).color_enabled)

        with patch.dict("os.environ", {"CLICOLOR_FORCE": "1"}, clear=True):
            self.assertTrue(ProgressReporter.from_mode("on", stream=non_tty_stream).color_enabled)

        with patch.dict("os.environ", {"TERM": "dumb"}, clear=True):
            self.assertFalse(ProgressReporter.from_mode("auto", stream=tty_stream).color_enabled)

    def test_update_rate_limits_and_skips_duplicate_messages(self) -> None:
        clock = _FakeClock()
        stream = StringIO()
        reporter = ProgressReporter(
            enabled=True,
            color_enabled=False,
            stream=stream,
            interval_seconds=1.0,
            time_source=clock,
        )

        reporter.emit("phase start")
        clock.current = 0.2
        reporter.update("count 1")
        clock.current = 0.5
        reporter.update("count 2")
        clock.current = 1.2
        reporter.update("count 3")
        clock.current = 1.3
        reporter.update("count 3")
        clock.current = 1.4
        reporter.emit("phase done")

        self.assertEqual(
            [
                "progress: phase start",
                "progress: count 3",
                "progress: phase done",
            ],
            stream.getvalue().splitlines(),
        )

    def test_custom_prefix_can_be_disabled(self) -> None:
        stream = StringIO()
        reporter = ProgressReporter(
            enabled=True,
            color_enabled=False,
            stream=stream,
            prefix="",
        )

        reporter.emit("Verify RC")
        reporter.emit("=========")

        self.assertEqual(
            [
                "Verify RC",
                "=========",
            ],
            stream.getvalue().splitlines(),
        )

    def test_mirror_stream_receives_output_when_stderr_progress_is_disabled(self) -> None:
        stream = StringIO()
        mirror_stream = StringIO()
        reporter = ProgressReporter(
            enabled=False,
            color_enabled=False,
            stream=stream,
            mirror_stream=mirror_stream,
            prefix="",
        )

        reporter.emit("Verify RC")

        self.assertEqual("", stream.getvalue())
        self.assertEqual("Verify RC\n", mirror_stream.getvalue())

    def test_colored_stderr_output_is_not_mirrored_into_plain_log(self) -> None:
        stream = _FakeTtyStream(is_tty=True)
        mirror_stream = StringIO()
        reporter = ProgressReporter(
            enabled=True,
            color_enabled=True,
            stream=stream,
            mirror_stream=mirror_stream,
            prefix="",
        )

        reporter.emit_styled("✓ Verified source artifact signature", sgr="32")

        self.assertEqual(
            "\x1b[32m✓ Verified source artifact signature\x1b[0m\n",
            stream.getvalue(),
        )
        self.assertEqual(
            "✓ Verified source artifact signature\n",
            mirror_stream.getvalue(),
        )
