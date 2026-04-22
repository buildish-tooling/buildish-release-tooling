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

"""Focused tests for artifact-registration helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from typing import Any, cast
from typing import ClassVar

from buildish_release_tooling.release.artifact_registration.kinds.generic_file import (
    _resolved_filename as _generic_file_resolved_filename,
)
from buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RepositoryFile,
    _inventory_entry_sha512,
    _normalized_base_url,
    _parse_nexus_index,
    _repository_files,
)
from buildish_release_tooling.release.artifact_registration.kinds.npm_package import (
    _resolved_filename as _npm_package_resolved_filename,
)
from buildish_release_tooling.release.artifact_registration.kinds.python_distribution import (
    _resolved_filename as _python_distribution_resolved_filename,
)
from buildish_release_tooling.shared._downloader import _ResourceDownloader
from buildish_release_tooling.shared.downloader import DownloadPolicy, DownloadSession


class _FakeHTTPResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        status: int = 200,
        reason: str = "OK",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self.reason = reason
        self.data = payload
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
    instances: ClassVar[list[_FakePoolManager]] = []
    queued_responses: ClassVar[list[_FakeHTTPResponse]] = []

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object]]] = []
        self.issued_responses: list[_FakeHTTPResponse] = []
        self.cleared = False
        self.__class__.instances.append(self)

    @classmethod
    def reset(cls, *responses: _FakeHTTPResponse) -> None:
        cls.instances = []
        cls.queued_responses = list(responses)

    def request(self, method: str, url: str, **kwargs: object) -> _FakeHTTPResponse:
        self.requests.append((method, url, kwargs))
        response = self.__class__.queued_responses.pop(0)
        self.issued_responses.append(response)
        return response

    def clear(self) -> None:
        self.cleared = True


class _NoopProgress:
    def emit(self, _message: str) -> None:
        pass

    def update(self, _message: str) -> None:
        pass


class MavenRepositoryRegistrationUnitTest(unittest.TestCase):
    """Verify Nexus-style listing parsing used by the maven-repository kind."""

    def test_normalized_base_url_defaults_to_canonical_nexus_staging_location(self) -> None:
        self.assertEqual(
            "https://repository.apache.org/content/repositories/orgapachebeam-1427/",
            _normalized_base_url(None, staging_repository_id="orgapachebeam-1427"),
        )

    def test_parse_nexus_index_recognizes_directories_and_files(self) -> None:
        base_url = "https://repository.apache.org/content/repositories/orgapachebeam-1427/"
        html_text = "\n".join(
            [
                "<html>",
                "  <body>",
                "    <table cellspacing=\"10\">",
                "      <tr><th>Name</th><th>Last Modified</th><th>Size</th><th>Description</th></tr>",
                "      <tr><td><a href=\"../\">Parent Directory</a></td></tr>",
                "      <tr>",
                "        <td><a href=\"https://repository.apache.org/content/repositories/orgapachebeam-1427/org/\">org/</a></td>",
                "        <td>Thu Apr 16 14:43:40 UTC 2026</td>",
                "        <td align=\"right\"></td>",
                "        <td></td>",
                "      </tr>",
                "      <tr>",
                "        <td><a href=\"https://repository.apache.org/content/repositories/orgapachebeam-1427/archetype-catalog.xml\">archetype-catalog.xml</a></td>",
                "        <td>Mon Apr 27 13:17:21 UTC 2026</td>",
                "        <td align=\"right\">25</td>",
                "        <td></td>",
                "      </tr>",
                "    </table>",
                "  </body>",
                "</html>",
            ]
        )

        entries = _parse_nexus_index(base_url, base_url, html_text)

        self.assertEqual(2, len(entries))
        self.assertEqual(
            "https://repository.apache.org/content/repositories/orgapachebeam-1427/org/",
            entries[0].href,
        )
        self.assertEqual("org/", entries[0].name)
        self.assertTrue(entries[0].is_directory)
        self.assertIsNone(entries[0].size_bytes)
        self.assertEqual(
            "https://repository.apache.org/content/repositories/orgapachebeam-1427/archetype-catalog.xml",
            entries[1].href,
        )
        self.assertEqual("archetype-catalog.xml", entries[1].name)
        self.assertFalse(entries[1].is_directory)
        self.assertEqual(25, entries[1].size_bytes)

    def test_download_session_reuses_shared_pool_manager(self) -> None:
        _FakePoolManager.reset(
            _FakeHTTPResponse(b"alpha"),
            _FakeHTTPResponse(b"beta"),
        )
        pool_manager = _FakePoolManager()
        downloader = DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"})),
            transport=_ResourceDownloader(pool_manager=cast(Any, pool_manager)),
        )

        first = downloader.read_bytes(
            "https://repository.apache.org/content/repositories/orgapachebeam-1427/one",
            max_bytes=25 * 1024 * 1024,
        )
        second = downloader.read_bytes(
            "https://repository.apache.org/content/repositories/orgapachebeam-1427/two",
            max_bytes=25 * 1024 * 1024,
        )
        downloader.close()

        self.assertEqual(b"alpha", first)
        self.assertEqual(b"beta", second)
        self.assertEqual(1, len(_FakePoolManager.instances))
        self.assertEqual(
            [
                ("GET", "https://repository.apache.org/content/repositories/orgapachebeam-1427/one"),
                ("GET", "https://repository.apache.org/content/repositories/orgapachebeam-1427/two"),
            ],
            [(method, url) for method, url, _kwargs in pool_manager.requests],
        )
        self.assertTrue(
            all(
                request_kwargs["preload_content"] is False and request_kwargs["timeout"] is not None
                for _method, _url, request_kwargs in pool_manager.requests
            )
        )
        self.assertTrue(pool_manager.cleared)
        self.assertTrue(all(response.released for response in pool_manager.issued_responses))

    def test_download_session_streams_sha512_without_preloading_content(self) -> None:
        _FakePoolManager.reset(_FakeHTTPResponse(b"jar\n"))
        pool_manager = _FakePoolManager()
        downloader = DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"})),
            transport=_ResourceDownloader(pool_manager=cast(Any, pool_manager)),
        )

        actual = downloader.hash_uri("https://repository.apache.org/content/repositories/orgapachebeam-1427/app.jar")

        self.assertEqual(hashlib.sha512(b"jar\n").hexdigest(), actual)
        self.assertFalse(pool_manager.requests[0][2]["preload_content"])

    def test_parse_nexus_index_rejects_cross_origin_links(self) -> None:
        base_url = "https://repository.apache.org/content/repositories/orgapachebeam-1427/"
        html_text = (
            "<table><tr>"
            "<td><a href=\"https://example.invalid/content/repositories/orgapachebeam-1427/app.jar\">app.jar</a></td>"
            "<td>Mon Apr 27 13:17:21 UTC 2026</td>"
            "<td align=\"right\">25</td>"
            "</tr></table>"
        )

        with self.assertRaisesRegex(ValueError, "outside the repository root"):
            _parse_nexus_index(base_url, base_url, html_text)

    def test_parse_nexus_index_rejects_encoded_path_escapes(self) -> None:
        base_url = "https://repository.apache.org/content/repositories/orgapachebeam-1427/"
        html_text = (
            "<table><tr>"
            "<td><a href=\"%2e%2e/app.jar\">app.jar</a></td>"
            "<td>Mon Apr 27 13:17:21 UTC 2026</td>"
            "<td align=\"right\">25</td>"
            "</tr></table>"
        )

        with self.assertRaisesRegex(ValueError, "not normalized|outside the repository root"):
            _parse_nexus_index(base_url, base_url, html_text)

    def test_inventory_entry_sha512_rejects_mismatched_sidecar(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_path = root / "app.jar"
            artifact_path.write_bytes(b"jar\n")
            sidecar_path = root / "app.jar.sha512"
            wrong_digest = ("0" * 127) + "1"
            sidecar_path.write_text(f"{wrong_digest}  app-1.0.0.jar\n", encoding="utf-8")
            repository_file = _RepositoryFile(
                relative_path="org/example/app-1.0.0.jar",
                size_bytes=4,
                local_path=artifact_path,
            )
            sidecar_file = _RepositoryFile(
                relative_path="org/example/app-1.0.0.jar.sha512",
                size_bytes=sidecar_path.stat().st_size,
                local_path=sidecar_path,
            )
            files_by_relative_path = {
                repository_file.relative_path: repository_file,
                sidecar_file.relative_path: sidecar_file,
            }

            with self.assertRaisesRegex(
                ValueError,
                "maven-repository SHA512 sidecar does not match file bytes",
            ):
                _inventory_entry_sha512(
                    repository_file,
                    files_by_relative_path=files_by_relative_path,
                    sha512_by_relative_path={},
                    sha512_sidecars_by_relative_path={},
                    remote_http_client=None,
                )

    def test_inventory_entry_sha512_hashes_local_file_without_reading_it_fully(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact_path = root / "app.jar"
            artifact_path.write_bytes(b"jar\n")
            repository_file = _RepositoryFile(
                relative_path="org/example/app-1.0.0.jar",
                size_bytes=4,
                local_path=artifact_path,
            )

            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected read_bytes")):
                actual = _inventory_entry_sha512(
                    repository_file,
                    files_by_relative_path={repository_file.relative_path: repository_file},
                    sha512_by_relative_path={},
                    sha512_sidecars_by_relative_path={},
                    remote_http_client=None,
                )

        self.assertEqual(hashlib.sha512(b"jar\n").hexdigest(), actual)

    def test_inventory_entry_sha512_reuses_derived_remote_sidecar_metadata(self) -> None:
        jar_bytes = b"jar\n"
        jar_digest = hashlib.sha512(jar_bytes).hexdigest()
        sidecar_bytes = f"{jar_digest}  app-1.0.0.jar\n".encode()
        _FakePoolManager.reset(
            _FakeHTTPResponse(sidecar_bytes),
            _FakeHTTPResponse(jar_bytes),
        )
        pool_manager = _FakePoolManager()
        downloader = DownloadSession(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"})),
            transport=_ResourceDownloader(pool_manager=cast(Any, pool_manager)),
        )
        repository_file = _RepositoryFile(
            relative_path="org/example/app-1.0.0.jar",
            size_bytes=len(jar_bytes),
            source_url="https://repository.apache.org/content/repositories/orgapachebeam-1427/org/example/app-1.0.0.jar",
        )
        sidecar_file = _RepositoryFile(
            relative_path="org/example/app-1.0.0.jar.sha512",
            size_bytes=len(sidecar_bytes),
            source_url="https://repository.apache.org/content/repositories/orgapachebeam-1427/org/example/app-1.0.0.jar.sha512",
        )
        files_by_relative_path = {
            repository_file.relative_path: repository_file,
            sidecar_file.relative_path: sidecar_file,
        }
        sha512_by_relative_path: dict[str, str] = {}
        sha512_sidecars_by_relative_path: dict[str, Any] = {}

        sidecar_actual = _inventory_entry_sha512(
            sidecar_file,
            files_by_relative_path=files_by_relative_path,
            sha512_by_relative_path=sha512_by_relative_path,
            sha512_sidecars_by_relative_path=sha512_sidecars_by_relative_path,
            remote_http_client=downloader,
        )
        artifact_actual = _inventory_entry_sha512(
            repository_file,
            files_by_relative_path=files_by_relative_path,
            sha512_by_relative_path=sha512_by_relative_path,
            sha512_sidecars_by_relative_path=sha512_sidecars_by_relative_path,
            remote_http_client=downloader,
        )

        self.assertEqual(hashlib.sha512(sidecar_bytes).hexdigest(), sidecar_actual)
        self.assertEqual(jar_digest, artifact_actual)
        self.assertEqual(
            [
                "https://repository.apache.org/content/repositories/orgapachebeam-1427/org/example/app-1.0.0.jar.sha512",
                "https://repository.apache.org/content/repositories/orgapachebeam-1427/org/example/app-1.0.0.jar",
            ],
            [url for _method, url, _kwargs in pool_manager.requests],
        )

    def test_registration_filename_helpers_reject_path_components(self) -> None:
        with self.assertRaisesRegex(ValueError, "simple file name"):
            _generic_file_resolved_filename(None, "../artifact.zip")
        with self.assertRaisesRegex(ValueError, "simple file name"):
            _python_distribution_resolved_filename(None, "../artifact.whl")
        with self.assertRaisesRegex(ValueError, "simple file name"):
            _npm_package_resolved_filename(
                "../package.tgz",
                explicit_uri=None,
                package_name="@buildish-tooling/buildish-example",
                version="1.2.3",
            )

    def test_local_maven_repository_rejects_symlinked_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = root / "repo"
            repo.mkdir()
            target = root / "target.jar"
            target.write_bytes(b"jar")
            symlink_path = repo / "app.jar"
            try:
                symlink_path.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlink creation is not supported: {exc}")

            with self.assertRaisesRegex(ValueError, "symlinks"):
                _repository_files(
                    repo.as_uri(),
                    worker_count=1,
                    remote_http_client=None,
                    progress_reporter=cast(Any, _NoopProgress()),
                )
