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

"""PyPI-specific authored publication configuration."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from buildish_release_tooling.docs.documentation import ComponentOwnedAuthoredModel


class PyPiTrustedPublisherConfig(ComponentOwnedAuthoredModel):
    """Expected GitHub Trusted Publisher identity for one PyPI target."""

    kind: Literal["GitHub"] = Field(
        default="GitHub",
        description="PyPI Trusted Publisher kind.",
    )
    repository: str = Field(
        min_length=1, description="GitHub owner/repository identity."
    )
    workflow: str = Field(
        min_length=1, description="GitHub workflow filename identity."
    )
    environment: str = Field(min_length=1, description="GitHub Environment identity.")


class PyPiPublicationConfig(ComponentOwnedAuthoredModel):
    """Secondary publication to PyPI or TestPyPI."""

    kind: Literal["pypi"] = Field(
        default="pypi",
        description="Secondary publication target discriminator.",
    )
    project_name: str = Field(min_length=1, description="PyPI project name.")
    repository_api_url: str = Field(
        default="https://pypi.org/pypi",
        min_length=1,
        description="PyPI JSON API base URL.",
    )
    project_url_template: str = Field(
        default="https://pypi.org/project/{project}/{version}/",
        min_length=1,
        description="Immutable project-version URL template.",
    )
    integrity_api_url: str = Field(
        default="https://pypi.org/integrity",
        min_length=1,
        description="PyPI Integrity API base URL.",
    )
    trusted_publisher: PyPiTrustedPublisherConfig = Field(
        description="Exact Trusted Publisher identity required for provenance."
    )

    @model_validator(mode="after")
    def validate_urls(self) -> PyPiPublicationConfig:
        """Require canonical HTTPS service URLs and an exact URL template."""

        for field_name, value in (
            ("repository_api_url", self.repository_api_url),
            ("integrity_api_url", self.integrity_api_url),
        ):
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(f"PyPI {field_name} must be an absolute HTTPS URL")
        if (
            self.project_url_template.count("{project}") != 1
            or self.project_url_template.count("{version}") != 1
        ):
            raise ValueError(
                "PyPI project_url_template must contain {project} and {version} exactly once"
            )
        try:
            rendered = self.project_url_template.format(
                project="project", version="1.0.0"
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(
                "PyPI project_url_template has unsupported placeholders"
            ) from exc
        parsed_template = urlparse(rendered)
        if parsed_template.scheme != "https" or not parsed_template.netloc:
            raise ValueError(
                "PyPI project_url_template must render an absolute HTTPS URL"
            )
        return self
