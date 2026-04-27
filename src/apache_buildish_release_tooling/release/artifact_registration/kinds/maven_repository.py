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

"""Handler for the `maven-repository` artifact-registration kind."""

from __future__ import annotations

import hashlib
import io
import re
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait
from argparse import Namespace
from dataclasses import dataclass
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlparse

import urllib3

from apache_buildish_release_tooling.release.artifact_registration.common import (
    apply_common_artifact_metadata,
)
from apache_buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)
from apache_buildish_release_tooling.release.manifest import write_manifest
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.source_artifact import sha512

_SHA512_PATTERN = re.compile(r"^[0-9a-fA-F]{128}$")
_DEFAULT_INVENTORY_WORKERS = 16
_DEFAULT_NEXUS_STAGING_BASE_URL_PREFIX = "https://repository.apache.org/content/repositories/"


@dataclass(frozen=True)
class _RepositoryFile:
    relative_path: str
    size_bytes: int
    source_url: str | None = None
    local_path: Path | None = None


@dataclass(frozen=True)
class _NexusIndexEntry:
    href: str
    name: str
    size_bytes: int | None
    is_directory: bool


@dataclass(frozen=True)
class _RemoteHttpClient:
    pool_manager: urllib3.PoolManager

    @classmethod
    def for_worker_count(cls, worker_count: int) -> _RemoteHttpClient:
        return cls(
            pool_manager=urllib3.PoolManager(
                maxsize=worker_count,
                block=True,
            )
        )

    def close(self) -> None:
        self.pool_manager.clear()

    def read_text(self, url: str) -> str:
        return self.read_bytes(url).decode("utf-8")

    def read_bytes(self, url: str) -> bytes:
        response = self.pool_manager.request("GET", url, preload_content=True)
        try:
            payload = response.data
            if response.status < 200 or response.status >= 300:
                raise HTTPError(
                    url,
                    response.status,
                    "unexpected HTTP response",
                    _http_error_headers(response.headers),
                    io.BytesIO(payload),
                )
            return payload
        finally:
            response.release_conn()


def _http_error_headers(headers: Any) -> Message[str, str]:
    message: Message[str, str] = Message()
    for name, value in headers.items():
        message[name] = value
    return message


class _NexusIndexParser(HTMLParser):
    """Parse one Sonatype Nexus directory index page."""

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[_NexusIndexEntry] = []
        self._inside_td = False
        self._current_cell_text: list[str] = []
        self._current_cells: list[str] = []
        self._current_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_cells = []
            self._current_href = None
            return
        if tag == "td":
            self._inside_td = True
            self._current_cell_text = []
            return
        if tag == "a" and self._inside_td and self._current_href is None:
            attributes = dict(attrs)
            href = attributes.get("href")
            if href is not None:
                self._current_href = href

    def handle_data(self, data: str) -> None:
        if self._inside_td:
            self._current_cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            normalized = "".join(self._current_cell_text).strip()
            self._current_cells.append(normalized)
            self._inside_td = False
            self._current_cell_text = []
            return
        if tag == "tr":
            self._finish_row()

    def _finish_row(self) -> None:
        if self._current_href is None or not self._current_cells:
            return
        if self._current_href == "../" or self._current_cells[0] == "Parent Directory":
            return
        size_bytes: int | None = None
        if len(self._current_cells) >= 3 and self._current_cells[2].isdigit():
            size_bytes = int(self._current_cells[2])
        name = self._current_cells[0]
        self.entries.append(
            _NexusIndexEntry(
                href=self._current_href,
                name=name,
                size_bytes=size_bytes,
                is_directory=name.endswith("/") or self._current_href.endswith("/"),
            )
        )


def _default_nexus_staging_base_url(staging_repository_id: str) -> str:
    return f"{_DEFAULT_NEXUS_STAGING_BASE_URL_PREFIX}{staging_repository_id}/"


def _normalized_base_url(base_url_text: str | None, *, staging_repository_id: str) -> str:
    if base_url_text is None or not base_url_text.strip():
        normalized = _default_nexus_staging_base_url(staging_repository_id)
    else:
        normalized = base_url_text.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"file", "http", "https"}:
        raise ValueError("maven-repository --base-url must use file://, http://, or https://")
    if not normalized.endswith("/"):
        normalized = f"{normalized}/"
        parsed = urlparse(normalized)
    repository_name = Path(parsed.path.rstrip("/")).name
    if not repository_name:
        raise ValueError(f"maven-repository base URL must end in the staging repository directory: {normalized}")
    return normalized


