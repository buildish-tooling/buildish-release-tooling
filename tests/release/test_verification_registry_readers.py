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

"""Unit tests for typed external registry/index reader subsets."""

from __future__ import annotations

import json
import unittest

from apache_buildish_release_tooling.release.verification.secondary.npm_package import (
    _NpmRegistryMetadataRead,
    _typed_npm_registry_metadata,
)
from apache_buildish_release_tooling.release.verification.secondary.python_distribution import (
    _simple_index_json_entries,
)


class VerificationRegistryReadersTest(unittest.TestCase):
    """Keep tolerant external registry/index readers explicit and well covered."""

    def test_simple_index_json_entries_rejects_non_object_payload(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "python-distribution simple index JSON must be an object with a files list",
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
            "python-distribution simple index JSON must be an object with a files list",
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


if __name__ == "__main__":
    unittest.main()
