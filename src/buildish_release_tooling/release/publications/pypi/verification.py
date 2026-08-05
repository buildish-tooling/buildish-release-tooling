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

"""Verify exact distribution publication through the PyPI JSON API."""

from __future__ import annotations

import json
import re
import time
from argparse import Namespace
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError
from urllib.parse import quote

from urllib3 import Timeout
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from buildish_release_tooling.release.core.models import ArtifactReference
from buildish_release_tooling.release.core.naming import require_semantic_version
from buildish_release_tooling.release.core.state import (
    DirectReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.publications.pypi.manifests import (
    VerifyPyPiPublicationManifest,
)
from buildish_release_tooling.release.publications.pypi.config import (
    PyPiPublicationConfig,
)
from buildish_release_tooling.release.publications.pypi.distributions import (
    is_project_distribution,
    normalized_pypi_version,
)
from buildish_release_tooling.shared.downloader import DownloadSession
from buildish_release_tooling.shared.io import hash_file
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_json_object_file_bounded,
)

_MAX_PYPI_RESPONSE_BYTES = 4 * 1024 * 1024
_PYPI_TIMEOUT = Timeout(connect=10.0, read=30.0)
_DEFAULT_TOTAL_TIMEOUT_SECONDS = 300.0
_RETRYABLE_HTTP_STATUSES = frozenset({408, 429, *range(500, 600)})


class _RetryablePyPiRequestError(RuntimeError):
    """One transient PyPI request failure governed by the polling budget."""


