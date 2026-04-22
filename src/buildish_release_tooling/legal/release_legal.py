# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generate preliminary release-legal artifacts for Python wheel/runtime outputs.

This helper is intentionally review-oriented instead of pretending to produce a
final publication-ready artifact. It derives the runtime dependency set from
``uv export --no-dev --frozen``, inspects the installed distributions available
to the current interpreter, copies bundled license/notice files into a review
directory, and writes draft ``LICENSE`` / ``NOTICE`` files plus detailed
inventory documents.

The generated output is a strong starting point for human review, not a final
source of truth.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import tomllib
from typing import Any

from buildish_release_tooling.release.process import run_logged_command

_PYLOCK_FILENAME = "pylock.release-legal.toml"
_LOCK_SELECTION_COMMAND = (
    "uv",
    "export",
    "--format",
    "pylock.toml",
    "--no-dev",
    "--frozen",
)
_LOCK_SELECTION_TIMEOUT_SECONDS = 15 * 60
_CONTAINERFILE_PATH = Path("tools/release-tooling-image/Containerfile")
_BASE_IMAGE_BUNDLE_MANIFEST_PATH = Path(
    "tools/release-tooling-image/legal/base-image-bundles.toml"
)
_NORMALIZE_NAME_PATTERN = re.compile(r"[-_.]+")
_LICENSE_FILE_NAMES = ("license", "licence", "copying")
_NOTICE_FILE_NAMES = ("notice", "notices")
_HOMEPAGE_LABELS = {"homepage", "home", "repository", "source"}
_REPOSITORY_URL_LABELS = {"repository", "source", "github"}
_MAX_LEGAL_FILE_BYTES = 25 * 1024 * 1024
_PRELIMINARY_WARNING = (
    "This file is PRELIMINARY and generated from dependency metadata plus "
    "bundled legal files. Human review is required before using it in any "
    "published artifact."
)
_LICENSE_SECTION_INTRO = (
    "The sections below describe bundled third-party Python runtime dependencies "
    "selected from uv.lock and inspected from the current installed environment."
)
_NOTICE_SECTION_INTRO = (
    "The sections below reproduce bundled third-party NOTICE-like content for "
    "human review."
)
_SPDX_TOKEN_PATTERN = re.compile(r"\(|\)|[A-Za-z0-9.+-]+")
_SPDX_OPERATORS = {"AND", "OR", "WITH"}
_FROM_INSTRUCTION_PATTERN = re.compile(
    r"^\s*FROM\s+(?P<image_ref>\S+)(?:\s+AS\s+(?P<alias>[A-Za-z0-9._-]+))?\s*$",
    re.IGNORECASE,
)
_COPY_FROM_PATTERN = re.compile(
    r"^\s*COPY\s+(?:--[^\s]+\s+)*--from=(?P<source>[^\s]+)",
    re.IGNORECASE,
)
_CATEGORY_X_SPDX_IDS = {
    "AGPL-3.0",
    "AGPL-3.0-ONLY",
    "AGPL-3.0-OR-LATER",
    "APSL-2.0",
    "BSD-2-CLAUSE-PATENT",
    "BSD-4-CLAUSE",
    "BUSL-1.1",
    "CPOL-1.02",
    "GPL-1.0",
    "GPL-1.0-ONLY",
    "GPL-1.0-OR-LATER",
    "GPL-2.0",
    "GPL-2.0-ONLY",
    "GPL-2.0-OR-LATER",
    "GPL-3.0",
    "GPL-3.0-ONLY",
    "GPL-3.0-OR-LATER",
    "JSON",
    "LGPL-2.0",
    "LGPL-2.0-ONLY",
    "LGPL-2.0-OR-LATER",
    "LGPL-2.1",
    "LGPL-2.1-ONLY",
    "LGPL-2.1-OR-LATER",
    "LGPL-3.0",
    "LGPL-3.0-ONLY",
    "LGPL-3.0-OR-LATER",
    "MS-LPL",
    "NPL-1.0",
    "NPL-1.1",
    "QPL-1.0",
    "SLEEPYCAT",
    "SSPL-1.0",
}
_CATEGORY_X_STRING_MARKERS = (
    "AFFERO GPL",
    "AGPL",
    "APPLE PUBLIC SOURCE LICENSE",
    "APSL-2.0",
    "BSD-4-CLAUSE",
    "BSD 4-CLAUSE",
    "BUSINESS SOURCE LICENSE",
    "BUSL-1.1",
    "COMMONS CLAUSE",
    "CPOL",
    "GNU AFFERO GENERAL PUBLIC LICENSE",
    "GNU GENERAL PUBLIC LICENSE",
    "GNU GPL",
    "JSON LICENSE",
    "LESSER GENERAL PUBLIC LICENSE",
    "LGPL",
    "MICROSOFT LIMITED PUBLIC LICENSE",
    "MS-LPL",
    "NETSCAPE PUBLIC LICENSE",
    "NPL 1.0",
    "NPL 1.1",
    "Q PUBLIC LICENSE",
    "QPL",
    "SERVER SIDE PUBLIC LICENSE",
    "SLEEPYCAT",
    "SSPL",
)
_CLASSPATH_EXCEPTION_SPDX_ID = "CLASSPATHEXCEPTION-2.0"
_GPL_2_ONLY_SPDX_IDS = {"GPL-2.0", "GPL-2.0-ONLY"}


@dataclass(frozen=True, slots=True)
class LockedPackage:
    """One runtime dependency selected from the project's lock export."""

    name: str
    version: str | None
    source_kind: str
    source_reference: str | None


@dataclass(frozen=True, slots=True)
class ProjectUrl:
    """One parsed ``Project-URL`` metadata entry."""

    label: str
    url: str

    def as_dict(self) -> dict[str, str]:
        return {"label": self.label, "url": self.url}


@dataclass(frozen=True, slots=True)
class CapturedLegalFile:
    """One copied legal file from an installed Python distribution."""

    kind: str
    original_relative_path: str
    installed_path: str
    output_relative_path: str
    sha256: str
    decode_warning: str | None
    text: str

    def as_inventory_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "outputRelativePath": self.output_relative_path,
            "sha256": self.sha256,
            "decodeWarning": self.decode_warning,
        }