def _staging_repository_id(raw_value: str | None) -> str:
    if raw_value is None:
        raise ValueError("maven-repository requires --staging-repository-id")
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError("maven-repository requires --staging-repository-id")
    if "/" in normalized:
        raise ValueError("maven-repository --staging-repository-id must not contain slashes")
    return normalized


def _validated_repository_root(base_url: str, staging_repository_id: str) -> None:
    repository_name = Path(urlparse(base_url).path.rstrip("/")).name
    if repository_name != staging_repository_id:
        raise ValueError(
            "maven-repository --base-url must end in the same repository directory as "
            f"--staging-repository-id: {base_url}"
        )


def _inventory_worker_count(raw_value: int | str | None) -> int:
    if raw_value is None:
        return _DEFAULT_INVENTORY_WORKERS
    worker_count = int(raw_value)
    if worker_count < 1:
        raise ValueError("maven-repository --inventory-workers must be at least 1")
    return worker_count


def _normalized_inventory_filename(artifact_id: str) -> str:
    return f"{artifact_id}-inventory.json"


def _read_remote_text(url: str, *, remote_http_client: _RemoteHttpClient) -> str:
    return remote_http_client.read_text(url)


def _read_remote_bytes(url: str, *, remote_http_client: _RemoteHttpClient) -> bytes:
    return remote_http_client.read_bytes(url)


def _parse_nexus_index(listing_url: str, base_url: str, html_text: str) -> list[_NexusIndexEntry]:
    parser = _NexusIndexParser()
    parser.feed(html_text)
    entries: list[_NexusIndexEntry] = []
    base_path = urlparse(base_url).path
    for entry in parser.entries:
        resolved_url = urljoin(listing_url, entry.href)
        resolved_path = unquote(urlparse(resolved_url).path)
        if not resolved_path.startswith(base_path):
            raise ValueError(f"maven-repository listing escaped the repository root: {resolved_url}")
        entries.append(
            _NexusIndexEntry(
                href=resolved_url,
                name=entry.name,
                size_bytes=entry.size_bytes,
                is_directory=entry.is_directory,
            )
        )
    return entries


def _relative_path_from_url(base_url: str, entry_url: str) -> str:
    base_path = urlparse(base_url).path
    resolved_path = unquote(urlparse(entry_url).path)
    if not resolved_path.startswith(base_path):
        raise ValueError(f"maven-repository entry is outside the repository root: {entry_url}")
    return resolved_path.removeprefix(base_path)


def _fetch_remote_listing(
    directory_url: str,
    base_url: str,
    *,
    remote_http_client: _RemoteHttpClient,
) -> tuple[str, list[_NexusIndexEntry]]:
    listing_html = _read_remote_text(directory_url, remote_http_client=remote_http_client)
    return directory_url, _parse_nexus_index(directory_url, base_url, listing_html)


def _enumerate_remote_repository(
    base_url: str,
    *,
    worker_count: int,
    remote_http_client: _RemoteHttpClient,
    progress_reporter: ProgressReporter,
) -> list[_RepositoryFile]:
    seen_directories: set[str] = set()
    files: list[_RepositoryFile] = []

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        pending_futures: dict[Future[tuple[str, list[_NexusIndexEntry]]], str] = {}

        def submit_directory(directory_url: str) -> None:
            directory_relative = _relative_path_from_url(base_url, directory_url)
            if directory_relative in seen_directories:
                return
            seen_directories.add(directory_relative)
            future = executor.submit(
                _fetch_remote_listing,
                directory_url,
                base_url,
                remote_http_client=remote_http_client,
            )
            pending_futures[future] = directory_url

        submit_directory(base_url)
        while pending_futures:
            completed, _ = wait(tuple(pending_futures.keys()), return_when=FIRST_COMPLETED)
            for future in completed:
                pending_futures.pop(future)
                _directory_url, entries = future.result()
                for entry in entries:
                    relative_path = _relative_path_from_url(base_url, entry.href)
                    if entry.is_directory:
                        submit_directory(entry.href)
                        continue
                    if entry.size_bytes is None:
                        raise ValueError(f"maven-repository listing omitted the file size for {entry.href}")
                    files.append(
                        _RepositoryFile(
                            relative_path=relative_path,
                            size_bytes=entry.size_bytes,
                            source_url=entry.href,
                        )
                    )
                    progress_reporter.update(f"maven repository enumeration: {len(files)} files discovered")
    return sorted(files, key=lambda entry: entry.relative_path)


def _enumerate_local_repository(root_path: Path, *, progress_reporter: ProgressReporter) -> list[_RepositoryFile]:
    files: list[_RepositoryFile] = []
    for local_path in sorted(root_path.rglob("*")):
        if not local_path.is_file():
            continue
        files.append(
            _RepositoryFile(
                relative_path=local_path.relative_to(root_path).as_posix(),
                size_bytes=local_path.stat().st_size,
                local_path=local_path,
            )
        )
        progress_reporter.update(f"maven repository enumeration: {len(files)} files discovered")
    return files


