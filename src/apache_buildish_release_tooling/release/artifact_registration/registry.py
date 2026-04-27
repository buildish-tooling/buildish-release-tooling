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

"""Registry for typed artifact-registration handlers."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable
from pathlib import Path

from apache_buildish_release_tooling.release.artifact_registration.kinds.generic_file import (
    build_generic_file_registration,
)
from apache_buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)

ArtifactRegistrationHandler = Callable[[Namespace, Path], ArtifactRegistrationResult]

_HANDLERS: dict[str, ArtifactRegistrationHandler] = {
    "generic-file": build_generic_file_registration,
}


def registered_artifact_kinds() -> tuple[str, ...]:
    """Return the supported artifact-registration kind names."""

    return tuple(sorted(_HANDLERS))


def build_artifact_registration(args: Namespace, bundle_dir: Path) -> ArtifactRegistrationResult:
    """Dispatch one artifact-registration request to the selected kind handler."""

    try:
        handler = _HANDLERS[args.kind]
    except KeyError as exc:
        supported = ", ".join(registered_artifact_kinds()) or "<none>"
        raise ValueError(f"unsupported artifact kind: {args.kind} (supported kinds: {supported})") from exc
    return handler(args, bundle_dir)