@dataclass(frozen=True, slots=True)
class CuratedContainerImageBundle:
    """Repo-managed legal metadata for one bundled container image."""

    image_ref: str
    name: str
    version: str
    output_key: str
    home_page: str | None
    license_expression: str | None
    license_field: str | None
    license_paths: tuple[Path, ...]
    notice_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ContainerBuildStage:
    """One parsed ``FROM`` stage from the configured container definition."""

    index: int
    image_ref: str
    alias: str | None
    copy_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DistributionInventoryEntry:
    """Structured review inventory for one locked runtime distribution."""

    entry_kind: str
    name: str
    normalized_name: str
    version: str
    source_kind: str
    source_reference: str | None
    is_local_project: bool
    metadata_version: str | None
    summary: str | None
    home_page: str | None
    project_urls: tuple[ProjectUrl, ...]
    author: str | None
    author_email: str | None
    maintainer: str | None
    maintainer_email: str | None
    requires_dist: tuple[str, ...]
    license_expression: str | None
    license_field: str | None
    license_classifiers: tuple[str, ...]
    declared_license_summary: str | None
    captured_legal_files: tuple[CapturedLegalFile, ...]
    review_flags: tuple[str, ...]

    @property
    def license_files(self) -> tuple[CapturedLegalFile, ...]:
        return tuple(file for file in self.captured_legal_files if file.kind == "license")

    @property
    def notice_files(self) -> tuple[CapturedLegalFile, ...]:
        return tuple(file for file in self.captured_legal_files if file.kind == "notice")

    def as_inventory_dict(self) -> dict[str, Any]:
        return {
            "entryKind": self.entry_kind,
            "name": self.name,
            "normalizedName": self.normalized_name,
            "sourceKind": self.source_kind,
            "sourceReference": self.source_reference,
            "isLocalProject": self.is_local_project,
            "metadataVersion": self.metadata_version,
            "summary": self.summary,
            "homePage": self.home_page,
            "projectUrls": [item.as_dict() for item in self.project_urls],
            "author": self.author,
            "authorEmail": self.author_email,
            "maintainer": self.maintainer,
            "maintainerEmail": self.maintainer_email,
            "requiresDist": list(self.requires_dist),
            "licenseExpression": self.license_expression,
            "license": self.license_field,
            "licenseClassifiers": list(self.license_classifiers),
            "declaredLicenseSummary": self.declared_license_summary,
            "licenseFiles": [item.as_inventory_dict() for item in self.license_files],
            "noticeFiles": [item.as_inventory_dict() for item in self.notice_files],
            "reviewFlags": list(self.review_flags),
        }


@dataclass(frozen=True, slots=True)
class ReleaseLegalReport:
    """All generated review data for one run of the preliminary helper."""

    selection_command: tuple[str, ...]
    entries: tuple[DistributionInventoryEntry, ...]

    @property
    def python_runtime_entries(self) -> tuple[DistributionInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.entry_kind == "python-runtime-distribution"
        )

    @property
    def third_party_entries(self) -> tuple[DistributionInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.python_runtime_entries
            if not entry.is_local_project
        )

    @property
    def supplemental_entries(self) -> tuple[DistributionInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.entry_kind != "python-runtime-distribution"
        )

    @property
    def bundled_entries(self) -> tuple[DistributionInventoryEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.entry_kind != "python-runtime-distribution" or not entry.is_local_project
        )

    def as_inventory_dict(self) -> dict[str, Any]:
        packages_with_notices = sum(1 for entry in self.entries if entry.notice_files)
        packages_with_flags = sum(1 for entry in self.entries if entry.review_flags)
        runtime_package_count = len(self.python_runtime_entries)
        supplemental_component_count = len(self.supplemental_entries)
        return {
            "selection": {
                "kind": "uv-export-pylock",
                "command": list(self.selection_command),
                "runtimePackageCount": runtime_package_count,
            },
            "summary": {
                "runtimePackageCount": runtime_package_count,
                "supplementalComponentCount": supplemental_component_count,
                "packagesWithBundledNoticeFiles": packages_with_notices,
                "packagesWithReviewFlags": packages_with_flags,
            },
            "entries": [entry.as_inventory_dict() for entry in self.entries],
        }


def _metadata_value(
    metadata_message: metadata.PackageMetadata,
    key: str,
) -> str | None:
    if key not in metadata_message:
        return None
    return metadata_message[key]


def normalize_distribution_name(name: str) -> str:
    """Return the PEP 503-style canonical form used for package matching."""

    return _NORMALIZE_NAME_PATTERN.sub("-", name).lower()


def locked_runtime_packages_from_pylock_text(pylock_text: str) -> tuple[LockedPackage, ...]:
    """Parse one ``uv export --format pylock.toml`` result."""

    parsed = tomllib.loads(pylock_text)
    packages: list[LockedPackage] = []
    for package in parsed.get("packages", []):
        source_kind, source_reference = _locked_package_source(package)
        packages.append(
            LockedPackage(
                name=str(package["name"]),
                version=package.get("version"),
                source_kind=source_kind,
                source_reference=source_reference,
            )
        )
    return tuple(packages)


def export_locked_runtime_packages(project_dir: Path) -> tuple[LockedPackage, ...]:
    """Return the runtime dependency set from the repository's uv lockfile."""

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / _PYLOCK_FILENAME
        # Security note: this command is intentionally fixed to the repo's trusted
        # `uv export` workflow, with no shell interpolation and no user-controlled
        # executable or arguments.
        completed = run_logged_command(
            [*_LOCK_SELECTION_COMMAND, "--output-file", output_path.as_posix()],
            cwd=project_dir,
            check=True,
            capture_output=True,
            log_command=False,
            timeout_seconds=_LOCK_SELECTION_TIMEOUT_SECONDS,
        )
        if completed.stderr:
            # The command succeeded, so stderr is only advisory noise from tooling.
            _ = completed.stderr
        return locked_runtime_packages_from_pylock_text(
            output_path.read_text(encoding="utf-8")
        )


def generate_release_legal_artifacts(
    *,
    project_dir: Path,
    output_dir: Path,
    details_output_dir: Path | None = None,
    distribution_search_paths: tuple[Path, ...] | None = None,
    locked_packages: tuple[LockedPackage, ...] | None = None,
    project_license_text: str | None = None,
    project_notice_text: str | None = None,
) -> tuple[Path, ...]:
    """Generate preliminary legal review artifacts.

    ``output_dir`` receives the generated preliminary ``LICENSE`` and ``NOTICE``.
    When ``details_output_dir`` is set, the larger generated review bundle
    (inventory files plus copied third-party legal texts) is written there
    instead of alongside the checked-in top-level drafts.
    """

    resolved_project_dir = project_dir.resolve()
    selected_packages = (
        export_locked_runtime_packages(resolved_project_dir)
        if locked_packages is None
        else locked_packages
    )
    report = build_release_legal_report(
        project_dir=resolved_project_dir,
        locked_packages=selected_packages,
        distribution_search_paths=distribution_search_paths,
    )
    return write_release_legal_output(
        output_dir=output_dir,
        details_output_dir=details_output_dir,
        report=report,
        project_license_text=(
            project_license_text
            if project_license_text is not None
            else (resolved_project_dir / "LICENSE").read_text(encoding="utf-8")
        ),
        project_notice_text=(
            project_notice_text
            if project_notice_text is not None
            else (resolved_project_dir / "NOTICE").read_text(encoding="utf-8")
        ),
    )


