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

"""Tests for the shared pooled resource downloader."""

from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from urllib.error import HTTPError

from urllib3 import Timeout
from urllib3.exceptions import ReadTimeoutError

from buildish_release_tooling.shared._downloader import _ResourceDownloader
from buildish_release_tooling.shared.downloader import DownloadPolicy, DownloadSession
from buildish_release_tooling.shared.io import ByteLimitExceededError


class _FakeResponse:
    def __init__(self, payload: bytes, *, status: int = 200) -> None:
        self.status = status
        self.headers: dict[str, str] = {"content-type": "application/octet-stream"}
        self._payload = payload
        self._offset = 0
        self.released = False
        self.closed = False

    def read(self, size: int | None = None) -> bytes:
        if size is None:
            size = len(self._payload) - self._offset
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def release_conn(self) -> None:
        self.released = True

    def close(self) -> None:
        self.closed = True

    def isclosed(self) -> bool:
        return self._offset >= len(self._payload)


class _FakePoolManager:
    def __init__(self, *responses: _FakeResponse) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, str, dict[str, object]]] = []
        self.cleared = False

    def request(self, method: str, url: str, **kwargs: object) -> _FakeResponse:
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)

    def clear(self) -> None:
        self.cleared = True


class SharedDownloaderTest(unittest.TestCase):
    """Verify shared URI downloader behavior without network access."""

    def test_download_to_path_streams_http_response_with_hashes(self) -> None:
        pool = _FakePoolManager(_FakeResponse(b"payload\n"))
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]
        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "artifact.bin"

            downloaded = downloader.download_to_path(
                "https://downloads.example.invalid/artifact.bin",
                destination,
                max_bytes=100,
                algorithms=("sha256", "sha512"),
            )

            self.assertEqual(b"payload\n", destination.read_bytes())
            self.assertEqual(8, downloaded.size_bytes)
            self.assertEqual(
                hashlib.sha256(b"payload\n").hexdigest(), downloaded.hashes["sha256"]
            )
            self.assertEqual(
                hashlib.sha512(b"payload\n").hexdigest(), downloaded.hashes["sha512"]
            )
            self.assertFalse(pool.requests[0][2]["preload_content"])
            self.assertFalse(pool.requests[0][2]["redirect"])
            self.assertFalse(pool.requests[0][2]["retries"])
            self.assertTrue(pool.requests[0][2]["timeout"] is not None)

    def test_download_to_path_discards_unread_response_after_limit_failure(
        self,
    ) -> None:
        response = _FakeResponse(b"x" * (1024 * 1024 + 1))
        pool = _FakePoolManager(response)
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]
        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "artifact.bin"

            with self.assertRaises(ByteLimitExceededError):
                downloader.download_to_path(
                    "https://downloads.example.invalid/artifact.bin",
                    destination,
                    max_bytes=3,
                )

            self.assertTrue(response.closed)
            self.assertTrue(response.released)
            self.assertFalse(destination.exists())

    def test_hash_uri_streams_local_file_uri(self) -> None:
        pool = _FakePoolManager()
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "artifact.bin"
            source.write_bytes(b"payload\n")

            digest = downloader.hash_uri(source.as_uri())

        self.assertEqual(hashlib.sha512(b"payload\n").hexdigest(), digest)
        self.assertEqual([], pool.requests)

    def test_read_text_uses_bounded_http_response(self) -> None:
        pool = _FakePoolManager(_FakeResponse(b"hello\n"))
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]

        self.assertEqual(
            "hello\n",
            downloader.read_text(
                "https://downloads.example.invalid/hello.txt", max_bytes=10
            ),
        )

    def test_read_text_rejects_oversized_http_response(self) -> None:
        pool = _FakePoolManager(_FakeResponse(b"hello\n"))
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]

        with self.assertRaises(ByteLimitExceededError):
            downloader.read_text(
                "https://downloads.example.invalid/hello.txt", max_bytes=3
            )

    def test_read_bytes_enforces_absolute_deadline_during_streaming(self) -> None:
        response = _FakeResponse(b"payload\n")
        pool = _FakePoolManager(response)
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]

        with mock.patch(
            "buildish_release_tooling.shared._downloader.time.monotonic",
            side_effect=(0.0, 2.0),
        ):
            with self.assertRaisesRegex(TimeoutError, "total deadline"):
                downloader.read_bytes(
                    "https://downloads.example.invalid/slow",
                    max_bytes=100,
                    deadline_monotonic=1.0,
                )

    def test_request_timeouts_are_capped_to_remaining_deadline(self) -> None:
        pool = _FakePoolManager(_FakeResponse(b"payload\n"))
        downloader = _ResourceDownloader(
            pool_manager=pool,  # type: ignore[arg-type]
            timeout=Timeout(connect=10, read=30),
        )

        with mock.patch(
            "buildish_release_tooling.shared._downloader.time.monotonic",
            return_value=10.0,
        ):
            self.assertEqual(
                b"payload\n",
                downloader.read_bytes(
                    "https://downloads.example.invalid/payload",
                    max_bytes=100,
                    deadline_monotonic=12.0,
                ),
            )

        request_timeout = pool.requests[0][2]["timeout"]
        self.assertIsInstance(request_timeout, Timeout)
        if not isinstance(request_timeout, Timeout):
            self.fail("request timeout must be an urllib3 Timeout")
        self.assertEqual(2.0, request_timeout.connect_timeout)
        self.assertEqual(2.0, request_timeout.read_timeout)
        self.assertEqual(2.0, request_timeout.total)

    def test_absolute_deadline_does_not_lengthen_configured_total_timeout(
        self,
    ) -> None:
        pool = _FakePoolManager(_FakeResponse(b"payload\n"))
        downloader = _ResourceDownloader(
            pool_manager=pool,  # type: ignore[arg-type]
            timeout=Timeout(total=1, connect=10, read=10),
        )

        with mock.patch(
            "buildish_release_tooling.shared._downloader.time.monotonic",
            return_value=10.0,
        ):
            self.assertEqual(
                b"payload\n",
                downloader.read_bytes(
                    "https://downloads.example.invalid/payload",
                    max_bytes=100,
                    deadline_monotonic=30.0,
                ),
            )

        request_timeout = pool.requests[0][2]["timeout"]
        self.assertIsInstance(request_timeout, Timeout)
        if not isinstance(request_timeout, Timeout):
            self.fail("request timeout must be an urllib3 Timeout")
        self.assertEqual(1.0, request_timeout.total)

    def test_http_errors_raise_http_error_and_release_connection(self) -> None:
        response = _FakeResponse(b"missing", status=404)
        pool = _FakePoolManager(response)
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]

        with self.assertRaises(HTTPError):
            downloader.read_bytes(
                "https://downloads.example.invalid/missing", max_bytes=100
            )

        self.assertTrue(response.released)

    def test_file_uri_rejects_non_local_authority(self) -> None:
        pool = _FakePoolManager()
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "non-local authority"):
            downloader.read_bytes("file://example.invalid/etc/passwd", max_bytes=100)

    def test_download_session_rejects_disallowed_initial_scheme(self) -> None:
        pool = _FakePoolManager()
        session = DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"})),
            transport=_ResourceDownloader(pool_manager=pool),  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(ValueError, "URI scheme"):
            session.read_bytes(
                "http://downloads.example.invalid/payload", max_bytes=100
            )
        self.assertEqual([], pool.requests)

    def test_download_session_restricts_request_headers_to_accept(self) -> None:
        pool = _FakePoolManager(_FakeResponse(b"payload\n"))
        session = DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"})),
            transport=_ResourceDownloader(pool_manager=pool),  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(ValueError, "restricted to Accept"):
            session.read_bytes(
                "https://downloads.example.invalid/payload",
                max_bytes=100,
                headers={"Authorization": "Bearer secret"},
            )
        self.assertEqual([], pool.requests)

        self.assertEqual(
            b"payload\n",
            session.read_bytes(
                "https://downloads.example.invalid/payload",
                max_bytes=100,
                headers={"Accept": "application/json"},
            ),
        )

    def test_download_session_follows_redirects_with_policy(self) -> None:
        redirect = _FakeResponse(b"", status=302)
        redirect.headers["location"] = "/payload"
        payload = _FakeResponse(b"payload\n")
        pool = _FakePoolManager(redirect, payload)
        session = DownloadSession(
            policy=DownloadPolicy(
                allowed_schemes=frozenset({"https"}), max_redirects=2
            ),
            transport=_ResourceDownloader(pool_manager=pool),  # type: ignore[arg-type]
        )

        self.assertEqual(
            b"payload\n",
            session.read_bytes(
                "https://downloads.example.invalid/start", max_bytes=100
            ),
        )
        self.assertEqual(
            [
                "https://downloads.example.invalid/start",
                "https://downloads.example.invalid/payload",
            ],
            [url for _method, url, _kwargs in pool.requests],
        )
        self.assertTrue(redirect.released)
        self.assertTrue(payload.released)

    def test_body_bearing_redirect_is_discarded_before_following(self) -> None:
        redirect = _FakeResponse(b"ignored redirect payload", status=302)
        redirect.headers["location"] = "/payload"
        payload = _FakeResponse(b"payload\n")
        pool = _FakePoolManager(redirect, payload)
        session = DownloadSession(
            policy=DownloadPolicy(
                allowed_schemes=frozenset({"https"}),
                max_redirects=2,
            ),
            transport=_ResourceDownloader(pool_manager=pool),  # type: ignore[arg-type]
        )

        self.assertEqual(
            b"payload\n",
            session.read_bytes(
                "https://downloads.example.invalid/start",
                max_bytes=100,
            ),
        )
        self.assertTrue(redirect.closed)
        self.assertTrue(redirect.released)
        self.assertEqual(2, len(pool.requests))

    def test_real_pool_replaces_discarded_connection_without_losing_slot(self) -> None:
        request_paths: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                request_paths.append(self.path)
                if self.path == "/redirect":
                    body = b"ignored redirect payload"
                    self.send_response(302)
                    self.send_header("Location", "/payload")
                elif self.path == "/oversized":
                    body = b"oversized"
                    self.send_response(200)
                elif self.path == "/next":
                    body = b"next"
                    self.send_response(200)
                else:
                    body = b"payload"
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *args: object) -> None:
                del args

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base_url = f"http://127.0.0.1:{server.server_port}"
        with DownloadSession(
            policy=DownloadPolicy(
                allowed_schemes=frozenset({"http"}),
                max_redirects=2,
            ),
            transport=_ResourceDownloader.create(max_connections=1),
        ) as session:
            self.assertEqual(
                b"payload",
                session.read_bytes(f"{base_url}/redirect", max_bytes=100),
            )
            with self.assertRaises(ByteLimitExceededError):
                session.read_bytes(f"{base_url}/oversized", max_bytes=3)
            self.assertEqual(
                b"next",
                session.read_bytes(f"{base_url}/next", max_bytes=100),
            )

        self.assertEqual(
            ["/redirect", "/payload", "/oversized", "/next"],
            request_paths,
        )

    def test_real_request_header_wait_is_bounded_by_total_deadline(self) -> None:
        class SlowHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                time.sleep(0.3)
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except BrokenPipeError:
                    pass

            def log_message(self, _format: str, *args: object) -> None:
                del args

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/slow"
        started = time.monotonic()
        with DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"http"})),
            transport=_ResourceDownloader.create(
                max_connections=1,
                timeout=Timeout(connect=5, read=5),
            ),
        ) as session:
            with self.assertRaises(ReadTimeoutError):
                session.read_bytes(
                    url,
                    max_bytes=100,
                    deadline_monotonic=time.monotonic() + 0.05,
                )
        self.assertLess(time.monotonic() - started, 0.25)

    def test_real_error_body_read_is_bounded_by_total_deadline(self) -> None:
        class SlowErrorHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                self.send_response(500)
                self.send_header("Content-Length", "100")
                self.end_headers()
                try:
                    for _index in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.01)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, _format: str, *args: object) -> None:
                del args

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowErrorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/slow-error"
        started = time.monotonic()
        with DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"http"})),
            transport=_ResourceDownloader.create(
                max_connections=1,
                timeout=Timeout(connect=5, read=5),
            ),
        ) as session:
            with self.assertRaisesRegex(TimeoutError, "total deadline"):
                session.read_bytes(
                    url,
                    max_bytes=100,
                    deadline_monotonic=time.monotonic() + 0.05,
                )
        self.assertLess(time.monotonic() - started, 0.25)

    def test_download_session_rejects_https_to_http_redirects_by_default(self) -> None:
        redirect = _FakeResponse(b"", status=302)
        redirect.headers["location"] = "http://downloads.example.invalid/payload"
        pool = _FakePoolManager(redirect)
        session = DownloadSession(
            policy=DownloadPolicy(
                allowed_schemes=frozenset({"https", "http"}), max_redirects=2
            ),
            transport=_ResourceDownloader(pool_manager=pool),  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(ValueError, "must not redirect to HTTP"):
            session.read_bytes("https://downloads.example.invalid/start", max_bytes=100)

    def test_download_session_context_manager_closes_owned_transport(self) -> None:
        pool = _FakePoolManager()
        with DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"})),
            transport=_ResourceDownloader(pool_manager=pool),  # type: ignore[arg-type]
        ):
            pass

        self.assertTrue(pool.cleared)