def _repository_files(
    base_url: str,
    *,
    worker_count: int,
    remote_http_client: _RemoteHttpClient | None,
    progress_reporter: ProgressReporter,
) -> list[_RepositoryFile]:
    parsed = urlparse(base_url)
    if parsed.scheme == "file":
        root_path = Path(unquote(parsed.path))
        if not root_path.is_dir():
            raise ValueError(f"maven-repository base URL does not point at a directory: {base_url}")
        return _enumerate_local_repository(root_path, progress_reporter=progress_reporter)
    if remote_http_client is None:
        raise ValueError(f"remote repository enumeration requires an HTTP client: {base_url}")
    return _enumerate_remote_repository(
        base_url,
        worker_count=worker_count,
        remote_http_client=remote_http_client,
        progress_reporter=progress_reporter,
    )


def _planned_remote_fetches(
    repository_files: list[_RepositoryFile],
    *,
    files_by_relative_path: dict[str, _RepositoryFile],
) -> dict[str, _RepositoryFile]:
    planned_fetches: dict[str, _RepositoryFile] = {}
    for repository_file in repository_files:
        if repository_file.source_url is None:
            continue
        if repository_file.relative_path.endswith(".sha512"):
            planned_fetches[repository_file.relative_path] = repository_file
            continue
        sidecar_relative_path = f"{repository_file.relative_path}.sha512"
        if sidecar_relative_path in files_by_relative_path:
            continue
        planned_fetches[repository_file.relative_path] = repository_file
    return planned_fetches


def _fetch_remote_repository_file(
    repository_file: _RepositoryFile,
    *,
    remote_http_client: _RemoteHttpClient,
) -> tuple[str, bytes]:
    if repository_file.source_url is None:
        raise ValueError(f"repository file has no remote source URL: {repository_file.relative_path}")
    return repository_file.relative_path, _read_remote_bytes(
        repository_file.source_url,
        remote_http_client=remote_http_client,
    )


def _prefetched_remote_bytes(
    repository_files: list[_RepositoryFile],
    *,
    files_by_relative_path: dict[str, _RepositoryFile],
    worker_count: int,
    remote_http_client: _RemoteHttpClient | None,
    progress_reporter: ProgressReporter,
) -> dict[str, bytes]:
    planned_fetches = _planned_remote_fetches(
        repository_files,
        files_by_relative_path=files_by_relative_path,
    )
    if not planned_fetches:
        return {}
    if remote_http_client is None:
        raise ValueError("remote repository prefetch requires an HTTP client")
    progress_reporter.emit(f"prefetching maven repository files: 0/{len(planned_fetches)} completed")
    payloads: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_path = {
            executor.submit(
                _fetch_remote_repository_file,
                repository_file,
                remote_http_client=remote_http_client,
            ): relative_path
            for relative_path, repository_file in planned_fetches.items()
        }
        for future in as_completed(future_to_path):
            relative_path, payload = future.result()
            payloads[relative_path] = payload
            progress_reporter.update(
                f"prefetching maven repository files: {len(payloads)}/{len(planned_fetches)} completed"
            )
    return payloads


def _repository_file_bytes(
    repository_file: _RepositoryFile,
    *,
    cache: dict[str, bytes],
    remote_http_client: _RemoteHttpClient | None,
) -> bytes:
    cached = cache.get(repository_file.relative_path)
    if cached is not None:
        return cached
    if repository_file.local_path is not None:
        payload = repository_file.local_path.read_bytes()
    elif repository_file.source_url is not None:
        if remote_http_client is None:
            raise ValueError(f"remote repository file requires an HTTP client: {repository_file.relative_path}")
        payload = _read_remote_bytes(
            repository_file.source_url,
            remote_http_client=remote_http_client,
        )
    else:
        raise ValueError(f"repository file has no readable source: {repository_file.relative_path}")
    cache[repository_file.relative_path] = payload
    return payload


def _parsed_sidecar_sha512(sidecar_bytes: bytes, *, relative_path: str) -> str:
    first_token = sidecar_bytes.decode("utf-8").strip().split()[0]
    normalized = first_token.lower()
    if not _SHA512_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid SHA512 sidecar for {relative_path}")
    return normalized