def build_release_legal_report(
    *,
    project_dir: Path,
    locked_packages: tuple[LockedPackage, ...],
    distribution_search_paths: tuple[Path, ...] | None = None,
) -> ReleaseLegalReport:
    """Collect structured legal-review data for the locked runtime set."""

    distributions = installed_distributions_by_name(distribution_search_paths)
    entries: list[DistributionInventoryEntry] = []
    missing_packages: list[str] = []
    for locked_package in locked_packages:
        distribution = distributions.get(normalize_distribution_name(locked_package.name))
        if distribution is None:
            missing_packages.append(locked_package.name)
            continue
        entries.append(build_distribution_inventory_entry(distribution, locked_package))
    if missing_packages:
        missing = ", ".join(sorted(missing_packages))
        raise RuntimeError(
            "The current Python environment does not contain all runtime packages "
            f"selected from uv.lock: {missing}"
        )
    # Intentionally disabled for now: legal review has not confirmed that the
    # generated release LICENSE should enumerate container base-image
    # licenses here. Keep the collection helpers in place so the work can be
    # re-enabled later without re-discovering the container inputs.
    # entries.extend(collect_container_base_image_entries(project_dir))
    ordered_entries = tuple(sorted(entries, key=_inventory_sort_key))
    _raise_for_category_x_licenses(ordered_entries)
    return ReleaseLegalReport(
        selection_command=_LOCK_SELECTION_COMMAND,
        entries=ordered_entries,
    )


def installed_distributions_by_name(
    search_paths: tuple[Path, ...] | None,
) -> dict[str, metadata.Distribution]:
    """Index installed distributions by normalized package name."""

    distribution_iterable = (
        metadata.distributions()
        if search_paths is None
        else metadata.distributions(path=[path.as_posix() for path in search_paths])
    )
    indexed: dict[str, metadata.Distribution] = {}
    duplicates: set[str] = set()
    for distribution in distribution_iterable:
        name = _metadata_value(distribution.metadata, "Name")
        if name is None:
            continue
        normalized_name = normalize_distribution_name(name)
        existing_distribution = indexed.get(normalized_name)
        if existing_distribution is not None:
            preferred_distribution = _prefer_distribution_candidate(
                existing_distribution, distribution
            )
            if preferred_distribution is None:
                duplicates.add(normalized_name)
                continue
            indexed[normalized_name] = preferred_distribution
            continue
        indexed[normalized_name] = distribution
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise RuntimeError(
            "Multiple installed distributions matched the same normalized name: "
            f"{duplicate_list}"
        )
    return indexed


def _prefer_distribution_candidate(
    existing_distribution: metadata.Distribution,
    candidate_distribution: metadata.Distribution,
) -> metadata.Distribution | None:
    """Prefer the richer metadata source when editable installs expose duplicates.

    Some Python environments expose both an ``.egg-info`` view and a richer
    ``.dist-info`` view for the same installed project. Prefer the candidate that
    exposes a ``RECORD`` file and enumerated installed files. If the candidates
    are still indistinguishable after that, keep the duplicate as an explicit
    error instead of guessing.
    """

    existing_rank = _distribution_preference_rank(existing_distribution)
    candidate_rank = _distribution_preference_rank(candidate_distribution)
    if candidate_rank > existing_rank:
        return candidate_distribution
    if candidate_rank < existing_rank:
        return existing_distribution
    return None


def _distribution_preference_rank(
    distribution: metadata.Distribution,
) -> tuple[int, int, int]:
    files = tuple(distribution.files or ())
    return (
        int(distribution.read_text("RECORD") is not None),
        int(bool(files)),
        len(files),
    )


def build_distribution_inventory_entry(
    distribution: metadata.Distribution,
    locked_package: LockedPackage,
) -> DistributionInventoryEntry:
    """Build review metadata for one installed distribution."""

    metadata_message = distribution.metadata
    project_urls = _parse_project_urls(metadata_message)
    legal_files = collect_distribution_legal_files(distribution)
    declared_license_summary = _declared_license_summary(metadata_message)
    review_flags = list(_review_flags(metadata_message, legal_files))
    if any(file.decode_warning for file in legal_files):
        review_flags.append("legal-file-utf8-decode-warning")
    distribution_name = _metadata_value(metadata_message, "Name") or locked_package.name
    return DistributionInventoryEntry(
        entry_kind="python-runtime-distribution",
        name=distribution_name,
        normalized_name=normalize_distribution_name(distribution_name),
        version=_metadata_value(metadata_message, "Version") or locked_package.version or "unknown",
        source_kind=locked_package.source_kind,
        source_reference=locked_package.source_reference,
        is_local_project=locked_package.source_kind == "directory",
        metadata_version=_metadata_value(metadata_message, "Metadata-Version"),
        summary=_metadata_value(metadata_message, "Summary"),
        home_page=_home_page(metadata_message, project_urls),
        project_urls=project_urls,
        author=_metadata_value(metadata_message, "Author"),
        author_email=_metadata_value(metadata_message, "Author-email"),
        maintainer=_metadata_value(metadata_message, "Maintainer"),
        maintainer_email=_metadata_value(metadata_message, "Maintainer-email"),
        requires_dist=tuple(metadata_message.get_all("Requires-Dist") or ()),
        license_expression=_metadata_value(metadata_message, "License-Expression"),
        license_field=_metadata_value(metadata_message, "License"),
        license_classifiers=tuple(_license_classifiers(metadata_message)),
        declared_license_summary=declared_license_summary,
        captured_legal_files=legal_files,
        review_flags=tuple(dict.fromkeys(review_flags)),
    )


def collect_container_base_image_entries(
    project_dir: Path,
) -> tuple[DistributionInventoryEntry, ...]:
    """Return curated legal entries for container images bundled into the final image."""

    containerfile_path = project_dir / _CONTAINERFILE_PATH
    if not containerfile_path.is_file():
        return ()

    manifest_path = project_dir / _BASE_IMAGE_BUNDLE_MANIFEST_PATH
    if not manifest_path.is_file():
        raise RuntimeError(
            "The configured container image exists but no curated base-image legal "
            f"bundle manifest was found at {manifest_path.as_posix()}"
        )

    referenced_image_refs = bundled_container_image_refs(containerfile_path)
    curated_bundles = curated_container_image_bundles_by_ref(
        project_dir=project_dir,
        manifest_path=manifest_path,
    )
    missing_bundles = sorted(
        image_ref for image_ref in referenced_image_refs if image_ref not in curated_bundles
    )
    if missing_bundles:
        missing_list = "\n - ".join(("", *missing_bundles))
        raise RuntimeError(
            "The configured container image references base images that have no "
            f"curated release-legal bundle metadata:{missing_list}"
        )
    return tuple(
        build_curated_container_image_entry(
            bundle=curated_bundles[image_ref],
        )
        for image_ref in referenced_image_refs
    )


