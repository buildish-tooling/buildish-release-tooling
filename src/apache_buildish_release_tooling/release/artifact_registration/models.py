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

"""Common models for secondary-artifact registration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from apache_buildish_release_tooling.release.contracts import (
    AnySecondaryArtifact,
    SecondaryArtifactManifestV1,
)

@dataclass(frozen=True)
class ArtifactRegistrationResult:
    """Typed result returned by one artifact-kind handler."""

    secondary_artifact: AnySecondaryArtifact
    inventory_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ArtifactRegistrationBundle:
    """Written registration bundle for one artifact registration command run."""

    bundle_dir: Path
    manifest_path: Path
    manifest_payload: SecondaryArtifactManifestV1
    inventory_paths: tuple[Path, ...] = field(default_factory=tuple)
