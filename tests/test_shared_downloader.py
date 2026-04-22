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
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError

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

    def read(self, size: int | None = None) -> bytes:
        if size is None:
            size = len(self._payload) - self._offset
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def release_conn(self) -> None:
        self.released = True


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
            self.assertEqual(hashlib.sha256(b"payload\n").hexdigest(), downloaded.hashes["sha256"])
            self.assertEqual(hashlib.sha512(b"payload\n").hexdigest(), downloaded.hashes["sha512"])
            self.assertFalse(pool.requests[0][2]["preload_content"])
            self.assertFalse(pool.requests[0][2]["redirect"])
            self.assertTrue(pool.requests[0][2]["timeout"] is not None)

    def test_download_to_path_releases_response_after_limit_failure(self) -> None:
        response = _FakeResponse(b"payload\n")
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
            downloader.read_text("https://downloads.example.invalid/hello.txt", max_bytes=10),
        )

    def test_read_text_rejects_oversized_http_response(self) -> None:
        pool = _FakePoolManager(_FakeResponse(b"hello\n"))
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]

        with self.assertRaises(ByteLimitExceededError):
            downloader.read_text("https://downloads.example.invalid/hello.txt", max_bytes=3)

    def test_http_errors_raise_http_error_and_release_connection(self) -> None:
        response = _FakeResponse(b"missing", status=404)
        pool = _FakePoolManager(response)
        downloader = _ResourceDownloader(pool_manager=pool)  # type: ignore[arg-type]

        with self.assertRaises(HTTPError):
            downloader.read_bytes("https://downloads.example.invalid/missing", max_bytes=100)

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
            session.read_bytes("http://downloads.example.invalid/payload", max_bytes=100)
        self.assertEqual([], pool.requests)

    def test_download_session_follows_redirects_with_policy(self) -> None:
        redirect = _FakeResponse(b"", status=302)
        redirect.headers["location"] = "/payload"
        payload = _FakeResponse(b"payload\n")
        pool = _FakePoolManager(redirect, payload)
        session = DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"}), max_redirects=2),
            transport=_ResourceDownloader(pool_manager=pool),  # type: ignore[arg-type]
        )

        self.assertEqual(
            b"payload\n",
            session.read_bytes("https://downloads.example.invalid/start", max_bytes=100),
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

    def test_download_session_rejects_https_to_http_redirects_by_default(self) -> None:
        redirect = _FakeResponse(b"", status=302)
        redirect.headers["location"] = "http://downloads.example.invalid/payload"
        pool = _FakePoolManager(redirect)
        session = DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https", "http"}), max_redirects=2),
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
