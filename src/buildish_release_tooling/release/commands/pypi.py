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

"""CLI orchestration for the PyPI publication adapter."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from buildish_release_tooling.release.commands._shared import (
    _append_github_outputs,
    _context,
    _manifest_path,
)
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.publications.pypi.verification import (
    verify_pypi_publication,
)
from buildish_release_tooling.release.publications.pypi.config import (
    PyPiPublicationConfig,
)
from buildish_release_tooling.release.publications.pypi.attestations import (
    verify_pypi_attestations,
)
from buildish_release_tooling.release.summary import SummaryWriter


def run_verify_pypi_publication(args: Namespace) -> Path:
    """Verify and record exact distributions published through the PyPI API."""

    context = _context(args)
    targets = [
        target
        for target in context.release_config.publication.secondary
        if isinstance(target, PyPiPublicationConfig)
    ]
    if len(targets) != 1:
        raise ValueError(
            "verify-pypi-publication requires exactly one configured PyPI secondary target"
        )
    result = verify_pypi_publication(
        args,
        component_id=context.release_config.component.id,
        config=targets[0],
    )
    result_path = _manifest_path(result.component, result.action)
    write_manifest(result_path, result, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Verify PyPI publication")
    summary.append_plaintext_block("Project", result.project_name)
    summary.append_plaintext_block("Version", result.version)
    summary.append_plaintext_block("State", result.publication_state)
    summary.append_plaintext_block("Files", str(len(result.published_files)))
    _append_github_outputs({"publication_state": result.publication_state})
    return result_path


def run_verify_pypi_attestations(args: Namespace) -> Path:
    """Verify and record PEP 740 provenance for configured PyPI distributions."""

    context = _context(args)
    targets = [
        target
        for target in context.release_config.publication.secondary
        if isinstance(target, PyPiPublicationConfig)
    ]
    if len(targets) != 1:
        raise ValueError(
            "verify-pypi-attestations requires exactly one configured PyPI secondary target"
        )
    result = verify_pypi_attestations(
        args,
        component_id=context.release_config.component.id,
        config=targets[0],
    )
    result_path = _manifest_path(result.component, result.action)
    write_manifest(result_path, result, exclude_none=True)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Verify PyPI attestations")
    summary.append_plaintext_block("Project", result.project_name)
    summary.append_plaintext_block("Version", result.version)
    summary.append_plaintext_block("Files", str(len(result.files)))
    return result_path
