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

"""Formal Python distribution identity helpers owned by the PyPI adapter."""

from __future__ import annotations

from packaging.utils import InvalidSdistFilename, InvalidWheelFilename
from packaging.utils import (
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version

from buildish_release_tooling.release.publications._adapter import (
    DURABLE_EVIDENCE_ASSET_PREFIX,
)


def pypi_publish_attestation_asset_name(distribution_filename: str) -> str:
    """Return the canonical durable evidence name for one distribution."""

    return (
        f"{DURABLE_EVIDENCE_ASSET_PREFIX}"
        f"{distribution_filename}.publish-attestations.json"
    )


def normalized_pypi_version(version: str) -> str:
    """Return the canonical PEP 440 spelling for one Buildish release version."""

    try:
        return str(Version(version))
    except InvalidVersion as exc:
        raise ValueError(
            f"release version is not representable on PyPI: {version}"
        ) from exc


def is_project_distribution(filename: str, *, project_name: str, version: str) -> bool:
    """Return whether a wheel or sdist filename names this exact project version."""

    try:
        if filename.endswith(".whl"):
            parsed_name, parsed_version, _build, _tags = parse_wheel_filename(filename)
        elif filename.endswith(".tar.gz"):
            parsed_name, parsed_version = parse_sdist_filename(filename)
        else:
            return False
    except (InvalidWheelFilename, InvalidSdistFilename):
        return False
    return parsed_name == canonicalize_name(project_name) and str(
        parsed_version
    ) == normalized_pypi_version(version)