def bundled_container_image_refs(containerfile_path: Path) -> tuple[str, ...]:
    """Return image refs that flow into the final configured container image."""

    stages = parse_container_build_stages(containerfile_path.read_text(encoding="utf-8"))
    if not stages:
        return ()

    stage_lookup: dict[str, int] = {}
    for stage in stages:
        stage_lookup[str(stage.index)] = stage.index
        if stage.alias is not None:
            stage_lookup[stage.alias] = stage.index

    included_stage_indexes = collect_included_stage_indexes(stages, stage_lookup)
    image_refs: list[str] = []
    for stage_index in included_stage_indexes:
        image_refs.append(stages[stage_index].image_ref)
        for copy_source in stages[stage_index].copy_sources:
            if copy_source not in stage_lookup:
                image_refs.append(copy_source)
    return tuple(dict.fromkeys(image_refs))


def parse_container_build_stages(containerfile_text: str) -> tuple[ContainerBuildStage, ...]:
    """Parse ``FROM`` stages and ``COPY --from`` dependencies from a Containerfile."""

    stages: list[ContainerBuildStage] = []
    current_image_ref: str | None = None
    current_alias: str | None = None
    current_copy_sources: list[str] = []

    for raw_line in containerfile_text.splitlines():
        from_match = _FROM_INSTRUCTION_PATTERN.match(raw_line)
        if from_match is not None:
            if current_image_ref is not None:
                stages.append(
                    ContainerBuildStage(
                        index=len(stages),
                        image_ref=current_image_ref,
                        alias=current_alias,
                        copy_sources=tuple(current_copy_sources),
                    )
                )
            current_image_ref = from_match.group("image_ref")
            current_alias = from_match.group("alias")
            current_copy_sources = []
            continue

        if current_image_ref is None:
            continue
        copy_match = _COPY_FROM_PATTERN.match(raw_line)
        if copy_match is not None:
            current_copy_sources.append(copy_match.group("source"))

    if current_image_ref is not None:
        stages.append(
            ContainerBuildStage(
                index=len(stages),
                image_ref=current_image_ref,
                alias=current_alias,
                copy_sources=tuple(current_copy_sources),
            )
        )
    return tuple(stages)


def collect_included_stage_indexes(
    stages: tuple[ContainerBuildStage, ...],
    stage_lookup: dict[str, int],
) -> tuple[int, ...]:
    """Return stage indexes whose content ends up in the final image."""

    if not stages:
        return ()

    included_stage_indexes: set[int] = set()
    stack = [len(stages) - 1]
    while stack:
        stage_index = stack.pop()
        if stage_index in included_stage_indexes:
            continue
        included_stage_indexes.add(stage_index)
        for copy_source in stages[stage_index].copy_sources:
            referenced_stage_index = stage_lookup.get(copy_source)
            if referenced_stage_index is not None:
                stack.append(referenced_stage_index)
    return tuple(sorted(included_stage_indexes))


def curated_container_image_bundles_by_ref(
    *,
    project_dir: Path,
    manifest_path: Path,
) -> dict[str, CuratedContainerImageBundle]:
    """Load repo-managed legal metadata for bundled container base images."""

    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    bundles_by_ref: dict[str, CuratedContainerImageBundle] = {}
    for raw_bundle in manifest.get("bundles", []):
        image_ref = str(raw_bundle["image-ref"])
        bundles_by_ref[image_ref] = CuratedContainerImageBundle(
            image_ref=image_ref,
            name=str(raw_bundle["name"]),
            version=str(raw_bundle["version"]),
            output_key=_validate_curated_output_key(str(raw_bundle["output-key"])),
            home_page=_optional_string(raw_bundle.get("home-page")),
            license_expression=_optional_string(raw_bundle.get("license-expression")),
            license_field=_optional_string(raw_bundle.get("license")),
            license_paths=tuple(
                _resolve_curated_manifest_path(project_dir, str(relative_path), field_name="license-files")
                for relative_path in raw_bundle.get("license-files", [])
            ),
            notice_paths=tuple(
                _resolve_curated_manifest_path(project_dir, str(relative_path), field_name="notice-files")
                for relative_path in raw_bundle.get("notice-files", [])
            ),
        )
    return bundles_by_ref


def _resolve_curated_manifest_path(project_dir: Path, raw_path: str, *, field_name: str) -> Path:
    project_root = project_dir.resolve()
    candidate = Path(raw_path.strip())
    if not raw_path.strip():
        raise ValueError(f"curated container image {field_name} entry must not be empty")
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"curated container image {field_name} entry must stay under the project root")
    resolved = (project_root / candidate).resolve()
    if not resolved.is_relative_to(project_root):
        raise ValueError(f"curated container image {field_name} entry must stay under the project root")
    return resolved


def _validate_curated_output_key(raw_output_key: str) -> str:
    output_key = raw_output_key.strip()
    if not output_key:
        raise ValueError("curated container image output-key must not be empty")
    pure_key = PurePosixPath(output_key)
    if pure_key.name != output_key or ".." in pure_key.parts:
        raise ValueError("curated container image output-key must be a simple path component")
    return output_key


def build_curated_container_image_entry(
    *,
    bundle: CuratedContainerImageBundle,
) -> DistributionInventoryEntry:
    """Convert one curated container-image bundle into a normal inventory entry."""

    legal_files = collect_curated_legal_files(
        component_key=bundle.output_key,
        component_kind="container-base-image",
        license_paths=bundle.license_paths,
        notice_paths=bundle.notice_paths,
    )
    review_flags: list[str] = []
    if any(file.decode_warning for file in legal_files):
        review_flags.append("legal-file-utf8-decode-warning")
    if any(file.kind == "notice" for file in legal_files):
        review_flags.append("bundled-notice-files-require-review")
    if not bundle.license_paths:
        review_flags.append("missing-curated-license-files")

    return DistributionInventoryEntry(
        entry_kind="container-base-image",
        name=bundle.name,
        normalized_name=normalize_distribution_name(bundle.name),
        version=bundle.version,
        source_kind="container-image",
        source_reference=bundle.image_ref,
        is_local_project=False,
        metadata_version=None,
        summary=(
            "Curated legal metadata for a container image whose content is bundled "
            "into the final configured image."
        ),
        home_page=bundle.home_page,
        project_urls=(),
        author=None,
        author_email=None,
        maintainer=None,
        maintainer_email=None,
        requires_dist=(),
        license_expression=bundle.license_expression,
        license_field=bundle.license_field,
        license_classifiers=(),
        declared_license_summary=_curated_declared_license_summary(bundle),
        captured_legal_files=legal_files,
        review_flags=tuple(review_flags),
    )


