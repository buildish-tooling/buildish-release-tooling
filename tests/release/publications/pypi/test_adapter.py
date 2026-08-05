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

"""PyPI publication adapter command and evidence tests."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import time
from argparse import Namespace
from email.message import Message
from pathlib import Path
from typing import Any, cast
from unittest import mock
from urllib.error import HTTPError

from buildish_release_tooling.release.commands.pypi import (
    run_verify_pypi_attestations,
    run_verify_pypi_publication,
)
from buildish_release_tooling.release.config import load_release_config
from buildish_release_tooling.release.commands.lifecycle import (
    run_create_release_manifest,
)
from buildish_release_tooling.release.core.models import (
    ArtifactReference,
    PublicationReference,
)
from buildish_release_tooling.release.core.state import (
    DirectReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.manifests import ReleaseManifestV1
from buildish_release_tooling.release.platforms.github.commands import (
    _validate_release_manifest,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    GitHubFinalPublication,
)
from buildish_release_tooling.release.publications.pypi.verification import (
    _RetryablePyPiRequestError,
    _read_pypi_release,
    _validate_release_identity,
)
from buildish_release_tooling.release.publications.pypi.attestations import (
    AttestationType,
    _verified_publish_attestations,
    _verified_publish_attestations_with_deadline,
)
from buildish_release_tooling.release.publications.pypi.config import (
    PyPiPublicationConfig,
)
from buildish_release_tooling.release.publications.evidence import _validated_adapters
from buildish_release_tooling.shared.downloader import DownloadSession
from tests.release.commands.support import (
    ReleaseCommandsIntegrationTestSupport,
    cleanup_sandbox,
    create_build_test_sandbox,
)
from tests.release.state_support import candidate_release_state


def _block_attestation_verification(*_args: object, **_kwargs: object) -> list[object]:
    time.sleep(60)
    return []


def _close_attestation_worker(connection: object, *_args: object) -> None:
    cast(Any, connection).close()
    time.sleep(60)


class PyPiPublicationTest(ReleaseCommandsIntegrationTestSupport):
    def test_attestation_verification_worker_enforces_total_timeout(self) -> None:
        if "fork" not in multiprocessing.get_all_start_methods():
            self.skipTest("blocking worker test requires the fork start method")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        distribution = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        distribution.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.example.invalid/dev",
            release_base_url="https://dist.example.invalid/release",
            secondary_targets=("pypi",),
        )
        config = cast(
            PyPiPublicationConfig,
            load_release_config(str(config_path)).publication.secondary[0],
        )
        started = time.monotonic()
        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations._VERIFICATION_PROCESS_START_METHOD",
                "fork",
            ),
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations._verified_publish_attestations",
                side_effect=_block_attestation_verification,
            ),
            self.assertRaisesRegex(RuntimeError, "total timeout"),
        ):
            _verified_publish_attestations_with_deadline(
                b"{}",
                distribution,
                config,
                deadline_monotonic=time.monotonic() + 0.1,
            )
        self.assertLess(time.monotonic() - started, 3.0)

        child_pids_before = {child.pid for child in multiprocessing.active_children()}
        started = time.monotonic()
        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations._VERIFICATION_PROCESS_START_METHOD",
                "fork",
            ),
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations._verify_attestations_worker",
                side_effect=_close_attestation_worker,
            ),
            self.assertRaisesRegex(RuntimeError, "without a result"),
        ):
            _verified_publish_attestations_with_deadline(
                b"{}",
                distribution,
                config,
                deadline_monotonic=time.monotonic() + 0.1,
            )
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(
            child_pids_before,
            {child.pid for child in multiprocessing.active_children()},
        )

        with self.assertRaisesRegex(ValueError, "provenance or distribution"):
            _verified_publish_attestations_with_deadline(
                b"{}",
                distribution,
                config,
                deadline_monotonic=time.monotonic() + 10.0,
            )

    def test_publication_adapter_registry_rejects_ownership_collisions(self) -> None:
        def adapter(key: str, action: str) -> mock.MagicMock:
            value = mock.MagicMock()
            value.key = key
            value.publication_actions = frozenset({action})
            value.verification_actions = frozenset()
            value.publication_target_kinds = frozenset()
            value.verification_result_kinds = frozenset()
            value.config_kinds = frozenset()
            return value

        with self.assertRaisesRegex(ValueError, "discriminator collision"):
            _validated_adapters((adapter("one", "publish"), adapter("two", "publish")))
        with self.assertRaisesRegex(ValueError, "duplicate publication adapter key"):
            _validated_adapters((adapter("same", "one"), adapter("same", "two")))

    def test_attestation_selection_requires_publish_predicate_from_expected_publisher(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        distribution = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        distribution.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.example.invalid/dev",
            release_base_url="https://dist.example.invalid/release",
            secondary_targets=("pypi",),
        )
        config = cast(
            PyPiPublicationConfig,
            load_release_config(str(config_path)).publication.secondary[0],
        )
        expected_publisher = object()
        unrelated_attestation = mock.MagicMock()
        publish_attestation = mock.MagicMock()
        publish_attestation.verify.return_value = (
            AttestationType.PYPI_PUBLISH_V1.value,
            {},
        )
        publish_attestation.model_dump.return_value = {"version": 1, "publish": True}
        slsa_attestation = mock.MagicMock()
        slsa_attestation.verify.return_value = ("https://slsa.dev/provenance/v1", {})
        matching_bundle = mock.MagicMock(
            publisher=expected_publisher,
            attestations=[slsa_attestation, publish_attestation],
        )
        unrelated_bundle = mock.MagicMock(
            publisher=object(), attestations=[unrelated_attestation]
        )
        provenance = mock.MagicMock(
            attestation_bundles=[unrelated_bundle, matching_bundle]
        )
        provenance_type = mock.MagicMock()
        provenance_type.model_validate_json.return_value = provenance
        distribution_type = mock.MagicMock()
        distribution_type.from_file.return_value = object()

        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations.GitHubPublisher",
                return_value=expected_publisher,
            ),
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations.Provenance",
                provenance_type,
            ),
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations.Distribution",
                distribution_type,
            ),
        ):
            selected = _verified_publish_attestations(b"{}", distribution, config)
            self.assertEqual([{"version": 1, "publish": True}], selected)
            unrelated_attestation.verify.assert_not_called()

            matching_bundle.attestations = [slsa_attestation]
            with self.assertRaisesRegex(ValueError, "no verified PyPI Publish"):
                _verified_publish_attestations(b"{}", distribution, config)

            provenance.attestation_bundles = [unrelated_bundle]
            with self.assertRaisesRegex(ValueError, "no bundle"):
                _verified_publish_attestations(b"{}", distribution, config)

    def test_publication_command_requires_selected_pypi_target(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("github-action",),
        )
        args = Namespace(component_config=str(config_path), test_target_mode=True)

        with self.assertRaisesRegex(ValueError, "configured PyPI secondary target"):
            run_verify_pypi_publication(args)

    def test_pypi_client_treats_only_not_found_as_absent(self) -> None:
        session = mock.MagicMock(spec=DownloadSession)
        session.read_bytes.side_effect = HTTPError(
            "https://pypi.example.invalid/project/1.2.3/json",
            404,
            "missing",
            Message(),
            None,
        )

        self.assertIsNone(
            _read_pypi_release(
                session,
                "https://pypi.example.invalid/project/1.2.3/json",
            )
        )

        session.read_bytes.side_effect = HTTPError(
            "https://pypi.example.invalid/project/1.2.3/json",
            500,
            "failure",
            Message(),
            None,
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
            _read_pypi_release(
                session,
                "https://pypi.example.invalid/project/1.2.3/json",
            )

        session.read_bytes.side_effect = HTTPError(
            "https://pypi.example.invalid/project/1.2.3/json",
            403,
            "forbidden",
            Message(),
            None,
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            _read_pypi_release(
                session,
                "https://pypi.example.invalid/project/1.2.3/json",
            )

    def test_pypi_client_rejects_invalid_json(self) -> None:
        session = mock.MagicMock(spec=DownloadSession)
        session.read_bytes.return_value = b"not JSON"

        with self.assertRaisesRegex(ValueError, "not valid UTF-8 JSON"):
            _read_pypi_release(
                session,
                "https://pypi.example.invalid/project/1.2.3/json",
            )

    def test_pypi_identity_accepts_pep440_normalized_semver(self) -> None:
        _validate_release_identity(
            {"info": {"name": "Example_Project", "version": "1.0.0rc1"}},
            project_name="example-project",
            version="1.0.0-rc.1",
        )
        with self.assertRaisesRegex(ValueError, "version does not match"):
            _validate_release_identity(
                {"info": {"name": "example-project", "version": "1.0.0rc2"}},
                project_name="example-project",
                version="1.0.0-rc.1",
            )

    @staticmethod
    def _write_direct_state(sandbox_dir: Path) -> str:
        candidate = candidate_release_state()
        state = DirectReleaseState(
            release=candidate.release,
            source=candidate.source,
            source_date_epoch=candidate.source_date_epoch,
            final_tag=candidate.final_tag_identity,
        )
        path = sandbox_dir / "direct-state.json"
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def test_verifies_exact_remote_distribution_bytes(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "pypi-result.json"
        wheel = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        sdist = sandbox_dir / "example_project-1.2.3.tar.gz"
        wheel.write_bytes(b"wheel\n")
        sdist.write_bytes(b"sdist\n")
        unrelated = sandbox_dir / "documentation-1.2.3.tar.gz"
        unrelated.write_bytes(b"docs\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        payload = {
            "info": {"name": "example-project", "version": "1.2.3"},
            "urls": [
                {
                    "filename": path.name,
                    "digests": {
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                    },
                    "size": path.stat().st_size,
                    "url": f"https://files.pythonhosted.org/{path.name}",
                }
                for path in (wheel, sdist)
            ],
        }
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=True,
            version="1.2.3",
            project_name="example-project",
            repository_api_url="https://pypi.org/pypi",
            project_url_template="https://pypi.org/project/{project}/{version}/",
            attempts=1,
            retry_delay=0,
            allow_incomplete=False,
            release_state=self._write_direct_state(sandbox_dir),
            distributions=[str(wheel), str(sdist), str(unrelated)],
        )

        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
                return_value=payload,
            ) as read_release,
            mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_STEP_SUMMARY": str(sandbox_dir / "summary.md"),
                    "MANIFEST_PATH": str(manifest_path),
                },
            ),
        ):
            result_path = run_verify_pypi_publication(args)

        self.assertEqual(manifest_path, result_path)
        read_release.assert_called_once()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("example-project", manifest["project_name"])
        self.assertEqual("1.2.3", manifest["version"])
        self.assertEqual("complete", manifest["publication_state"])
        self.assertEqual("direct", manifest["lifecycle"])
        self.assertEqual(
            candidate_release_state().source.commit_sha,
            manifest["source_commit"],
        )
        self.assertEqual(
            sorted([wheel.name, sdist.name]),
            sorted(entry["logical_name"] for entry in manifest["published_files"]),
        )

        partial_manifest_path = sandbox_dir / "pypi-partial-result.json"
        github_output_path = sandbox_dir / "github-output.txt"
        args.allow_incomplete = True
        payload_urls = payload["urls"]
        if not isinstance(payload_urls, list):
            self.fail("test package-index payload URLs must be a list")
        partial_payload = {**payload, "urls": payload_urls[:1]}
        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
                return_value=partial_payload,
            ),
            mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_OUTPUT": str(github_output_path),
                    "GITHUB_STEP_SUMMARY": str(sandbox_dir / "partial-summary.md"),
                    "MANIFEST_PATH": str(partial_manifest_path),
                },
            ),
        ):
            run_verify_pypi_publication(args)
        partial_manifest = json.loads(partial_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("partial", partial_manifest["publication_state"])
        self.assertEqual(
            "publication_state=partial\n",
            github_output_path.read_text(encoding="utf-8"),
        )

    def test_rejects_remote_file_with_different_digest(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        wheel = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        wheel.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=True,
            version="1.2.3",
            project_name="example-project",
            repository_api_url="https://pypi.org/pypi",
            project_url_template="https://pypi.org/project/{project}/{version}/",
            attempts=1,
            retry_delay=0,
            allow_incomplete=False,
            release_state=self._write_direct_state(sandbox_dir),
            distributions=[str(wheel)],
        )
        payload = {
            "info": {"name": "example-project", "version": "1.2.3"},
            "urls": [
                {
                    "filename": wheel.name,
                    "digests": {"sha256": "0" * 64},
                    "size": wheel.stat().st_size,
                    "url": f"https://files.pythonhosted.org/{wheel.name}",
                }
            ],
        }

        with mock.patch(
            "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
            return_value=payload,
        ):
            with self.assertRaisesRegex(ValueError, "differs from candidate"):
                run_verify_pypi_publication(args)

    def test_reuses_one_pooled_session_across_polling_attempts(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "pypi-result.json"
        wheel = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        wheel.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=True,
            version="1.2.3",
            project_name="example-project",
            repository_api_url="https://pypi.org/pypi",
            project_url_template="https://pypi.org/project/{project}/{version}/",
            attempts=2,
            retry_delay=0,
            allow_incomplete=False,
            release_state=self._write_direct_state(sandbox_dir),
            distributions=[str(wheel)],
        )
        payload = {
            "info": {"name": "example-project", "version": "1.2.3"},
            "urls": [
                {
                    "filename": wheel.name,
                    "digests": {
                        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()
                    },
                    "size": wheel.stat().st_size,
                    "url": f"https://files.pythonhosted.org/{wheel.name}",
                }
            ],
        }
        session = object()
        session_context = mock.MagicMock()
        session_context.__enter__.return_value = session

        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification.DownloadSession.harness",
                return_value=session_context,
            ) as session_factory,
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
                side_effect=(None, payload),
            ) as read_release,
            mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_STEP_SUMMARY": str(sandbox_dir / "summary.md"),
                    "MANIFEST_PATH": str(manifest_path),
                },
            ),
        ):
            run_verify_pypi_publication(args)

        session_factory.assert_called_once()
        self.assertEqual(2, read_release.call_count)
        self.assertTrue(
            all(call.args[0] is session for call in read_release.call_args_list)
        )
        session_context.__exit__.assert_called_once()

    def test_retries_transient_transport_failure_within_one_session(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "pypi-result.json"
        wheel = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        wheel.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=True,
            version="1.2.3",
            repository_api_url="https://pypi.org/pypi",
            project_url_template="https://pypi.org/project/{project}/{version}/",
            attempts=2,
            retry_delay=0,
            total_timeout=30,
            allow_incomplete=False,
            release_state=self._write_direct_state(sandbox_dir),
            distributions=[str(wheel)],
        )
        payload = {
            "info": {"name": "example-project", "version": "1.2.3"},
            "urls": [
                {
                    "filename": wheel.name,
                    "digests": {
                        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()
                    },
                    "size": wheel.stat().st_size,
                    "url": f"https://files.pythonhosted.org/{wheel.name}",
                }
            ],
        }
        session_context = mock.MagicMock()
        session_context.__enter__.return_value = object()
        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification.DownloadSession.harness",
                return_value=session_context,
            ),
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
                side_effect=(
                    _RetryablePyPiRequestError("temporary"),
                    payload,
                ),
            ) as read_release,
            mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_STEP_SUMMARY": str(sandbox_dir / "summary.md"),
                    "MANIFEST_PATH": str(manifest_path),
                },
            ),
        ):
            run_verify_pypi_publication(args)
        self.assertEqual(2, read_release.call_count)

        exhausted_context = mock.MagicMock()
        exhausted_context.__enter__.return_value = object()
        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification.DownloadSession.harness",
                return_value=exhausted_context,
            ),
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
                side_effect=(
                    _RetryablePyPiRequestError("temporary one"),
                    _RetryablePyPiRequestError("temporary two"),
                ),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "exhausted"):
                run_verify_pypi_publication(args)

    def test_attestation_command_uses_configured_publisher_and_pooled_session(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "attestation-evidence.json"
        wheel = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        wheel.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        provenance = json.dumps(
            {
                "attestation_bundles": [
                    {
                        "publisher": {
                            "kind": "GitHub",
                            "repository": "example/example",
                            "workflow": "release.yml",
                            "environment": "pypi",
                        },
                        "attestations": [{"envelope": "fixture"}],
                    }
                ]
            }
        ).encode()
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=False,
            integrity_api_url=None,
            attempts=1,
            retry_delay=0,
            total_timeout=30,
            provenance_dir=str(sandbox_dir / "provenance"),
            version="1.2.3",
            distributions=[str(wheel)],
        )
        session = mock.MagicMock(spec=DownloadSession)
        session.read_bytes.return_value = provenance
        session_context = mock.MagicMock()
        session_context.__enter__.return_value = session
        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations.DownloadSession.production",
                return_value=session_context,
            ),
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.attestations._verified_publish_attestations_with_deadline",
                return_value=[{"version": 1, "fixture": "publish"}],
            ) as verifier,
            mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_STEP_SUMMARY": str(sandbox_dir / "summary.md"),
                    "MANIFEST_PATH": str(manifest_path),
                },
            ),
        ):
            run_verify_pypi_attestations(args)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("verify-pypi-attestations", manifest["action"])
        self.assertEqual("example/example", manifest["publisher"]["repository"])
        session.read_bytes.assert_called_once()
        self.assertEqual(
            {"Accept": "application/vnd.pypi.integrity.v1+json"},
            session.read_bytes.call_args.kwargs["headers"],
        )
        verifier.assert_called_once()
        evidence_path = (
            sandbox_dir
            / "provenance"
            / "buildish-verification-evidence--example_project-1.2.3-py3-none-any.whl.publish-attestations.json"
        )
        self.assertTrue(evidence_path.is_file())
        self.assertEqual(evidence_path.name, manifest["files"][0]["evidence_filename"])

    def test_reports_absent_release_when_index_returns_not_found(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "pypi-absent-result.json"
        wheel = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        wheel.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=True,
            version="1.2.3",
            project_name="example-project",
            repository_api_url="https://pypi.org/pypi",
            project_url_template="https://pypi.org/project/{project}/{version}/",
            attempts=1,
            retry_delay=0,
            allow_incomplete=True,
            release_state=self._write_direct_state(sandbox_dir),
            distributions=[str(wheel)],
        )

        with (
            mock.patch(
                "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
                return_value=None,
            ),
            mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_STEP_SUMMARY": str(sandbox_dir / "summary.md"),
                    "MANIFEST_PATH": str(manifest_path),
                },
            ),
        ):
            run_verify_pypi_publication(args)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("absent", manifest["publication_state"])
        self.assertEqual([], manifest["published_files"])

    def test_rejects_unexpected_remote_filename(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        wheel = sandbox_dir / "example_project-1.2.3-py3-none-any.whl"
        wheel.write_bytes(b"wheel\n")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=True,
            version="1.2.3",
            project_name="example-project",
            repository_api_url="https://pypi.org/pypi",
            project_url_template="https://pypi.org/project/{project}/{version}/",
            attempts=1,
            retry_delay=0,
            allow_incomplete=True,
            release_state=self._write_direct_state(sandbox_dir),
            distributions=[str(wheel)],
        )
        payload = {
            "info": {"name": "example-project", "version": "1.2.3"},
            "urls": [
                {
                    "filename": "unexpected-1.2.3.tar.gz",
                    "digests": {"sha256": "a" * 64},
                    "size": 1,
                    "url": "https://files.pythonhosted.org/unexpected-1.2.3.tar.gz",
                }
            ],
        }

        with mock.patch(
            "buildish_release_tooling.release.publications.pypi.verification._read_pypi_release",
            return_value=payload,
        ):
            with self.assertRaisesRegex(ValueError, "unexpected files"):
                run_verify_pypi_publication(args)

    def test_final_manifest_binds_pypi_files_to_promoted_artifacts(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/example",
            release_base_url="https://dist.apache.org/repos/dist/release/example",
            secondary_targets=("pypi",),
        )
        candidate = candidate_release_state()
        wheel = ArtifactReference(
            kind="generic-file",
            logical_name="example_project-1.2.3-py3-none-any.whl",
            digests={"sha256": "a" * 64},
            size_bytes=10,
        )
        sdist = ArtifactReference(
            kind="generic-file",
            logical_name="example_project-1.2.3.tar.gz",
            digests={"sha256": "b" * 64},
            size_bytes=20,
        )
        unrelated_archive = ArtifactReference(
            kind="generic-file",
            logical_name="documentation-1.2.3.tar.gz",
            digests={"sha256": "c" * 64},
            size_bytes=30,
        )
        published_wheel = wheel.model_copy(update={"kind": "python-distribution"})
        published_sdist = sdist.model_copy(update={"kind": "python-distribution"})
        promotion = PromotionState(
            release=candidate.release,
            source=candidate.source,
            source_date_epoch=candidate.source_date_epoch,
            candidate=candidate.candidate,
            candidate_manifest_digest="c" * 64,
            final_tag=candidate.final_tag_identity,
            artifacts=[wheel, sdist, unrelated_archive],
            publications=[
                PublicationReference(
                    target_kind="github-release-candidate",
                    uri="https://github.com/example/example/releases/tag/v1.2.3-rc2",
                    immutable_id="41",
                )
            ],
        )
        state_path = sandbox_dir / "promotion-state.json"
        state_path.write_text(promotion.model_dump_json(indent=2), encoding="utf-8")
        publication_path = sandbox_dir / "github-publication.json"
        publication_path.write_text(
            json.dumps(
                {
                    "component": "example-project",
                    "version": "1.2.3",
                    "source_commit": candidate.source.commit_sha,
                    "publication": {
                        "repository": "example/example",
                        "release_id": 42,
                        "release_url": "https://github.com/example/example/releases/tag/v1.2.3",
                        "created_at": "2026-08-05T09:00:00Z",
                        "published_at": "2026-08-05T09:05:00Z",
                        "tag": "v1.2.3",
                        "draft": False,
                        "prerelease": False,
                        "assets": [],
                    },
                    "action": "publish-github-final-release",
                    "outcome": "published",
                }
            ),
            encoding="utf-8",
        )
        pypi_path = sandbox_dir / "pypi-publication.json"
        pypi_path.write_text(
            json.dumps(
                {
                    "component": "example-project",
                    "action": "verify-pypi-publication",
                    "project_name": "example-project",
                    "version": "1.2.3",
                    "repository_api_url": "https://pypi.org/pypi",
                    "project_url": "https://pypi.org/project/example-project/1.2.3/",
                    "lifecycle": "candidate-promotion",
                    "source_commit": candidate.source.commit_sha,
                    "release_state_sha256": hashlib.sha256(
                        state_path.read_bytes()
                    ).hexdigest(),
                    "publication_state": "complete",
                    "published_files": [
                        published_wheel.model_dump(mode="json"),
                        published_sdist.model_dump(mode="json"),
                    ],
                }
            ),
            encoding="utf-8",
        )
        attestation_path = sandbox_dir / "attestation-evidence.json"
        attestation_path.write_text(
            json.dumps(
                {
                    "component": "example-project",
                    "action": "verify-pypi-attestations",
                    "kind": "pypi-attestation-verification",
                    "schema_version": "1",
                    "project_name": "example-project",
                    "version": "1.2.3",
                    "integrity_base_url": "https://pypi.org/integrity",
                    "publisher": {
                        "kind": "GitHub",
                        "repository": "example/example",
                        "workflow": "release.yml",
                        "environment": "pypi",
                    },
                    "files": [
                        {
                            "filename": wheel.logical_name,
                            "distribution_sha256": wheel.digests["sha256"],
                            "evidence_filename": f"buildish-verification-evidence--{wheel.logical_name}.publish-attestations.json",
                            "evidence_sha256": "d" * 64,
                            "evidence_size_bytes": 101,
                            "source_provenance_url": (
                                "https://pypi.org/integrity/example-project/1.2.3/"
                                f"{wheel.logical_name}/provenance"
                            ),
                            "publish_attestation_count": 1,
                        },
                        {
                            "filename": sdist.logical_name,
                            "distribution_sha256": sdist.digests["sha256"],
                            "evidence_filename": f"buildish-verification-evidence--{sdist.logical_name}.publish-attestations.json",
                            "evidence_sha256": "e" * 64,
                            "evidence_size_bytes": 102,
                            "source_provenance_url": (
                                "https://pypi.org/integrity/example-project/1.2.3/"
                                f"{sdist.logical_name}/provenance"
                            ),
                            "publish_attestation_count": 1,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        evidence_attachment_path = sandbox_dir / "evidence-attachment.json"
        evidence_attachment_path.write_text(
            json.dumps(
                {
                    "component": "example-project",
                    "action": "attach-github-release-assets",
                    "version": "1.2.3",
                    "repository_slug": "example/example",
                    "release_id": "42",
                    "release_name": "Example Project 1.2.3",
                    "release_tag": "v1.2.3",
                    "release_url": "https://github.com/example/example/releases/tag/v1.2.3",
                    "primary_asset_names": [
                        f"buildish-verification-evidence--{wheel.logical_name}.publish-attestations.json",
                        f"buildish-verification-evidence--{sdist.logical_name}.publish-attestations.json",
                    ],
                    "primary_assets": [
                        {
                            "kind": "verification-evidence",
                            "logical_name": f"buildish-verification-evidence--{wheel.logical_name}.publish-attestations.json",
                            "digests": {"sha256": "d" * 64},
                            "size_bytes": 101,
                        },
                        {
                            "kind": "verification-evidence",
                            "logical_name": f"buildish-verification-evidence--{sdist.logical_name}.publish-attestations.json",
                            "digests": {"sha256": "e" * 64},
                            "size_bytes": 102,
                        },
                    ],
                    "uploaded_asset_names": [],
                    "generated_checksum_asset_names": [],
                    "generated_signature_asset_names": [],
                    "checksum_algorithms": [],
                    "gpg_fingerprint": "",
                }
            ),
            encoding="utf-8",
        )
        manifest_path = sandbox_dir / "release-manifest.json"
        args = Namespace(
            component_config=str(config_path),
            test_target_mode=True,
            release_state=str(state_path),
            publication_result=str(publication_path),
            secondary_publication_result=[str(pypi_path)],
            secondary_verification_result=[str(attestation_path)],
            verification_evidence_publication_result=[str(evidence_attachment_path)],
        )
        with mock.patch.dict(
            "os.environ",
            {
                "GITHUB_STEP_SUMMARY": str(sandbox_dir / "manifest-summary.md"),
                "MANIFEST_PATH": str(manifest_path),
            },
        ):
            run_create_release_manifest(args)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "example-project==1.2.3",
            manifest["secondary_publications"][0]["immutable_id"],
        )
        self.assertEqual("2026-08-05T09:05:00Z", manifest["created_at"])
        self.assertEqual(2, len(manifest["verification_results"]))
        self.assertEqual(
            "pypi-publish-attestation",
            manifest["verification_results"][0]["kind"],
        )
        _validate_release_manifest(
            ReleaseManifestV1.model_validate(manifest),
            promotion,
            GitHubFinalPublication.model_validate(
                json.loads(publication_path.read_text(encoding="utf-8"))["publication"]
            ),
            load_release_config(str(config_path)),
            test_target_mode=True,
        )

        attachment_payload = json.loads(
            evidence_attachment_path.read_text(encoding="utf-8")
        )
        attachment_payload["primary_assets"][0]["kind"] = "release-asset"
        evidence_attachment_path.write_text(
            json.dumps(attachment_payload), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "immutable mode"):
            run_create_release_manifest(args)
        attachment_payload["primary_assets"][0]["kind"] = "verification-evidence"
        original_evidence_name = attachment_payload["primary_asset_names"][0]
        attachment_payload["primary_asset_names"][0] = "unreserved-evidence.json"
        attachment_payload["primary_assets"][0]["logical_name"] = (
            "unreserved-evidence.json"
        )
        evidence_attachment_path.write_text(
            json.dumps(attachment_payload), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "reserved asset namespace"):
            run_create_release_manifest(args)
        attachment_payload["primary_asset_names"][0] = original_evidence_name
        attachment_payload["primary_assets"][0]["logical_name"] = original_evidence_name
        evidence_attachment_path.write_text(
            json.dumps(attachment_payload), encoding="utf-8"
        )

        attestation_payload = json.loads(attestation_path.read_text(encoding="utf-8"))
        canonical_name = attestation_payload["files"][0]["evidence_filename"]
        alternate_name = (
            "buildish-verification-evidence--alternate.publish-attestations.json"
        )
        attestation_payload["files"][0]["evidence_filename"] = alternate_name
        attestation_path.write_text(json.dumps(attestation_payload), encoding="utf-8")
        attachment_payload["primary_asset_names"][0] = alternate_name
        attachment_payload["primary_assets"][0]["logical_name"] = alternate_name
        evidence_attachment_path.write_text(
            json.dumps(attachment_payload), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "not canonical"):
            run_create_release_manifest(args)
        attestation_payload["files"][0]["evidence_filename"] = canonical_name
        attestation_path.write_text(json.dumps(attestation_payload), encoding="utf-8")
        attachment_payload["primary_asset_names"][0] = original_evidence_name
        attachment_payload["primary_assets"][0]["logical_name"] = original_evidence_name
        evidence_attachment_path.write_text(
            json.dumps(attachment_payload), encoding="utf-8"
        )

        args.secondary_publication_result = []
        args.secondary_verification_result = []
        with self.assertRaisesRegex(
            ValueError,
            "configured PyPI publication requires",
        ):
            run_create_release_manifest(args)
        args.secondary_publication_result = [str(pypi_path)]
        args.secondary_verification_result = [str(attestation_path)]

        parsed_manifest = ReleaseManifestV1.model_validate(manifest)
        altered_result = parsed_manifest.verification_results[0]
        altered_evidence_claims = dict(altered_result.claims)
        altered_evidence_claims["evidence_asset_name"] = "arbitrary.json"
        altered_name_manifest = parsed_manifest.model_copy(
            update={
                "verification_results": [
                    altered_result.model_copy(
                        update={
                            "claims": altered_evidence_claims,
                            "uri": (
                                "https://github.com/example/example/releases/download/"
                                "v1.2.3/arbitrary.json"
                            ),
                        }
                    ),
                    *parsed_manifest.verification_results[1:],
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "name is not canonical"):
            _validate_release_manifest(
                altered_name_manifest,
                promotion,
                GitHubFinalPublication.model_validate(
                    json.loads(publication_path.read_text(encoding="utf-8"))[
                        "publication"
                    ]
                ),
                load_release_config(str(config_path)),
                test_target_mode=True,
            )
        unknown_manifest = parsed_manifest.model_copy(
            update={
                "secondary_publications": [
                    *parsed_manifest.secondary_publications,
                    PublicationReference(
                        target_kind="unregistered-registry",
                        uri="https://registry.example.invalid/project/1.2.3",
                        immutable_id="project==1.2.3",
                    ),
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "unsupported or ambiguously owned"):
            _validate_release_manifest(
                unknown_manifest,
                promotion,
                GitHubFinalPublication.model_validate(
                    json.loads(publication_path.read_text(encoding="utf-8"))[
                        "publication"
                    ]
                ),
                load_release_config(str(config_path)),
                test_target_mode=True,
            )

        altered_uri = parsed_manifest.model_copy(
            update={
                "secondary_publications": [
                    parsed_manifest.secondary_publications[0].model_copy(
                        update={"uri": "https://attacker.invalid/project/1.2.3"}
                    )
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "PyPI publication"):
            _validate_release_manifest(
                altered_uri,
                promotion,
                GitHubFinalPublication.model_validate(
                    json.loads(publication_path.read_text(encoding="utf-8"))[
                        "publication"
                    ]
                ),
                load_release_config(str(config_path)),
                test_target_mode=False,
            )

        altered_claims = parsed_manifest.model_copy(deep=True)
        altered_claims.verification_results[0].claims["publisher_repository"] = (
            "attacker/project"
        )
        with self.assertRaisesRegex(ValueError, "publisher is invalid"):
            _validate_release_manifest(
                altered_claims,
                promotion,
                GitHubFinalPublication.model_validate(
                    json.loads(publication_path.read_text(encoding="utf-8"))[
                        "publication"
                    ]
                ),
                load_release_config(str(config_path)),
                test_target_mode=True,
            )

        pypi_payload = json.loads(pypi_path.read_text(encoding="utf-8"))
        pypi_payload["published_files"][0]["digests"]["sha256"] = "d" * 64
        pypi_path.write_text(json.dumps(pypi_payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from final-release artifact"):
            run_create_release_manifest(args)

        pypi_payload["published_files"][0]["digests"]["sha256"] = "a" * 64
        pypi_path.write_text(json.dumps(pypi_payload), encoding="utf-8")
        attestation_payload = json.loads(attestation_path.read_text(encoding="utf-8"))
        attestation_payload["files"][0]["distribution_sha256"] = "f" * 64
        attestation_path.write_text(json.dumps(attestation_payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from PyPI publication"):
            run_create_release_manifest(args)
