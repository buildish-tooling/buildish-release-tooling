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

"""Unit tests for typed external registry/index reader subsets."""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

from pydantic import ValidationError

from buildish_release_tooling.release.artifact_registration.kinds.oci_image import (
    _inspect_image_ref,
)
from buildish_release_tooling.release.verification.secondary.npm_package import (
    _NpmRegistryMetadataRead,
    _npm_registry_package_metadata,
    _typed_npm_registry_metadata,
)
from buildish_release_tooling.release.verification.secondary.python_distribution import (
    _simple_index_json_entries,
)


class VerificationRegistryReadersTest(unittest.TestCase):
    """Keep tolerant external registry/index readers explicit and well covered."""

    def test_simple_index_json_entries_rejects_malformed_payload_variants(self) -> None:
        malformed_payloads = (
            b'{"files": 17}',
            b'{"files": [17]}',
            b'{"files": [{"filename": [], "url": "packages/example.whl"}]}',
        )
        for payload_bytes in malformed_payloads:
            with self.subTest(payload_bytes=payload_bytes):
                with self.assertRaisesRegex(
                    ValueError,
                    "python-distribution simple index JSON at .* returned a malformed simple-index payload",
                ):
                    _simple_index_json_entries(
                        "https://example.invalid/simple/buildish-example/",
                        payload_bytes,
                    )

    def test_simple_index_json_entries_rejects_non_object_payload(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "python-distribution simple index JSON at .* did not return a JSON object payload",
        ):
            _simple_index_json_entries(
                "https://example.invalid/simple/buildish-example/",
                b"[]",
            )

    def test_simple_index_json_entries_skips_incomplete_entries_and_normalizes_hashes(self) -> None:
        entries = _simple_index_json_entries(
            "https://example.invalid/simple/buildish-example/",
            json.dumps(
                {
                    "files": [
                        {
                            "filename": "buildish_example-1.2.3-py3-none-any.whl",
                            "url": "packages/buildish_example-1.2.3-py3-none-any.whl",
                            "hashes": {
                                "SHA256": "A" * 64,
                                "sha512": "B" * 128,
                            },
                        },
                        {
                            "filename": "",
                            "url": "packages/ignored.whl",
                        },
                        {
                            "filename": "missing-url.whl",
                        },
                    ]
                }
            ).encode("utf-8"),
        )

        self.assertEqual(1, len(entries))
        self.assertEqual(
            "buildish_example-1.2.3-py3-none-any.whl",
            entries[0].filename,
        )
        self.assertEqual(
            "https://example.invalid/simple/buildish-example/packages/buildish_example-1.2.3-py3-none-any.whl",
            entries[0].url,
        )
        self.assertEqual(
            {
                "sha256": "a" * 64,
                "sha512": "b" * 128,
            },
            entries[0].hashes,
        )

    def test_simple_index_json_entries_rejects_non_string_hash_values(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "python-distribution simple index JSON at .* returned a malformed simple-index payload",
        ):
            _simple_index_json_entries(
                "https://example.invalid/simple/buildish-example/",
                json.dumps(
                    {
                        "files": [
                            {
                                "filename": "buildish_example-1.2.3-py3-none-any.whl",
                                "url": "packages/buildish_example-1.2.3-py3-none-any.whl",
                                "hashes": {
                                    "sha256": 17,
                                },
                            }
                        ]
                    }
                ).encode("utf-8"),
            )

    def test_typed_npm_registry_metadata_skips_incomplete_versions(self) -> None:
        metadata = _typed_npm_registry_metadata(
            _NpmRegistryMetadataRead.model_validate(
                {
                    "versions": {
                        "1.2.3": {
                            "name": "buildish-example",
                            "version": "1.2.3",
                            "dist": {
                                "tarball": "https://registry.example.invalid/buildish-example/-/buildish-example-1.2.3.tgz",
                                "integrity": "sha512-abc",
                                "signatures": [{}, {}],
                            },
                        },
                        "1.2.4": {
                            "name": "buildish-example",
                            "version": "1.2.4",
                            "dist": {
                                "tarball": "",
                                "integrity": "sha512-def",
                            },
                        },
                        "1.2.5": {
                            "name": "buildish-example",
                            "version": "1.2.5",
                        },
                    }
                }
            ),
            metadata_url="https://registry.example.invalid/buildish-example",
            found_via="plain-path",
        )

        self.assertEqual(
            ["1.2.3"],
            list(metadata.versions),
        )
        version_entry = metadata.versions["1.2.3"]
        self.assertEqual("buildish-example", version_entry.name)
        self.assertEqual("1.2.3", version_entry.version)
        self.assertEqual(
            "https://registry.example.invalid/buildish-example/-/buildish-example-1.2.3.tgz",
            version_entry.dist.tarball,
        )
        self.assertEqual("sha512-abc", version_entry.dist.integrity)
        self.assertEqual(2, version_entry.dist.signatures_count)

    def test_npm_registry_metadata_reader_rejects_malformed_payload_variants(self) -> None:
        malformed_payloads: tuple[dict[str, object], ...] = (
            {"versions": []},
            {
                "versions": {
                    "1.2.3": {
                        "name": "buildish-example",
                        "version": "1.2.3",
                        "dist": {
                            "tarball": "https://registry.example.invalid/buildish-example/-/buildish-example-1.2.3.tgz",
                            "integrity": 17,
                        },
                    }
                }
            },
            {
                "versions": {
                    "1.2.3": {
                        "name": "buildish-example",
                        "version": "1.2.3",
                        "dist": {
                            "tarball": "https://registry.example.invalid/buildish-example/-/buildish-example-1.2.3.tgz",
                            "integrity": "sha512-abc",
                            "signatures": {},
                        },
                    }
                }
            },
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    _NpmRegistryMetadataRead.model_validate(payload)

    def test_npm_registry_package_metadata_reports_normalized_malformed_payload_error(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.verification.secondary.npm_package._npm_registry_metadata_urls",
            return_value=(("https://registry.example.invalid/buildish-example", "plain-path"),),
        ), mock.patch(
            "buildish_release_tooling.release.verification.secondary.npm_package._read_npm_registry_bytes",
            return_value=b"[]",
        ):
            with self.assertRaisesRegex(
                ValueError,
                "npm-package registry metadata could not be fetched for buildish-example: "
                "https://registry.example.invalid/buildish-example: "
                "npm-package registry metadata at https://registry.example.invalid/buildish-example "
                "did not return a JSON object payload",
            ):
                _npm_registry_package_metadata(
                    "https://registry.example.invalid/",
                    "buildish-example",
                    allow_non_production_release_targets=True,
                )

    def test_inspect_image_ref_rejects_invalid_external_payload_variants(self) -> None:
        malformed_payloads: tuple[tuple[str, str], ...] = (
            (
                "[]",
                "oci-image docker buildx imagetools inspect for --image-ref .* did not return a JSON object payload",
            ),
            (
                json.dumps(
                    {
                        "digest": "sha256:" + ("a1" * 32),
                        "manifests": [
                            {
                                "digest": "sha256:" + ("b2" * 32),
                                "platform": {"os": "linux", "architecture": "amd64"},
                            },
                            {
                                "digest": "sha256:" + ("c3" * 32),
                                "platform": {"os": "linux", "architecture": "amd64"},
                            },
                        ],
                    }
                ),
                "oci-image registry manifest declared platform more than once: linux/amd64",
            ),
        )
        for payload_text, error_fragment in malformed_payloads:
            with self.subTest(error_fragment=error_fragment):
                with mock.patch(
                    "buildish_release_tooling.release.artifact_registration.kinds.oci_image.run_logged_command",
                    return_value=subprocess.CompletedProcess([], 0, payload_text, ""),
                ):
                    with self.assertRaisesRegex(ValueError, error_fragment):
                        _inspect_image_ref("ghcr.io/buildish-tooling/buildish-example:latest")


if __name__ == "__main__":
    unittest.main()
