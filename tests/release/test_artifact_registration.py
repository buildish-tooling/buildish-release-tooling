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

"""Focused tests for artifact-registration helpers."""

from __future__ import annotations

import unittest
from typing import ClassVar
from typing import Any, cast

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    _RepositoryFile,
    _inventory_entry_sha512,
    _RemoteHttpClient,
    _normalized_base_url,
    _parse_nexus_index,
)


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
        self.released = False

    def release_conn(self) -> None:
        self.released = True


class _FakePoolManager:
    instances: ClassVar[list[_FakePoolManager]] = []
    queued_responses: ClassVar[list[_FakeHTTPResponse]] = []

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, bool]] = []
        self.issued_responses: list[_FakeHTTPResponse] = []
        self.cleared = False
        self.__class__.instances.append(self)

    @classmethod
    def reset(cls, *responses: _FakeHTTPResponse) -> None:
        cls.instances = []
        cls.queued_responses = list(responses)

    def request(self, method: str, url: str, **kwargs: object) -> _FakeHTTPResponse:
        preload_content = bool(kwargs.get("preload_content", True))
        self.requests.append((method, url, preload_content))
        response = self.__class__.queued_responses.pop(0)
        self.issued_responses.append(response)
        return response

    def clear(self) -> None:
        self.cleared = True


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

    def test_remote_http_client_reuses_shared_pool_manager(self) -> None:
        _FakePoolManager.reset(
            _FakeHTTPResponse(b"alpha"),
            _FakeHTTPResponse(b"beta"),
        )
        pool_manager = _FakePoolManager()
        client = _RemoteHttpClient(pool_manager=cast(Any, pool_manager))

        first = client.read_bytes("https://repository.apache.org/content/repositories/orgapachebeam-1427/one")
        second = client.read_bytes("https://repository.apache.org/content/repositories/orgapachebeam-1427/two")
        client.close()

        self.assertEqual(b"alpha", first)
        self.assertEqual(b"beta", second)
        self.assertEqual(1, len(_FakePoolManager.instances))
        self.assertEqual(
            [
                ("GET", "https://repository.apache.org/content/repositories/orgapachebeam-1427/one", True),
                ("GET", "https://repository.apache.org/content/repositories/orgapachebeam-1427/two", True),
            ],
            pool_manager.requests,
        )
        self.assertTrue(pool_manager.cleared)
        self.assertTrue(all(response.released for response in pool_manager.issued_responses))

    def test_inventory_entry_sha512_rejects_mismatched_sidecar(self) -> None:
        repository_file = _RepositoryFile(
            relative_path="org/example/app-1.0.0.jar",
            size_bytes=4,
            local_path=None,
            source_url="https://repository.apache.org/content/repositories/orgapachebeam-1427/org/example/app-1.0.0.jar",
        )
        sidecar_file = _RepositoryFile(
            relative_path="org/example/app-1.0.0.jar.sha512",
            size_bytes=129,
            local_path=None,
            source_url="https://repository.apache.org/content/repositories/orgapachebeam-1427/org/example/app-1.0.0.jar.sha512",
        )
        files_by_relative_path = {
            repository_file.relative_path: repository_file,
            sidecar_file.relative_path: sidecar_file,
        }
        jar_bytes = b"jar\n"
        wrong_digest = ("0" * 127) + "1"
        cache = {
            repository_file.relative_path: jar_bytes,
            sidecar_file.relative_path: f"{wrong_digest}  app-1.0.0.jar\n".encode(),
        }

        with self.assertRaisesRegex(
            ValueError,
            "maven-repository SHA512 sidecar does not match file bytes",
        ):
            _inventory_entry_sha512(
                repository_file,
                files_by_relative_path=files_by_relative_path,
                cache=cache,
                remote_http_client=None,
            )
