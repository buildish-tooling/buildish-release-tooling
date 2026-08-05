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

"""Download and cryptographically verify PyPI PEP 740 provenance."""

from __future__ import annotations

import multiprocessing
import time
from argparse import Namespace
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from urllib3 import Timeout
from urllib3.exceptions import HTTPError as Urllib3HTTPError

try:
    from pypi_attestations import (
        AttestationError,
        AttestationType,
        Distribution,
        GitHubPublisher,
        Provenance,
    )
except ImportError:  # pragma: no cover - exercised by installations without the extra
    AttestationError = None  # type: ignore[assignment,misc]
    AttestationType = None  # type: ignore[assignment,misc]
    Distribution = None  # type: ignore[assignment,misc]
    GitHubPublisher = None  # type: ignore[assignment,misc]
    Provenance = None  # type: ignore[assignment,misc]

from buildish_release_tooling.release.core.naming import require_semantic_version
from buildish_release_tooling.release.publications.pypi.config import (
    PyPiPublicationConfig,
)
from buildish_release_tooling.release.publications.pypi.distributions import (
    is_project_distribution,
    normalized_pypi_version,
    pypi_publish_attestation_asset_name,
)
from buildish_release_tooling.release.publications.pypi.manifests import (
    PyPiAttestationFileEvidence,
    PyPiAttestationPublisher,
    PyPiPublishAttestationEvidence,
    VerifyPyPiAttestationsManifest,
)
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.shared.downloader import DownloadSession
from buildish_release_tooling.shared.io import hash_file

_MAX_PROVENANCE_BYTES = 8 * 1024 * 1024
_PROVENANCE_TIMEOUT = Timeout(connect=10.0, read=30.0)
_PYPI_INTEGRITY_ACCEPT = "application/vnd.pypi.integrity.v1+json"
_RETRYABLE_HTTP_STATUSES = frozenset({404, 408, 429, *range(500, 600)})
_VERIFICATION_PROCESS_START_METHOD = "spawn"


class _RetryableProvenanceError(RuntimeError):
    """One transient provenance read governed by the command polling budget."""


def _verified_publish_attestations(
    provenance_bytes: bytes,
    distribution_path: Path,
    config: PyPiPublicationConfig,
) -> list[dict[str, object]]:
    if Provenance is None or GitHubPublisher is None or Distribution is None:
        raise RuntimeError(
            "PyPI attestation verification requires the 'pypi' optional dependency"
        )
    expected_publisher = GitHubPublisher(
        repository=config.trusted_publisher.repository,
        workflow=config.trusted_publisher.workflow,
        environment=config.trusted_publisher.environment,
    )
    try:
        provenance = Provenance.model_validate_json(provenance_bytes)
        distribution = Distribution.from_file(distribution_path)
    except (ValueError, AttestationError) as exc:
        raise ValueError("PyPI provenance or distribution is invalid") from exc
    matching_bundles = [
        bundle
        for bundle in provenance.attestation_bundles
        if bundle.publisher == expected_publisher
    ]
    if not matching_bundles:
        raise ValueError("PyPI provenance has no bundle from the expected publisher")
    selected: list[dict[str, object]] = []
    for bundle in matching_bundles:
        for attestation in bundle.attestations:
            try:
                predicate_type, _predicate = attestation.verify(
                    identity=expected_publisher,
                    dist=distribution,
                )
            except AttestationError as exc:
                raise ValueError(
                    "PyPI attestation from the expected publisher is invalid"
                ) from exc
            if predicate_type == AttestationType.PYPI_PUBLISH_V1.value:
                selected.append(attestation.model_dump(mode="json"))
    if not selected:
        raise ValueError(
            "PyPI provenance has no verified PyPI Publish Attestation from the expected publisher"
        )
    return selected


def _verify_attestations_worker(
    connection: Connection,
    provenance_bytes: bytes,
    distribution_path: str,
    config_payload: dict[str, Any],
) -> None:
    """Run online Sigstore verification behind a killable process boundary."""

    try:
        selected = _verified_publish_attestations(
            provenance_bytes,
            Path(distribution_path),
            PyPiPublicationConfig.model_validate(config_payload),
        )
        connection.send({"status": "ok", "attestations": selected})
    except Exception as exc:
        connection.send(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
    finally:
        connection.close()


def _terminate_verification_process(process: multiprocessing.Process) -> None:
    if not process.is_alive():
        process.join()
        return
    process.terminate()
    process.join(timeout=0.1)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.1)


