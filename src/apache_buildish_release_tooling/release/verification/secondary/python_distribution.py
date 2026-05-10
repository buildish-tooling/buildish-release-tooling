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

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlparse

from pydantic import BaseModel, ConfigDict, Field

from apache_buildish_release_tooling.release.contracts import (
    ArtifactReproducibilityReport,
    ChecksumVerificationReport,
    PythonDistributionSecondaryArtifact,
    PythonDistributionVerificationReport,
    PythonIndexResolutionReport,
)
from apache_buildish_release_tooling.release.external_json import validate_json_object_model_text
from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from apache_buildish_release_tooling.release.path_validation import validate_simple_filename
from apache_buildish_release_tooling.release.rc_vote_manifest import download_uri_to_path, read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.common import (
    validate_fetch_uri,
    verify_checksum_sidecar,
)
from apache_buildish_release_tooling.shared.io import read_bytes_bounded

from .file_reproducibility import verify_host_direct_single_file_reproducibility
from .shared import url_without_fragment


@dataclass(frozen=True)
class _SimpleIndexEntry:
    """One stable simple-index file entry used by the verifier."""

    filename: str
    url: str
    hashes: dict[str, str] = field(default_factory=dict)
    source: str = "simple-html"


class _ExternalSimpleIndexReadModel(BaseModel):
    """Typed subset base for external Python simple-index payloads."""

    model_config = ConfigDict(extra="allow")


class _SimpleIndexJsonFileRead(_ExternalSimpleIndexReadModel):
    filename: str | None = Field(
        default=None,
        description="Distribution filename advertised by the JSON simple-index response.",
    )
    url: str | None = Field(
        default=None,
        description="Distribution download URL advertised by the JSON simple-index response.",
    )
    hashes: dict[str, str] | None = Field(
        default=None,
        description="Hash values advertised for one Python distribution file in the JSON simple-index response.",
    )


class _SimpleIndexJsonRead(_ExternalSimpleIndexReadModel):
    files: list[_SimpleIndexJsonFileRead] = Field(
        default_factory=list,
        description="Distribution-file entries advertised by the JSON simple-index response.",
    )


