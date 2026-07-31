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

"""Shared release communication text blocks."""

from __future__ import annotations

import hashlib
from pathlib import Path

from buildish_release_tooling.release.contracts import IncubatorDisclaimer
from buildish_release_tooling.release.config import ReleaseConfig, require_asf_profile


def resolved_incubator_disclaimer(
    component_config: ReleaseConfig,
    *,
    project_root: Path,
) -> IncubatorDisclaimer | None:
    """Read and snapshot the Incubator disclaimer text for an incubating component."""

    if not require_asf_profile(component_config).is_incubating:
        return None
    source_path = Path(require_asf_profile(component_config).disclaimer_file)
    disclaimer_path = project_root / source_path
    if not disclaimer_path.is_file():
        raise ValueError(f"incubator disclaimer file does not exist: {disclaimer_path}")
    disclaimer_text = disclaimer_path.read_text(encoding="utf-8").strip()
    if not disclaimer_text:
        raise ValueError(f"incubator disclaimer file is empty: {disclaimer_path}")
    return IncubatorDisclaimer(
        source_path=source_path.as_posix(),
        text=disclaimer_text,
        sha512=hashlib.sha512(disclaimer_text.encode("utf-8")).hexdigest(),
    )


def incubator_disclaimer_section(
    incubator_disclaimer: IncubatorDisclaimer | None,
    *,
    heading: str,
) -> str:
    """Render an incubator disclaimer section, or an empty string for non-podlings."""

    if incubator_disclaimer is None:
        return ""
    return f"{heading}\n\n{incubator_disclaimer.text}"