def _load_release_state(
    path: Path,
) -> tuple[DirectReleaseState | PromotionState, str]:
    payload = read_json_object_file_bounded(
        path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    state: DirectReleaseState | PromotionState
    if "candidate_manifest_digest" in payload:
        state = PromotionState.model_validate(payload)
    else:
        state = DirectReleaseState.model_validate(payload)
    return state, hash_file(path, algorithm="sha256")


def _local_distribution_files(
    arguments: list[str], *, project_name: str, version: str
) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for argument in arguments:
        path = Path(argument)
        if not path.is_file():
            raise ValueError(f"Python distribution file does not exist: {path}")
        if not is_project_distribution(
            path.name,
            project_name=project_name,
            version=version,
        ):
            continue
        if path.name in files:
            raise ValueError(f"duplicate Python distribution filename: {path.name}")
        files[path.name] = path
    if not files:
        raise ValueError(
            "at least one distribution for the configured PyPI project and version is required"
        )
    return files


def _read_pypi_release(
    session: DownloadSession,
    url: str,
    *,
    deadline_monotonic: float | None = None,
) -> dict[str, object] | None:
    try:
        body = session.read_bytes(
            url,
            max_bytes=_MAX_PYPI_RESPONSE_BYTES,
            deadline_monotonic=deadline_monotonic,
        )
    except HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in _RETRYABLE_HTTP_STATUSES:
            raise _RetryablePyPiRequestError(
                f"PyPI request returned retryable HTTP {exc.code}"
            ) from exc
        raise RuntimeError(f"PyPI request failed with HTTP {exc.code}") from exc
    except FileNotFoundError:
        return None
    except (TimeoutError, Urllib3HTTPError) as exc:
        raise _RetryablePyPiRequestError("transient PyPI transport failure") from exc
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PyPI JSON API response is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("PyPI JSON API response must be a JSON object")
    return payload


def _wait_for_retry(*, deadline_monotonic: float, retry_delay: float) -> None:
    remaining = deadline_monotonic - time.monotonic()
    if remaining <= 0 or retry_delay >= remaining:
        raise RuntimeError("PyPI verification exceeded its total timeout")
    if retry_delay:
        time.sleep(retry_delay)


def _remote_files(payload: dict[str, object]) -> dict[str, tuple[str, int, str]]:
    urls = payload.get("urls")
    if not isinstance(urls, list):
        raise ValueError("PyPI JSON API response has no release file list")
    files: dict[str, tuple[str, int, str]] = {}
    for entry in urls:
        if not isinstance(entry, dict):
            raise ValueError("PyPI release file entry must be an object")
        filename = entry.get("filename")
        digests = entry.get("digests")
        size = entry.get("size")
        file_url = entry.get("url")
        if (
            not isinstance(filename, str)
            or not isinstance(digests, dict)
            or not isinstance(digests.get("sha256"), str)
            or not isinstance(size, int)
            or not isinstance(file_url, str)
        ):
            raise ValueError("PyPI release file metadata is incomplete")
        if filename in files:
            raise ValueError(f"duplicate PyPI release filename: {filename}")
        files[filename] = (digests["sha256"], size, file_url)
    return files


def _validate_release_identity(
    payload: dict[str, object],
    *,
    project_name: str,
    version: str,
) -> None:
    info = payload.get("info")
    if not isinstance(info, dict):
        raise ValueError("PyPI JSON API response has no project metadata")
    remote_name = info.get("name")
    remote_version = info.get("version")

    def normalize_name(value: str) -> str:
        return re.sub(r"[-_.]+", "-", value).lower()

    if not isinstance(remote_name, str) or normalize_name(
        remote_name
    ) != normalize_name(project_name):
        raise ValueError("PyPI project name does not match the requested project")
    if not isinstance(remote_version, str) or normalized_pypi_version(
        remote_version
    ) != normalized_pypi_version(version):
        raise ValueError("PyPI version does not match the requested version")


def verify_pypi_publication(
    args: Namespace, *, component_id: str, config: PyPiPublicationConfig
) -> VerifyPyPiPublicationManifest:
    """Prove that one PyPI project version contains the supplied distributions."""

    version = require_semantic_version(args.version)
    pypi_version = normalized_pypi_version(version)
    release_state, release_state_digest = _load_release_state(Path(args.release_state))
    if (
        release_state.release.component.id != component_id
        or release_state.release.version != version
    ):
        raise ValueError("release state does not match the requested PyPI publication")
    local_files = _local_distribution_files(
        args.distributions,
        project_name=config.project_name,
        version=version,
    )
    if args.attempts < 1:
        raise ValueError("PyPI verification attempts must be at least one")
    if args.retry_delay < 0:
        raise ValueError("PyPI verification retry delay must not be negative")
    total_timeout = float(
        getattr(args, "total_timeout", _DEFAULT_TOTAL_TIMEOUT_SECONDS)
    )
    if total_timeout <= 0:
        raise ValueError("PyPI verification total timeout must be positive")
    deadline_monotonic = time.monotonic() + total_timeout
    repository_api_url = (args.repository_api_url or config.repository_api_url).rstrip(
        "/"
    )
    project_url_template = args.project_url_template or config.project_url_template
    if not args.test_target_mode and (
        repository_api_url != config.repository_api_url.rstrip("/")
        or project_url_template != config.project_url_template
    ):
        raise ValueError("PyPI service URL overrides require test-target mode")
    if not repository_api_url.startswith("https://") and not (
        args.test_target_mode and repository_api_url.startswith("file://")
    ):
        raise ValueError(
            "PyPI repository API URL must use HTTPS; "
            "file:// is allowed only in test-target mode"
        )
    endpoint = (
        f"{repository_api_url}/{quote(config.project_name, safe='')}/"
        f"{quote(pypi_version, safe='')}/json"
    )

    payload: dict[str, object] | None = None
    remote_files: dict[str, tuple[str, int, str]] = {}
    session_factory = (
        DownloadSession.harness if args.test_target_mode else DownloadSession.production
    )
    with session_factory(timeout=_PYPI_TIMEOUT) as session:
        for attempt in range(args.attempts):
            if time.monotonic() >= deadline_monotonic:
                raise RuntimeError("PyPI verification exceeded its total timeout")
            try:
                payload = _read_pypi_release(
                    session,
                    endpoint,
                    deadline_monotonic=deadline_monotonic,
                )
            except _RetryablePyPiRequestError as exc:
                if attempt + 1 >= args.attempts:
                    raise RuntimeError(
                        "PyPI verification exhausted its transient-failure retry budget"
                    ) from exc
                _wait_for_retry(
                    deadline_monotonic=deadline_monotonic,
                    retry_delay=args.retry_delay,
                )
                continue
            if payload is not None:
                _validate_release_identity(
                    payload,
                    project_name=config.project_name,
                    version=version,
                )
                remote_files = _remote_files(payload)
            else:
                remote_files = {}
            missing = sorted(set(local_files) - set(remote_files))
            if not missing or args.allow_incomplete:
                break
            if attempt + 1 < args.attempts:
                _wait_for_retry(
                    deadline_monotonic=deadline_monotonic,
                    retry_delay=args.retry_delay,
                )
        else:
            raise ValueError(
                "PyPI release is missing expected files: " + ", ".join(missing)
            )

    unexpected = sorted(set(remote_files) - set(local_files))
    if unexpected:
        raise ValueError(
            "PyPI release contains unexpected files: " + ", ".join(unexpected)
        )

    published_files: list[ArtifactReference] = []
    for filename, path in sorted(local_files.items()):
        if filename not in remote_files:
            continue
        local_digest = hash_file(path, algorithm="sha256")
        remote_digest, remote_size, remote_url = remote_files[filename]
        if remote_digest != local_digest or remote_size != path.stat().st_size:
            raise ValueError(f"PyPI release file differs from candidate: {filename}")
        published_files.append(
            ArtifactReference(
                kind="python-distribution",
                logical_name=filename,
                digests={"sha256": local_digest},
                size_bytes=remote_size,
                locations=[remote_url],
            )
        )

    missing = sorted(set(local_files) - set(remote_files))
    publication_state: Literal["absent", "partial", "complete"] = (
        "absent" if not remote_files else "partial" if missing else "complete"
    )
    if not args.allow_incomplete and publication_state != "complete":
        raise ValueError(
            "PyPI release is missing expected files: " + ", ".join(missing)
        )

    project_url = project_url_template.format(
        project=quote(config.project_name, safe=""),
        version=quote(pypi_version, safe=""),
    )
    return VerifyPyPiPublicationManifest(
        component=component_id,
        project_name=config.project_name,
        version=version,
        repository_api_url=repository_api_url,
        project_url=project_url,
        lifecycle=(
            "candidate-promotion"
            if isinstance(release_state, PromotionState)
            else "direct"
        ),
        source_commit=release_state.source.commit_sha,
        release_state_sha256=release_state_digest,
        publication_state=publication_state,
        published_files=published_files,
    )