class _SimpleIndexHtmlParser(HTMLParser):
    """Collect file links from one HTML simple-index project page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def verify_python_distribution(
    artifact_entry: PythonDistributionSecondaryArtifact,
    *,
    manifest_url: str,
    work_dir: Path,
    allow_non_production_release_targets: bool,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    build_checks_allowed: bool,
    inspection_bundle_root: Path | None,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> PythonDistributionVerificationReport:
    artifact_id = artifact_entry.artifact_id
    filename = validate_simple_filename(
        artifact_entry.filename,
        field_name=f"python distribution filename for {artifact_id}",
    )
    artifact_uri = artifact_entry.uri
    index_url = artifact_entry.index_url
    project_name = artifact_entry.project_name
    version = artifact_entry.version
    issues: list[str] = []
    if version not in filename:
        issues.append(
            "python-distribution filename does not contain the declared version: "
            f"{filename} vs {version}"
        )
    authenticity = artifact_entry.authenticity
    if authenticity is not None:
        issues.append(
            "python-distribution pypi-attestation verification is not implemented; omit authenticity metadata for now"
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path: Path | None = None
    try:
        validate_fetch_uri(
            artifact_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"python distribution URL for {artifact_id}",
        )
        downloaded_artifact_path = work_dir / filename
        download_uri_to_path(artifact_uri, downloaded_artifact_path)
        artifact_path = downloaded_artifact_path
    except Exception as exc:
        issues.append(str(exc))

    checksum_algorithm: Literal["sha256"] = "sha256"
    checksum_value = artifact_entry.checksums.sha256.value
    checksum_uri = artifact_entry.checksums.sha256.uri
    actual_checksum: str | None = None
    checksum_matches_manifest = False
    if artifact_path is not None:
        actual_checksum = checksum(artifact_path, checksum_algorithm)
        if actual_checksum != checksum_value:
            issues.append(
                "python-distribution checksum does not match the signed manifest: "
                f"{artifact_id} {actual_checksum} != {checksum_value}"
            )
        else:
            checksum_matches_manifest = True

    checksum_sidecar_verified = False
    if artifact_path is not None and checksum_uri is not None:
        try:
            validate_fetch_uri(
                checksum_uri,
                allow_non_production_release_targets=allow_non_production_release_targets,
                purpose=f"python distribution checksum sidecar URL for {artifact_id}",
            )
            sidecar_path = work_dir / f"{filename}.{checksum_algorithm}"
            download_uri_to_path(checksum_uri, sidecar_path)
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
    reproducibility_verification: ArtifactReproducibilityReport | None = None
    try:
        validate_fetch_uri(
            project_index_url,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"python simple index URL for {artifact_id}",
        )
        project_index_entries = _simple_index_entries(project_index_url)
        matching_entry = next(
            (candidate for candidate in project_index_entries if candidate.filename == filename),
            None,
        )
        if matching_entry is None:
            raise ValueError(
                "python-distribution file is not present in the declared simple index: "
                f"{project_index_url} -> {filename}"
            )
        resolved_url = url_without_fragment(matching_entry.url)
        found_via = matching_entry.source
        if resolved_url != url_without_fragment(artifact_uri):
            issues.append(
                "python-distribution URI does not match the declared simple index entry: "
                f"{resolved_url} != {url_without_fragment(artifact_uri)}"
            )
        index_sha256 = matching_entry.hashes.get("sha256")
        sha256_matches_index = index_sha256 is None or index_sha256 == checksum_value
        if index_sha256 is not None and index_sha256 != checksum_value:
            issues.append(
                "python-distribution sha256 does not match the declared simple index entry: "
                f"{index_sha256} != {checksum_value}"
            )
    except Exception as exc:
        issues.append(str(exc))

    if build_checks_allowed and artifact_entry.reproducibility is not None:
        reproducibility_verification = verify_host_direct_single_file_reproducibility(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            kind="python-distribution",
            artifact_path=artifact_path,
            work_dir=work_dir / "reproducibility",
            component_config=component_config,
            project_root=project_root,
            source_date_epoch=source_date_epoch,
            inspection_bundle_root=inspection_bundle_root,
            subject_label="python-distribution",
            profile_overrides=profile_overrides,
        )
        issues.extend(reproducibility_verification.issues)

    return PythonDistributionVerificationReport(
        artifact_id=artifact_id,
        verdict="failed" if issues else "verified",
        issues=issues,
        filename=filename,
        uri=artifact_uri,
        index_url=index_url,
        project_name=project_name,
        version=version,
        checksum=ChecksumVerificationReport(
            algorithm=checksum_algorithm,
            value=actual_checksum,
            matches_manifest=checksum_matches_manifest,
            sidecar_verified=checksum_sidecar_verified,
        ),
        index_resolution=PythonIndexResolutionReport(
            project_index_url=project_index_url,
            resolved_url=resolved_url,
            found_via=found_via,
            sha256_matches_index=sha256_matches_index,
        ),
        reproducibility=reproducibility_verification,
    )


def _simple_index_project_url(index_url: str, project_name: str) -> str:
    normalized_project_name = _normalized_python_project_name(project_name)
    if index_url.endswith(".html") or index_url.endswith(".json"):
        return index_url
    return urljoin(index_url.rstrip("/") + "/", f"{normalized_project_name}/")


def _normalized_python_project_name(project_name: str) -> str:
    return re.sub(r"[-_.]+", "-", project_name).lower()


def _simple_index_entries(project_index_url: str) -> list[_SimpleIndexEntry]:
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
                with candidate_path.open("rb") as handle:
                    return read_bytes_bounded(handle, max_bytes=25 * 1024 * 1024)
        raise ValueError(f"python-distribution simple index directory has no index file: {local_path}")
    return read_uri_bytes(project_index_url)


def _simple_index_json_entries(project_index_url: str, payload_bytes: bytes) -> list[_SimpleIndexEntry]:
    payload = validate_json_object_model_text(
        _SimpleIndexJsonRead,
        payload_bytes,
        source=f"python-distribution simple index JSON at {project_index_url}",
        expected_payload="simple-index",
    )
    entries: list[_SimpleIndexEntry] = []
    for raw_file in payload.files:
        filename = raw_file.filename
        file_url = raw_file.url
        if filename is None or not filename.strip():
            continue
        if file_url is None or not file_url.strip():
            continue
        hashes = raw_file.hashes or {}
        entries.append(
            _SimpleIndexEntry(
                filename=filename.strip(),
                url=urljoin(project_index_url, file_url.strip()),
                hashes={
                    key.lower(): value.lower()
                    for key, value in hashes.items()
                    if isinstance(key, str) and isinstance(value, str)
                },
                source="simple-json",
            )
        )
    return entries


def _simple_index_html_entries(project_index_url: str, payload_bytes: bytes) -> list[_SimpleIndexEntry]:
    parser = _SimpleIndexHtmlParser()
    parser.feed(payload_bytes.decode("utf-8"))
    entries: list[_SimpleIndexEntry] = []
    for href in parser.links:
        resolved_url = urljoin(project_index_url, href)
        parsed_url = urlparse(resolved_url)
        filename = Path(parsed_url.path).name
        if not filename:
            continue
        entries.append(
            _SimpleIndexEntry(
                filename=filename,
                url=resolved_url,
                hashes=_hashes_from_fragment(parsed_url.fragment),
                source="simple-html",
            )
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