def _verified_publish_attestations_with_deadline(
    provenance_bytes: bytes,
    distribution_path: Path,
    config: PyPiPublicationConfig,
    *,
    deadline_monotonic: float,
) -> list[dict[str, object]]:
    """Verify attestations without allowing online verification to exceed the deadline."""

    remaining = deadline_monotonic - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("PyPI attestation verification exceeded its total timeout")
    context = multiprocessing.get_context(_VERIFICATION_PROCESS_START_METHOD)
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(  # type: ignore[attr-defined]
        target=_verify_attestations_worker,
        args=(
            send_connection,
            provenance_bytes,
            str(distribution_path),
            config.model_dump(mode="json"),
        ),
    )
    process.start()
    send_connection.close()
    try:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0 or not receive_connection.poll(remaining):
            _terminate_verification_process(process)
            raise RuntimeError(
                "PyPI attestation verification exceeded its total timeout"
            )
        try:
            payload = receive_connection.recv()
        except EOFError as exc:
            _terminate_verification_process(process)
            raise RuntimeError(
                "PyPI attestation verification worker exited without a result"
            ) from exc
        process.join(timeout=max(0.0, deadline_monotonic - time.monotonic()))
        if process.is_alive():
            _terminate_verification_process(process)
            raise RuntimeError(
                "PyPI attestation verification exceeded its total timeout"
            )
        if not isinstance(payload, dict) or payload.get("status") not in {
            "ok",
            "error",
        }:
            raise RuntimeError(
                "PyPI attestation verification worker returned invalid data"
            )
        if payload["status"] == "error":
            message = payload.get("message")
            error_type = payload.get("error_type")
            if not isinstance(message, str) or not isinstance(error_type, str):
                raise RuntimeError(
                    "PyPI attestation verification worker returned invalid error data"
                )
            if error_type == "ValueError":
                raise ValueError(message)
            raise RuntimeError(message)
        selected = payload.get("attestations")
        if not isinstance(selected, list) or any(
            not isinstance(attestation, dict) for attestation in selected
        ):
            raise RuntimeError(
                "PyPI attestation verification worker returned invalid attestations"
            )
        return selected
    finally:
        receive_connection.close()
        if process.is_alive():
            _terminate_verification_process(process)


def _read_provenance(
    session: DownloadSession,
    url: str,
    *,
    deadline_monotonic: float,
) -> bytes:
    try:
        return session.read_bytes(
            url,
            max_bytes=_MAX_PROVENANCE_BYTES,
            deadline_monotonic=deadline_monotonic,
            headers={"Accept": _PYPI_INTEGRITY_ACCEPT},
        )
    except HTTPError as exc:
        if exc.code in _RETRYABLE_HTTP_STATUSES:
            raise _RetryableProvenanceError(
                f"PyPI provenance returned retryable HTTP {exc.code}"
            ) from exc
        raise RuntimeError(
            f"PyPI provenance request failed with HTTP {exc.code}"
        ) from exc
    except (FileNotFoundError, TimeoutError, Urllib3HTTPError) as exc:
        raise _RetryableProvenanceError(
            "transient PyPI provenance transport failure"
        ) from exc


def _download_with_retries(
    session: DownloadSession,
    url: str,
    *,
    attempts: int,
    retry_delay: float,
    deadline_monotonic: float,
) -> bytes:
    for attempt in range(attempts):
        if time.monotonic() >= deadline_monotonic:
            raise RuntimeError(
                "PyPI attestation verification exceeded its total timeout"
            )
        try:
            return _read_provenance(
                session,
                url,
                deadline_monotonic=deadline_monotonic,
            )
        except _RetryableProvenanceError as exc:
            if attempt + 1 >= attempts:
                raise RuntimeError(
                    "PyPI attestation verification exhausted its retry budget"
                ) from exc
            remaining = deadline_monotonic - time.monotonic()
            if remaining <= 0 or retry_delay >= remaining:
                raise RuntimeError(
                    "PyPI attestation verification exceeded its total timeout"
                ) from exc
            if retry_delay:
                time.sleep(retry_delay)
    raise AssertionError("unreachable PyPI attestation retry state")