def _inventory_entry_sha512(
    repository_file: _RepositoryFile,
    *,
    files_by_relative_path: dict[str, _RepositoryFile],
    cache: dict[str, bytes],
    remote_http_client: _RemoteHttpClient | None,
) -> str:
    sidecar_relative_path = f"{repository_file.relative_path}.sha512"
    if not repository_file.relative_path.endswith(".sha512"):
        sidecar_file = files_by_relative_path.get(sidecar_relative_path)
        if sidecar_file is not None:
            return _parsed_sidecar_sha512(
                _repository_file_bytes(
                    sidecar_file,
                    cache=cache,
                    remote_http_client=remote_http_client,
                ),
                relative_path=sidecar_relative_path,
            )
    payload = _repository_file_bytes(
        repository_file,
        cache=cache,
        remote_http_client=remote_http_client,
    )
    return hashlib.sha512(payload).hexdigest()


def _inventory_payload(
    *,
    artifact_id: str,
    staging_repository_id: str,
    base_url: str,
    repository_files: list[_RepositoryFile],
    worker_count: int,
    remote_http_client: _RemoteHttpClient | None,
    progress_reporter: ProgressReporter,
) -> tuple[dict[str, Any], int]:
    files_by_relative_path = {entry.relative_path: entry for entry in repository_files}
    cache = _prefetched_remote_bytes(
        repository_files,
        files_by_relative_path=files_by_relative_path,
        worker_count=worker_count,
        remote_http_client=remote_http_client,
        progress_reporter=progress_reporter,
    )
    progress_reporter.emit(f"building maven repository inventory: 0/{len(repository_files)} entries")
    entries: list[dict[str, Any]] = []
    total_size_bytes = 0
    for repository_file in repository_files:
        total_size_bytes += repository_file.size_bytes
        entries.append(
            {
                "path": repository_file.relative_path,
                "size_bytes": repository_file.size_bytes,
                "sha512": _inventory_entry_sha512(
                    repository_file,
                    files_by_relative_path=files_by_relative_path,
                    cache=cache,
                    remote_http_client=remote_http_client,
                ),
            }
        )
        progress_reporter.update(
            f"building maven repository inventory: {len(entries)}/{len(repository_files)} entries"
        )
    return (
        {
            "schema_version": "1",
            "inventory_type": "maven-repository",
            "artifact_id": artifact_id,
            "staging_repository_id": staging_repository_id,
            "base_url": base_url,
            "entries": entries,
        },
        total_size_bytes,
    )


def build_maven_repository_registration(
    args: Namespace,
    bundle_dir: Path,
) -> ArtifactRegistrationResult:
    """Build one typed secondary-artifact fragment for the `maven-repository` kind."""

    staging_repository_id = _staging_repository_id(getattr(args, "staging_repository_id", None))
    base_url = _normalized_base_url(
        getattr(args, "base_url", None),
        staging_repository_id=staging_repository_id,
    )
    worker_count = _inventory_worker_count(getattr(args, "inventory_workers", None))
    progress_reporter = ProgressReporter.from_mode(getattr(args, "progress", "auto"))
    _validated_repository_root(base_url, staging_repository_id)
    remote_http_client: _RemoteHttpClient | None = None
    if urlparse(base_url).scheme in {"http", "https"}:
        remote_http_client = _RemoteHttpClient.for_worker_count(worker_count)
    try:
        progress_reporter.emit(f"enumerating maven repository from {base_url}")
        repository_files = _repository_files(
            base_url,
            worker_count=worker_count,
            remote_http_client=remote_http_client,
            progress_reporter=progress_reporter,
        )
        if not repository_files:
            raise ValueError(f"maven-repository is empty: {base_url}")
        inventory_payload, total_size_bytes = _inventory_payload(
            artifact_id=args.artifact_id,
            staging_repository_id=staging_repository_id,
            base_url=base_url,
            repository_files=repository_files,
            worker_count=worker_count,
            remote_http_client=remote_http_client,
            progress_reporter=progress_reporter,
        )
    finally:
        if remote_http_client is not None:
            remote_http_client.close()
    inventory_filename = _normalized_inventory_filename(args.artifact_id)
    inventory_path = bundle_dir / inventory_filename
    write_manifest(inventory_path, inventory_payload)
    inventory_sha512 = sha512(inventory_path)
    artifact: dict[str, Any] = {
        "artifact_id": args.artifact_id,
        "kind": "maven-repository",
        "staging_repository_id": staging_repository_id,
        "base_url": base_url,
        "inventory": {
            "filename": inventory_filename,
            "sha512": inventory_sha512,
            "entry_count": len(repository_files),
            "total_size_bytes": total_size_bytes,
        },
    }
    apply_common_artifact_metadata(artifact, args)
    progress_reporter.emit(
        f"wrote maven repository inventory: {len(repository_files)} entries, {total_size_bytes} bytes"
    )
    return ArtifactRegistrationResult(
        secondary_artifact=artifact,
        inventory_paths=(inventory_path,),
    )