def collect_curated_legal_files(
    *,
    component_key: str,
    component_kind: str,
    license_paths: tuple[Path, ...],
    notice_paths: tuple[Path, ...],
) -> tuple[CapturedLegalFile, ...]:
    """Read repo-managed legal files for curated bundled components."""

    captured: list[CapturedLegalFile] = []
    for kind, paths in (("license", license_paths), ("notice", notice_paths)):
        for source_path in paths:
            if not source_path.is_file():
                raise RuntimeError(
                    f"Missing curated {kind} file for {component_kind}: {source_path.as_posix()}"
                )
            file_bytes = _read_legal_file_bytes(source_path)
            try:
                file_text = file_bytes.decode("utf-8")
                decode_warning = None
            except UnicodeDecodeError:
                file_text = file_bytes.decode("utf-8", errors="replace")
                decode_warning = (
                    "File was not valid UTF-8 and was decoded with replacement characters."
                )
            captured.append(
                CapturedLegalFile(
                    kind=kind,
                    original_relative_path=source_path.name,
                    installed_path=source_path.as_posix(),
                    output_relative_path=(
                        f"{kind}s/container-base-images/{component_key}/{source_path.name}"
                    ),
                    sha256=hashlib.sha256(file_bytes).hexdigest(),
                    decode_warning=decode_warning,
                    text=_ensure_trailing_newline(file_text),
                )
            )
    return tuple(sorted(captured, key=lambda file: file.output_relative_path))


def _curated_declared_license_summary(bundle: CuratedContainerImageBundle) -> str | None:
    if bundle.license_expression is not None:
        return f"SPDX: {bundle.license_expression}"
    return bundle.license_field


def collect_distribution_legal_files(
    distribution: metadata.Distribution,
) -> tuple[CapturedLegalFile, ...]:
    """Collect bundled license and notice files from one installed distribution."""

    name = _metadata_value(distribution.metadata, "Name") or "unknown"
    dist_key = normalize_distribution_name(name)
    distribution_root = Path(str(distribution.locate_file(""))).resolve(strict=False)
    captured: dict[str, CapturedLegalFile] = {}
    for relative_path in distribution.files or ():
        pure_relative_path = PurePosixPath(str(relative_path))
        capture_kind = _captured_legal_file_kind(pure_relative_path)
        if capture_kind is None:
            continue
        if pure_relative_path.is_absolute() or ".." in pure_relative_path.parts:
            raise ValueError(f"distribution legal file path must stay under distribution root: {relative_path}")
        absolute_path = Path(str(distribution.locate_file(relative_path)))
        resolved_path = absolute_path.resolve(strict=False)
        if absolute_path.is_symlink() or not resolved_path.is_relative_to(distribution_root):
            raise ValueError(f"distribution legal file path must stay under distribution root: {relative_path}")
        if not absolute_path.is_file():
            continue
        file_bytes = _read_legal_file_bytes(absolute_path)
        try:
            file_text = file_bytes.decode("utf-8")
            decode_warning = None
        except UnicodeDecodeError:
            file_text = file_bytes.decode("utf-8", errors="replace")
            decode_warning = "File was not valid UTF-8 and was decoded with replacement characters."
        output_relative_path = _managed_output_relative_path(
            package_key=dist_key,
            capture_kind=capture_kind,
            original_relative_path=pure_relative_path,
        )
        captured[output_relative_path] = CapturedLegalFile(
            kind=capture_kind,
            original_relative_path=pure_relative_path.as_posix(),
            installed_path=resolved_path.as_posix(),
            output_relative_path=output_relative_path,
            sha256=hashlib.sha256(file_bytes).hexdigest(),
            decode_warning=decode_warning,
            text=_ensure_trailing_newline(file_text),
        )
    return tuple(sorted(captured.values(), key=lambda file: file.output_relative_path))


def _read_legal_file_bytes(path: Path) -> bytes:
    file_size = path.stat().st_size
    if file_size > _MAX_LEGAL_FILE_BYTES:
        raise RuntimeError(
            f"Legal file is too large to capture: {path.as_posix()} "
            f"({file_size} bytes exceeds {_MAX_LEGAL_FILE_BYTES} bytes)"
        )
    return path.read_bytes()


