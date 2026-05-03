# Copyright 2026 The Apache Software Foundation
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

"""Typed registries used by generated release-tooling reference documentation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelSectionDefinition:
    """Grouping rule for one generated model-reference section."""

    title: str
    description: str
    module_prefixes: tuple[str, ...]

    def matches(self, module_name: str) -> bool:
        return any(module_name.startswith(prefix) for prefix in self.module_prefixes)


@dataclass(frozen=True, slots=True)
class ScalarReferenceEntry:
    """Reference-doc description for one exported scalar alias or literal set."""

    name: str
    base_type: str
    description: str


MODEL_SECTION_DEFINITIONS = (
    ModelSectionDefinition(
        title="Release configuration and authored override types",
        description=(
            "Consumer-owned and component-owned authored configuration models, "
            "including `release-config.yaml` and local verify-rc override payloads."
        ),
        module_prefixes=("apache_buildish_release_tooling.release.models",),
    ),
    ModelSectionDefinition(
        title="Release manifests, inventories, and verification report types",
        description=(
            "Typed Buildish release manifests, emitted verification reports, "
            "inspection-bundle payloads, and related helper contracts."
        ),
        module_prefixes=("apache_buildish_release_tooling.release.contracts",),
    ),
    ModelSectionDefinition(
        title="Internal unstable command action manifest types",
        description=(
            "Machine-readable command action manifests written for workflow coordination. "
            "These are Buildish-owned internal input/output contracts and are intentionally unstable."
        ),
        module_prefixes=("apache_buildish_release_tooling.release.command_manifests",),
    ),
    ModelSectionDefinition(
        title="Harness configuration types",
        description=(
            "Committed and resolved release-harness configuration models."
        ),
        module_prefixes=("apache_buildish_release_tooling.harness.config",),
    ),
    ModelSectionDefinition(
        title="Harness scenario and runtime result types",
        description=(
            "Harness scenario inputs, mocked tool behavior contracts, and machine-readable run results."
        ),
        module_prefixes=("apache_buildish_release_tooling.harness.models",),
    ),
    ModelSectionDefinition(
        title="Harness shim builtin payload types",
        description=(
            "Small runtime payloads used by the harness shim to emulate GitHub and other tools."
        ),
        module_prefixes=("apache_buildish_release_tooling.harness.shim_builtins",),
    ),
)


SCALAR_REFERENCE_ENTRIES = (
    ScalarReferenceEntry(
        "NonEmptyString",
        "String",
        "Trimmed string value with a minimum length of one character.",
    ),
    ScalarReferenceEntry(
        "SchemaVersionV1",
        "Literal set",
        "Current schema-version marker for Buildish v1 wire contracts.",
    ),
    ScalarReferenceEntry(
        "VerificationVerdict",
        "Literal set",
        "Verification outcome literal, currently `verified` or `failed`.",
    ),
    ScalarReferenceEntry(
        "ArtifactKind",
        "Literal set",
        "Supported signed secondary-artifact kind names.",
    ),
    ScalarReferenceEntry(
        "SecondaryVerificationKind",
        "Literal set",
        "Verification report kind names, including the synthetic invalid-entry sentinel.",
    ),
    ScalarReferenceEntry(
        "Sha256Hex",
        "String",
        "Lowercase 64-character hexadecimal SHA-256 digest.",
    ),
    ScalarReferenceEntry(
        "Sha512Hex",
        "String",
        "Lowercase 128-character hexadecimal SHA-512 digest.",
    ),
    ScalarReferenceEntry(
        "GitCommitSha",
        "String",
        "Lowercase 40-character hexadecimal Git commit SHA.",
    ),
    ScalarReferenceEntry(
        "OciContentDigest",
        "String",
        "Normalized OCI content digest in `algorithm:<hex>` form.",
    ),
    ScalarReferenceEntry(
        "SelfRepositoryCheckoutMode",
        "Literal set",
        "Harness self-repository checkout policy for the workflow repository under test.",
    ),
    ScalarReferenceEntry(
        "RepositoryOverrideCheckoutMode",
        "Literal set",
        "Harness checkout policy for an explicit repository override binding.",
    ),
    ScalarReferenceEntry(
        "HarnessBackendName",
        "Literal set",
        "Supported harness execution backend names.",
    ),
    ScalarReferenceEntry(
        "GpgFixtureMode",
        "Literal set",
        "Harness GPG fixture modes used by workflow scenarios.",
    ),
    ScalarReferenceEntry(
        "HarnessJobStatus",
        "Literal set",
        "Harness job-result status values retained in machine-readable run results.",
    ),
    ScalarReferenceEntry(
        "SvnInitialState",
        "Literal set",
        "Named harness SVN fixture presets for simulated ASF dist state.",
    ),
)