def verify_pypi_attestations(
    args: Namespace,
    *,
    component_id: str,
    config: PyPiPublicationConfig,
) -> VerifyPyPiAttestationsManifest:
    """Verify configured publisher provenance for exact project distributions."""

    version = require_semantic_version(args.version)
    pypi_version = normalized_pypi_version(version)
    distributions = [
        Path(argument)
        for argument in args.distributions
        if is_project_distribution(
            Path(argument).name,
            project_name=config.project_name,
            version=version,
        )
    ]
    if not distributions or any(not path.is_file() for path in distributions):
        raise ValueError(
            "PyPI attestation verification requires existing project distributions"
        )
    if len({path.name for path in distributions}) != len(distributions):
        raise ValueError("PyPI attestation verification received duplicate filenames")
    if args.attempts < 1 or args.retry_delay < 0 or args.total_timeout <= 0:
        raise ValueError("invalid PyPI attestation polling limits")
    integrity_base_url = (args.integrity_api_url or config.integrity_api_url).rstrip(
        "/"
    )
    if (
        not args.test_target_mode
        and integrity_base_url != config.integrity_api_url.rstrip("/")
    ):
        raise ValueError("PyPI Integrity API override requires test-target mode")
    if not integrity_base_url.startswith("https://"):
        raise ValueError("PyPI Integrity API must use HTTPS")
    if Provenance is None:
        raise RuntimeError(
            "PyPI attestation verification requires the 'pypi' optional dependency"
        )
    provenance_dir = Path(args.provenance_dir)
    provenance_dir.mkdir(parents=True, exist_ok=True)
    deadline_monotonic = time.monotonic() + args.total_timeout
    evidence: list[PyPiAttestationFileEvidence] = []
    publisher = PyPiAttestationPublisher(
        kind=config.trusted_publisher.kind,
        repository=config.trusted_publisher.repository,
        workflow=config.trusted_publisher.workflow,
        environment=config.trusted_publisher.environment,
    )
    session_factory = (
        DownloadSession.harness if args.test_target_mode else DownloadSession.production
    )
    with session_factory(timeout=_PROVENANCE_TIMEOUT) as session:
        for distribution in sorted(distributions, key=lambda path: path.name):
            provenance_url = (
                f"{integrity_base_url}/{config.project_name}/{pypi_version}/"
                f"{distribution.name}/provenance"
            )
            provenance_bytes = _download_with_retries(
                session,
                provenance_url,
                attempts=args.attempts,
                retry_delay=args.retry_delay,
                deadline_monotonic=deadline_monotonic,
            )
            provenance_path = provenance_dir / f"{distribution.name}.provenance.json"
            provenance_path.write_bytes(provenance_bytes)
            publish_attestations = _verified_publish_attestations_with_deadline(
                provenance_bytes,
                distribution,
                config,
                deadline_monotonic=deadline_monotonic,
            )
            evidence_path = provenance_dir / pypi_publish_attestation_asset_name(
                distribution.name
            )
            write_manifest(
                evidence_path,
                PyPiPublishAttestationEvidence(
                    publisher=publisher,
                    distribution_filename=distribution.name,
                    distribution_sha256=hash_file(distribution, algorithm="sha256"),
                    source_provenance_url=provenance_url,
                    attestations=publish_attestations,
                ),
            )
            if time.monotonic() >= deadline_monotonic:
                raise RuntimeError(
                    "PyPI attestation verification exceeded its total timeout"
                )
            evidence.append(
                PyPiAttestationFileEvidence(
                    filename=distribution.name,
                    distribution_sha256=hash_file(distribution, algorithm="sha256"),
                    evidence_filename=evidence_path.name,
                    evidence_sha256=hash_file(evidence_path, algorithm="sha256"),
                    evidence_size_bytes=evidence_path.stat().st_size,
                    source_provenance_url=provenance_url,
                    publish_attestation_count=len(publish_attestations),
                )
            )
    return VerifyPyPiAttestationsManifest(
        component=component_id,
        project_name=config.project_name,
        version=version,
        integrity_base_url=integrity_base_url,
        publisher=publisher,
        files=evidence,
    )
