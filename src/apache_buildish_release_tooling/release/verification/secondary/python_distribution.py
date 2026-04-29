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

"""Python distribution secondary-artifact verification."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.common import (
    validate_fetch_uri,
    verify_checksum_sidecar,
)

from .shared import required_checksum_payload, required_non_empty_string, url_without_fragment


class _SimpleIndexHtmlParser(HTMLParser):
    """Collect file links from one HTML simple-index project page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        self.links.append({"href": href})


def verify_python_distribution(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    allow_non_production_release_targets: bool,
) -> dict[str, Any]:
    artifact_id = required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    filename = required_non_empty_string(artifact_entry, "filename", source=manifest_url)
    artifact_uri = required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    index_url = required_non_empty_string(artifact_entry, "index_url", source=manifest_url)
    project_name = required_non_empty_string(artifact_entry, "project_name", source=manifest_url)
    version = required_non_empty_string(artifact_entry, "version", source=manifest_url)
    issues: list[str] = []
    if version not in filename:
        issues.append(
            "python-distribution filename does not contain the declared version: "
            f"{filename} vs {version}"
        )
    authenticity = artifact_entry.get("authenticity")
    if authenticity is not None:
        try:
            scheme = required_non_empty_string(authenticity, "scheme", source=manifest_url)
            if scheme != "pypi-attestation":
                raise ValueError(f"unsupported python-distribution authenticity scheme: {scheme}")
            raise ValueError(
                "python-distribution pypi-attestation verification is not implemented; omit authenticity metadata for now"
            )
        except Exception as exc:
            issues.append(str(exc))

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path: Path | None = None
    try:
        validate_fetch_uri(
            artifact_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"python distribution URL for {artifact_id}",
        )
        downloaded_artifact_path = work_dir / filename
        downloaded_artifact_path.write_bytes(read_uri_bytes(artifact_uri))
        artifact_path = downloaded_artifact_path
    except Exception as exc:
        issues.append(str(exc))

    checksum_algorithm: str | None = None
    checksum_value: str | None = None
    checksum_uri: str | None = None
    actual_checksum: str | None = None
    checksum_matches_manifest = False
    try:
        checksum_algorithm, checksum_value, checksum_uri = required_checksum_payload(
            artifact_entry,
            source=manifest_url,
            algorithms=("sha256",),
        )
    except Exception as exc:
        issues.append(str(exc))

    if artifact_path is not None and checksum_algorithm is not None and checksum_value is not None:
        actual_checksum = checksum(artifact_path, checksum_algorithm)
        if actual_checksum != checksum_value:
            issues.append(
                "python-distribution checksum does not match the signed manifest: "
                f"{artifact_id} {actual_checksum} != {checksum_value}"
            )
        else:
            checksum_matches_manifest = True

    checksum_sidecar_verified = False
    if artifact_path is not None and checksum_uri is not None and checksum_algorithm is not None:
        try:
            validate_fetch_uri(
                checksum_uri,
                allow_non_production_release_targets=allow_non_production_release_targets,
                purpose=f"python distribution checksum sidecar URL for {artifact_id}",
            )
            sidecar_path = work_dir / f"{filename}.{checksum_algorithm}"
            sidecar_path.write_bytes(read_uri_bytes(checksum_uri))
            verify_checksum_sidecar(
                artifact_path,
                sidecar_path,
                algorithm=checksum_algorithm,
                purpose=f"python distribution {artifact_id}",
            )
            checksum_sidecar_verified = True
        except Exception as exc:
            issues.append(str(exc))

    project_index_url = _simple_index_project_url(index_url, project_name)
    resolved_url: str | None = None
    found_via: str | None = None
    sha256_matches_index: bool | None = None
    try:
        validate_fetch_uri(
            project_index_url,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"python simple index URL for {artifact_id}",
        )
        project_index_entries = _simple_index_entries(project_index_url)
        matching_entry = next(
            (candidate for candidate in project_index_entries if candidate["filename"] == filename),
            None,
        )
        if matching_entry is None:
            raise ValueError(
                "python-distribution file is not present in the declared simple index: "
                f"{project_index_url} -> {filename}"
            )
        resolved_url = url_without_fragment(matching_entry["url"])
        found_via = matching_entry["source"]
        if resolved_url != url_without_fragment(artifact_uri):
            issues.append(
                "python-distribution URI does not match the declared simple index entry: "
                f"{resolved_url} != {url_without_fragment(artifact_uri)}"
            )
        index_sha256 = matching_entry["hashes"].get("sha256")
        sha256_matches_index = index_sha256 is None or index_sha256 == checksum_value
        if (
            index_sha256 is not None
            and checksum_value is not None
            and index_sha256 != checksum_value
        ):
            issues.append(
                "python-distribution sha256 does not match the declared simple index entry: "
                f"{index_sha256} != {checksum_value}"
            )
    except Exception as exc:
        issues.append(str(exc))

    return {
        "artifact_id": artifact_id,
        "kind": "python-distribution",
        "verdict": "failed" if issues else "verified",
        "issues": issues,
        "filename": filename,
        "uri": artifact_uri,
        "index_url": index_url,
        "project_name": project_name,
        "version": version,
        "checksum": {
            "algorithm": checksum_algorithm,
            "value": actual_checksum,
            "matches_manifest": checksum_matches_manifest,
            "sidecar_verified": checksum_sidecar_verified,
        },
        "index_resolution": {
            "project_index_url": project_index_url,
            "resolved_url": resolved_url,
            "found_via": found_via,
            "sha256_matches_index": sha256_matches_index,
        },
    }