def write_release_legal_output(
    *,
    output_dir: Path,
    details_output_dir: Path | None,
    report: ReleaseLegalReport,
    project_license_text: str,
    project_notice_text: str,
) -> tuple[Path, ...]:
    """Write the preliminary review files and copied legal texts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_details_output_dir = output_dir if details_output_dir is None else details_output_dir
    resolved_details_output_dir.mkdir(parents=True, exist_ok=True)
    licenses_dir = resolved_details_output_dir / "licenses"
    notices_dir = resolved_details_output_dir / "notices"

    if resolved_details_output_dir != output_dir:
        for stale_path in (
            resolved_details_output_dir / "LICENSE",
            resolved_details_output_dir / "NOTICE",
            output_dir / "inventory.json",
            output_dir / "inventory.md",
            output_dir / "licenses",
            output_dir / "notices",
        ):
            _remove_output_path(stale_path)

    for managed_dir in (licenses_dir, notices_dir):
        if managed_dir.exists():
            shutil.rmtree(managed_dir)
        managed_dir.mkdir(parents=True, exist_ok=True)

    for entry in report.entries:
        for legal_file in entry.captured_legal_files:
            destination = _resolve_legal_output_path(
                resolved_details_output_dir,
                legal_file.output_relative_path,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(legal_file.text, encoding="utf-8")

    license_path = output_dir / "LICENSE"
    notice_path = output_dir / "NOTICE"
    inventory_json_path = resolved_details_output_dir / "inventory.json"
    inventory_markdown_path = resolved_details_output_dir / "inventory.md"

    license_path.write_text(
        build_preliminary_license_text(report, project_license_text),
        encoding="utf-8",
    )
    notice_path.write_text(
        build_preliminary_notice_text(report, project_notice_text),
        encoding="utf-8",
    )
    inventory_json_path.write_text(
        json.dumps(report.as_inventory_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inventory_markdown_path.write_text(
        build_inventory_markdown(report),
        encoding="utf-8",
    )

    return (
        license_path,
        notice_path,
        inventory_json_path,
        inventory_markdown_path,
        licenses_dir,
        notices_dir,
    )


def build_preliminary_license_text(
    report: ReleaseLegalReport, project_license_text: str
) -> str:
    """Render the generated draft ``LICENSE`` text."""

    lines = [
        _ensure_trailing_newline(project_license_text).rstrip("\n"),
        "",
    ]
    if not report.bundled_entries:
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            _section_rule(),
            _LICENSE_SECTION_INTRO,
            _PRELIMINARY_WARNING,
            f"Selection command: {' '.join(report.selection_command)}",
            "",
        ]
    )
    for entry in report.bundled_entries:
        lines.extend(
            _render_license_distribution_section(
                entry, project_license_text=project_license_text
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def build_preliminary_notice_text(
    report: ReleaseLegalReport, project_notice_text: str
) -> str:
    """Render the generated draft ``NOTICE`` text."""

    lines = [
        _ensure_trailing_newline(project_notice_text).rstrip("\n"),
        "",
    ]
    entries_with_notices = tuple(entry for entry in report.bundled_entries if entry.notice_files)
    if not entries_with_notices:
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            _section_rule(),
            _NOTICE_SECTION_INTRO,
            _PRELIMINARY_WARNING,
            f"Selection command: {' '.join(report.selection_command)}",
            "",
        ]
    )
    for entry in entries_with_notices:
        lines.extend(_render_notice_distribution_section(entry))
    return "\n".join(lines).rstrip() + "\n"


def build_inventory_markdown(report: ReleaseLegalReport) -> str:
    """Render the human-readable Markdown inventory."""

    packages_with_notices = sum(1 for entry in report.entries if entry.notice_files)
    packages_with_flags = sum(1 for entry in report.entries if entry.review_flags)
    supplemental_component_count = len(report.supplemental_entries)
    lines = [
        "<!--",
        "Copyright 2026 The Buildish Authors",
        "",
        'Licensed under the Apache License, Version 2.0 (the "License");',
        "you may not use this file except in compliance with the License.",
        "You may obtain a copy of the License at",
        "",
        "http://www.apache.org/licenses/LICENSE-2.0",
        "",
        "Unless required by applicable law or agreed to in writing, software",
        'distributed under the License is distributed on an "AS IS" BASIS,',
        "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
        "See the License for the specific language governing permissions and",
        "limitations under the License.",
        "-->",
        "",
        "# Preliminary release-legal inventory",
        "",
        _PRELIMINARY_WARNING,
        "",
        f"- selection command: `{' '.join(report.selection_command)}`",
        f"- runtime packages: `{len(report.python_runtime_entries)}`",
        f"- supplemental bundled components: `{supplemental_component_count}`",
        f"- packages with bundled notice files: `{packages_with_notices}`",
        f"- packages with review flags: `{packages_with_flags}`",
        "",
        "## Package summary",
        "",
        "| Package | Source | Declared license | License files | Notice files | Review flags |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in report.entries:
        lines.append(
            "| "
            f"`{entry.name}` | `{entry.source_kind}` | "
            f"{_escape_markdown_table_cell(entry.declared_license_summary or '(missing)')} | "
            f"{len(entry.license_files)} | {len(entry.notice_files)} | "
            f"{_escape_markdown_table_cell(', '.join(entry.review_flags) if entry.review_flags else '—')} |"
        )
    lines.extend(["", "## Review details", ""])
    for entry in report.entries:
        lines.extend(_render_inventory_detail_section(entry))
    return "\n".join(lines).rstrip() + "\n"


def _render_license_distribution_section(
    entry: DistributionInventoryEntry,
    *,
    project_license_text: str,
) -> list[str]:
    lines = [
        _section_rule(),
        f"This product bundles {entry.name}.",
        "",
    ]
    for link_label, url in _license_section_links(entry):
        lines.append(f"{link_label}: {url}")
    lines.append(f"License: {_display_license_name(entry)}")
    review_notes = _review_note_messages(entry.review_flags)
    if review_notes:
        lines.append("Review notes:")
        for review_note in review_notes:
            lines.append(f"* {review_note}")
    lines.append("")

    for legal_file in entry.license_files:
        if _should_inline_license_text(
            entry,
            legal_file=legal_file,
            project_license_text=project_license_text,
        ):
            lines.append(f"Included license text from {legal_file.output_relative_path}:")
            lines.extend(_pipe_prefixed_lines(legal_file.text))
            lines.append("")
    return lines


def _render_notice_distribution_section(entry: DistributionInventoryEntry) -> list[str]:
    lines = [
        _section_rule(),
        f"This product bundles {entry.name} with the following in its NOTICE file:",
        "|",
    ]
    for legal_file in entry.notice_files:
        lines.extend(_pipe_prefixed_lines(legal_file.text))
        lines.append("|")
    lines.append("")
    return lines


def _license_section_links(entry: DistributionInventoryEntry) -> tuple[tuple[str, str], ...]:
    links: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    if entry.home_page is not None:
        links.append(("Project URL", entry.home_page))
        seen_urls.add(entry.home_page)
    for project_url in entry.project_urls:
        normalized_label = project_url.label.strip().lower()
        if normalized_label not in _REPOSITORY_URL_LABELS:
            continue
        if project_url.url in seen_urls:
            continue
        links.append(("Repository URL", project_url.url))
        seen_urls.add(project_url.url)
        break
    return tuple(links)


def _review_note_messages(review_flags: tuple[str, ...]) -> tuple[str, ...]:
    messages = [_review_note_message(flag) for flag in review_flags]
    return tuple(message for message in messages if message is not None)


def _review_note_message(review_flag: str) -> str | None:
    if review_flag == "classifier-only-license-metadata":
        return None
    if review_flag == "missing-license-metadata":
        return (
            "The package metadata does not declare a license. Review the bundled legal "
            "files manually before relying on this entry."
        )
    if review_flag == "license-and-license-expression-both-present":
        return (
            "The package declares both `License` and `License-Expression` metadata. "
            "Verify that both declarations agree."
        )
    if review_flag == "no-license-files-detected":
        return (
            "No bundled license file was detected in the installed distribution. "
            "Check whether a license file still needs to be added manually."
        )
    if review_flag == "bundled-notice-files-require-review":
        return (
            "A bundled NOTICE-like file was detected. Review whether its contents must "
            "be merged into the final `NOTICE`."
        )
    if review_flag == "legal-file-utf8-decode-warning":
        return (
            "At least one captured legal file was not valid UTF-8 and was decoded with "
            "replacement characters. Verify the copied text manually."
        )
    if review_flag == "missing-curated-license-files":
        return (
            "This curated container-image entry does not list any license files yet. "
            "Add them before relying on this output."
        )
    return f"Manual review is required for `{review_flag}`."


def _render_inventory_detail_section(entry: DistributionInventoryEntry) -> list[str]:
    lines = [f"### {entry.name}", ""]
    lines.append(f"- source: `{entry.source_kind}`{_markdown_source_reference_suffix(entry.source_reference)}")
    lines.append(
        f"- declared license: `{entry.declared_license_summary or '(missing declared license metadata)'}`"
    )
    if entry.home_page is not None:
        lines.append(f"- home page: `{entry.home_page}`")
    if entry.project_urls:
        lines.append("- project URLs:")
        for project_url in entry.project_urls:
            lines.append(f"  - `{project_url.label}`: `{project_url.url}`")
    if entry.requires_dist:
        lines.append("- Requires-Dist entries:")
        for requirement in entry.requires_dist:
            lines.append(f"  - `{requirement}`")
    lines.append("- copied license files:")
    if entry.license_files:
        for legal_file in entry.license_files:
            lines.append(f"  - `{legal_file.output_relative_path}`")
    else:
        lines.append("  - none found")
    lines.append("- copied notice files:")
    if entry.notice_files:
        for legal_file in entry.notice_files:
            lines.append(f"  - `{legal_file.output_relative_path}`")
    else:
        lines.append("  - none found")
    lines.append("- review flags:")
    if entry.review_flags:
        for flag in entry.review_flags:
            lines.append(f"  - `{flag}`")
    else:
        lines.append("  - none")
    lines.append("")
    return lines


def _captured_legal_file_kind(relative_path: PurePosixPath) -> str | None:
    lowered_path = relative_path.as_posix().lower()
    lowered_name = relative_path.name.lower()
    if ".dist-info/licenses/" in lowered_path:
        return "notice" if _looks_like_notice_file(lowered_name) else "license"
    if ".dist-info/" not in lowered_path:
        return None
    if _looks_like_notice_file(lowered_name):
        return "notice"
    if _looks_like_license_file(lowered_name):
        return "license"
    return None


def _managed_output_relative_path(
    *,
    package_key: str,
    capture_kind: str,
    original_relative_path: PurePosixPath,
) -> str:
    base_dir = PurePosixPath("notices" if capture_kind == "notice" else "licenses") / package_key
    lowered_path = original_relative_path.as_posix().lower()
    if ".dist-info/licenses/" in lowered_path:
        _, relative_suffix = original_relative_path.as_posix().split(".dist-info/licenses/", maxsplit=1)
        return (base_dir / _safe_relative_subpath(PurePosixPath(relative_suffix))).as_posix()
    return (base_dir / _safe_relative_subpath(PurePosixPath(original_relative_path.name))).as_posix()


def _safe_relative_subpath(path: PurePosixPath) -> PurePosixPath:
    safe_parts = tuple(part for part in path.parts if part not in {"", ".", "..", "/"})
    return PurePosixPath(*safe_parts) if safe_parts else PurePosixPath("legal.txt")


def _resolve_legal_output_path(root: Path, relative_path: str) -> Path:
    raw_path = Path(relative_path)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise ValueError(f"generated legal output path must stay under output root: {relative_path}")
    resolved_root = root.resolve(strict=False)
    resolved_path = (resolved_root / raw_path).resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"generated legal output path must stay under output root: {relative_path}")
    return resolved_path


def _review_flags(
    metadata_message: metadata.PackageMetadata,
    legal_files: tuple[CapturedLegalFile, ...],
) -> tuple[str, ...]:
    flags: list[str] = []
    has_license_expression = _metadata_value(metadata_message, "License-Expression") is not None
    has_license_field = _metadata_value(metadata_message, "License") is not None
    classifiers = _license_classifiers(metadata_message)
    if not has_license_expression and not has_license_field and not classifiers:
        flags.append("missing-license-metadata")
    if not has_license_expression and not has_license_field and classifiers:
        flags.append("classifier-only-license-metadata")
    if has_license_expression and has_license_field:
        flags.append("license-and-license-expression-both-present")
    if not any(file.kind == "license" for file in legal_files):
        flags.append("no-license-files-detected")
    if any(file.kind == "notice" for file in legal_files):
        flags.append("bundled-notice-files-require-review")
    return tuple(flags)


def _raise_for_category_x_licenses(
    entries: tuple[DistributionInventoryEntry, ...],
) -> None:
    violations: list[str] = []
    for entry in entries:
        violation_reason = _category_x_violation_reason(entry)
        if violation_reason is None:
            continue
        violations.append(f"{entry.name} {entry.version}: {violation_reason}")
    if violations:
        violation_list = "\n - ".join(("", *violations))
        raise RuntimeError(
            "Refusing to generate release-legal artifacts because Apache Category X "
            f"license metadata was detected:{violation_list}"
        )


def _category_x_violation_reason(
    entry: DistributionInventoryEntry,
) -> str | None:
    if entry.license_expression is not None and _spdx_expression_is_category_x(
        entry.license_expression
    ):
        return (
            "SPDX license expression "
            f"{entry.license_expression!r} resolves to an Apache Category X license"
        )
    for metadata_value in (entry.license_field, *entry.license_classifiers):
        if metadata_value is None:
            continue
        marker = _category_x_string_marker(metadata_value)
        if marker is None:
            continue
        return (
            f"declared license metadata {metadata_value!r} matched prohibited marker "
            f"{marker!r}"
        )
    return None


def _spdx_expression_is_category_x(expression: str) -> bool:
    tokens = _SPDX_TOKEN_PATTERN.findall(expression)
    if not tokens:
        return False
    parsed_value, next_index = _parse_spdx_or_expression(tokens, 0)
    if next_index != len(tokens):
        return any(
            _spdx_identifier_is_category_x(token)
            for token in tokens
            if token.upper() not in _SPDX_OPERATORS and token not in {"(", ")"}
        )
    return parsed_value


def _parse_spdx_or_expression(tokens: list[str], start_index: int) -> tuple[bool, int]:
    value, index = _parse_spdx_and_expression(tokens, start_index)
    while index < len(tokens) and tokens[index].upper() == "OR":
        next_value, next_index = _parse_spdx_and_expression(tokens, index + 1)
        value = value and next_value
        index = next_index
    return value, index


def _parse_spdx_and_expression(tokens: list[str], start_index: int) -> tuple[bool, int]:
    value, index = _parse_spdx_factor(tokens, start_index)
    while index < len(tokens) and tokens[index].upper() == "AND":
        next_value, next_index = _parse_spdx_factor(tokens, index + 1)
        value = value or next_value
        index = next_index
    return value, index


def _parse_spdx_factor(tokens: list[str], start_index: int) -> tuple[bool, int]:
    if start_index >= len(tokens):
        raise ValueError("Unexpected end of SPDX expression")
    current_symbol = tokens[start_index]
    if current_symbol == "(":
        value, index = _parse_spdx_or_expression(tokens, start_index + 1)
        if index >= len(tokens) or tokens[index] != ")":
            raise ValueError("Unbalanced SPDX parentheses")
        return value, index + 1
    if current_symbol in {"AND", "OR", "WITH", ")"}:
        raise ValueError(f"Unexpected SPDX token {current_symbol!r}")

    license_id = _normalize_spdx_identifier(current_symbol)
    next_index = start_index + 1
    if next_index + 1 < len(tokens) and tokens[next_index].upper() == "WITH":
        exception_id = _normalize_spdx_identifier(tokens[next_index + 1])
        return (_spdx_with_expression_is_category_x(license_id, exception_id), next_index + 2)
    return (_spdx_identifier_is_category_x(license_id), next_index)


def _spdx_with_expression_is_category_x(license_id: str, exception_id: str) -> bool:
    if license_id in _GPL_2_ONLY_SPDX_IDS and exception_id == _CLASSPATH_EXCEPTION_SPDX_ID:
        return False
    return _spdx_identifier_is_category_x(license_id)


def _spdx_identifier_is_category_x(identifier: str) -> bool:
    return _normalize_spdx_identifier(identifier) in _CATEGORY_X_SPDX_IDS


def _normalize_spdx_identifier(identifier: str) -> str:
    return identifier.strip().upper()


def _category_x_string_marker(metadata_value: str) -> str | None:
    upper_value = metadata_value.upper()
    for marker in _CATEGORY_X_STRING_MARKERS:
        if marker in upper_value:
            return marker
    return None


def _declared_license_summary(
    metadata_message: metadata.PackageMetadata,
) -> str | None:
    license_expression = _metadata_value(metadata_message, "License-Expression")
    if license_expression is not None:
        return f"SPDX: {license_expression}"
    license_field = _metadata_value(metadata_message, "License")
    if license_field is not None:
        return license_field
    classifiers = _license_classifiers(metadata_message)
    if classifiers:
        return "; ".join(classifiers)
    return None


def _license_classifiers(
    metadata_message: metadata.PackageMetadata,
) -> tuple[str, ...]:
    return tuple(
        value
        for value in (metadata_message.get_all("Classifier") or ())
        if value.startswith("License ::")
    )


def _parse_project_urls(
    metadata_message: metadata.PackageMetadata,
) -> tuple[ProjectUrl, ...]:
    parsed: list[ProjectUrl] = []
    for raw_value in metadata_message.get_all("Project-URL") or ():
        label, separator, url = raw_value.partition(",")
        if not separator:
            continue
        parsed.append(ProjectUrl(label=label.strip(), url=url.strip()))
    return tuple(parsed)


def _home_page(
    metadata_message: metadata.PackageMetadata,
    project_urls: tuple[ProjectUrl, ...],
) -> str | None:
    home_page = _metadata_value(metadata_message, "Home-page")
    if home_page is not None:
        return home_page
    for project_url in project_urls:
        if project_url.label.lower() in _HOMEPAGE_LABELS:
            return project_url.url
    return project_urls[0].url if project_urls else None


def _locked_package_source(package: dict[str, Any]) -> tuple[str, str | None]:
    if "directory" in package:
        directory = package["directory"]
        return ("directory", str(directory.get("path")))
    if "vcs" in package:
        vcs = package["vcs"]
        return ("vcs", str(vcs.get("url")))
    if "archive" in package:
        archive = package["archive"]
        return ("archive", str(archive.get("url")))
    if "index" in package:
        return ("index", str(package.get("index")))
    if "sdist" in package:
        return ("sdist", str(package["sdist"].get("url")))
    if "wheels" in package and package["wheels"]:
        first_wheel = package["wheels"][0]
        return ("wheel", str(first_wheel.get("url")))
    return ("unknown", None)


def _inventory_sort_key(entry: DistributionInventoryEntry) -> tuple[str, str, str, str, str]:
    return (
        entry.normalized_name,
        entry.version,
        entry.entry_kind,
        entry.source_kind,
        entry.source_reference or "",
    )


def _looks_like_license_file(file_name: str) -> bool:
    return file_name.startswith(_LICENSE_FILE_NAMES)


def _looks_like_notice_file(file_name: str) -> bool:
    return file_name.startswith(_NOTICE_FILE_NAMES)


def _escape_markdown_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _section_rule() -> str:
    return "-" * 79


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def _remove_output_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return
    if path.exists():
        path.unlink()


def _source_reference_suffix(source_reference: str | None) -> str:
    return "" if source_reference is None else f" ({source_reference})"


def _markdown_source_reference_suffix(source_reference: str | None) -> str:
    return "" if source_reference is None else f" (`{source_reference}`)"


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value or None


def _display_license_name(entry: DistributionInventoryEntry) -> str:
    if entry.license_expression is not None:
        return entry.license_expression
    if entry.license_field is not None:
        return entry.license_field
    if entry.license_classifiers:
        return "; ".join(entry.license_classifiers)
    return "(missing declared license metadata)"


def _should_inline_license_text(
    entry: DistributionInventoryEntry,
    *,
    legal_file: CapturedLegalFile,
    project_license_text: str,
) -> bool:
    if entry.license_expression == "Apache-2.0":
        return False
    if legal_file.text.strip() == project_license_text.strip():
        return False
    return True


def _pipe_prefixed_lines(text: str) -> list[str]:
    return [f"| {line}" if line else "|" for line in text.rstrip("\n").splitlines()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m buildish_release_tooling.legal.release_legal"
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Repository root that contains pyproject.toml, LICENSE, and NOTICE.",
    )
    parser.add_argument(
        "--output-dir",
        default="dist-release-legal/preliminary",
        help="Directory that should receive the generated preliminary LICENSE and NOTICE drafts.",
    )
    parser.add_argument(
        "--details-output-dir",
        default="dist/release-legal-preliminary",
        help=(
            "Directory that should receive the generated inventory files and copied "
            "third-party legal texts."
        ),
    )
    parser.add_argument(
        "--distribution-path",
        action="append",
        default=[],
        help=(
            "Optional additional importlib.metadata search path. "
            "When omitted, the current interpreter environment is inspected."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the preliminary release-legal generator."""

    args = _build_parser().parse_args(argv)
    distribution_paths = tuple(Path(path).resolve() for path in args.distribution_path) or None
    for written_path in generate_release_legal_artifacts(
        project_dir=Path(args.project_dir),
        output_dir=Path(args.output_dir),
        details_output_dir=Path(args.details_output_dir),
        distribution_search_paths=distribution_paths,
    ):
        sys.stdout.write(written_path.as_posix())  # noqa: TID251
        sys.stdout.write("\n")  # noqa: TID251
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
