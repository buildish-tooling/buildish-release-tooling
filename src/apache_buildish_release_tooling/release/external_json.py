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

"""Shared helpers for tolerant external JSON payload readers."""

from __future__ import annotations

import json
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def parse_json_object(payload_text: str | bytes, *, source: str) -> dict[str, object]:
    """Parse one external JSON payload and require a top-level object."""

    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError(f"{source} did not return a JSON object payload")
    return cast(dict[str, object], payload)


def validate_json_object_model(
    model_type: type[_ModelT],
    payload: object,
    *,
    source: str,
    expected_payload: str,
) -> _ModelT:
    """Validate one already-parsed top-level JSON object against a tolerant model."""

    if not isinstance(payload, dict):
        raise ValueError(f"{source} did not return a JSON object payload")
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{source} returned a malformed {expected_payload} payload") from exc


def validate_json_object_model_text(
    model_type: type[_ModelT],
    payload_text: str | bytes,
    *,
    source: str,
    expected_payload: str,
) -> _ModelT:
    """Parse and validate one external JSON object payload against a tolerant model."""

    return validate_json_object_model(
        model_type,
        parse_json_object(payload_text, source=source),
        source=source,
        expected_payload=expected_payload,
    )
