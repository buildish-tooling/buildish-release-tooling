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

"""Shared release communication text blocks."""

from __future__ import annotations

from apache_buildish_release_tooling.release.models import ComponentConfig


def default_incubator_disclaimer(
    *,
    project_name: str,
    sponsor_name: str,
) -> str:
    """Render the standard Apache Incubator disclaimer text."""

    return "\n\n".join(
        [
            (
                f"{project_name} is an effort undergoing incubation at The Apache Software "
                f"Foundation (ASF), sponsored by {sponsor_name}. Incubation is required "
                "of all newly accepted projects until a further review indicates that the "
                "infrastructure, communications, and decision making process have "
                "stabilized in a manner consistent with other successful ASF projects."
            ),
            (
                "While incubation status is not necessarily a reflection of the "
                "completeness or stability of the code, it does indicate that the "
                "project has yet to be fully endorsed by the ASF."
            ),
        ]
    )


def incubator_disclaimer_text(component_config: ComponentConfig) -> str:
    """Return the configured or default incubator disclaimer text."""

    if component_config.incubator_disclaimer is not None:
        return component_config.incubator_disclaimer.strip()
    return default_incubator_disclaimer(
        project_name=component_config.vote_release_name,
        sponsor_name=component_config.incubator_sponsor_name,
    )


def incubator_disclaimer_section(component_config: ComponentConfig, *, heading: str) -> str:
    """Render an incubator disclaimer section, or an empty string for non-podlings."""

    if not component_config.is_incubating:
        return ""
    return f"{heading}\n\n{incubator_disclaimer_text(component_config)}"
