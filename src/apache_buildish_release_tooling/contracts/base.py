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

"""Shared conventions for Buildish-owned file and wire contracts."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict


class BuildishContractModel(BaseModel):
    """Base model for Buildish-owned persisted contracts."""

    model_config = ConfigDict(extra="forbid")
    contract_documentation: ClassVar[object | None] = None

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Return the generated JSON Schema with Buildish documentation metadata injected."""

        schema = super().model_json_schema(*args, **kwargs)
        from apache_buildish_release_tooling.docs.documentation import (
            apply_documentation_to_schema,
        )

        return apply_documentation_to_schema(cls, schema)