def _simple_index_project_url(index_url: str, project_name: str) -> str:
    normalized_project_name = _normalized_python_project_name(project_name)
    if index_url.endswith(".html") or index_url.endswith(".json"):
        return index_url
    return urljoin(index_url.rstrip("/") + "/", f"{normalized_project_name}/")


def _normalized_python_project_name(project_name: str) -> str:
    return re.sub(r"[-_.]+", "-", project_name).lower()


def _simple_index_entries(project_index_url: str) -> list[dict[str, Any]]:
    payload_bytes = _read_simple_index_bytes(project_index_url)
    stripped = payload_bytes.lstrip()
    if stripped.startswith(b"{"):
        return _simple_index_json_entries(project_index_url, payload_bytes)
    return _simple_index_html_entries(project_index_url, payload_bytes)


def _read_simple_index_bytes(project_index_url: str) -> bytes:
    parsed = urlparse(project_index_url)
    if parsed.scheme != "file":
        return read_uri_bytes(project_index_url)
    local_path = Path(unquote(parsed.path))
    if local_path.is_dir():
        for candidate_name in ("index.json", "index.html"):
            candidate_path = local_path / candidate_name
            if candidate_path.is_file():
                return candidate_path.read_bytes()
        raise ValueError(f"python-distribution simple index directory has no index file: {local_path}")
    return read_uri_bytes(project_index_url)


def _simple_index_json_entries(project_index_url: str, payload_bytes: bytes) -> list[dict[str, Any]]:
    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"python-distribution simple index JSON must be an object: {project_index_url}")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise ValueError(f"python-distribution simple index JSON must contain a files list: {project_index_url}")
    entries: list[dict[str, Any]] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        filename = raw_file.get("filename")
        file_url = raw_file.get("url")
        if not isinstance(filename, str) or not filename.strip():
            continue
        if not isinstance(file_url, str) or not file_url.strip():
            continue
        hashes = raw_file.get("hashes")
        entries.append(
            {
                "filename": filename.strip(),
                "url": urljoin(project_index_url, file_url.strip()),
                "hashes": dict(hashes) if isinstance(hashes, dict) else {},
                "source": "simple-json",
            }
        )
    return entries


def _simple_index_html_entries(project_index_url: str, payload_bytes: bytes) -> list[dict[str, Any]]:
    parser = _SimpleIndexHtmlParser()
    parser.feed(payload_bytes.decode("utf-8"))
    entries: list[dict[str, Any]] = []
    for link in parser.links:
        href = link["href"]
        resolved_url = urljoin(project_index_url, href)
        parsed_url = urlparse(resolved_url)
        filename = Path(parsed_url.path).name
        if not filename:
            continue
        entries.append(
            {
                "filename": filename,
                "url": resolved_url,
                "hashes": _hashes_from_fragment(parsed_url.fragment),
                "source": "simple-html",
            }
        )
    return entries


def _hashes_from_fragment(fragment: str) -> dict[str, str]:
    if "=" not in fragment:
        return {}
    algorithm, digest_value = fragment.split("=", 1)
    normalized_algorithm = algorithm.strip().lower()
    normalized_digest = digest_value.strip().lower()
    expected_lengths = {
        "sha256": 64,
        "sha512": 128,
    }
    if normalized_algorithm not in expected_lengths:
        return {}
    if len(normalized_digest) != expected_lengths[normalized_algorithm]:
        return {}
    if any(character not in "0123456789abcdef" for character in normalized_digest):
        return {}
    return {normalized_algorithm: normalized_digest}
