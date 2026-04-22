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

"""Shared bounded structured-file parsing helpers."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import TypeVar, cast

import yaml
from pydantic import BaseModel, ValidationError

from buildish_release_tooling.shared.io import read_text_file_bounded

DEFAULT_CONFIG_PARSE_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_MANIFEST_PARSE_MAX_BYTES = 25 * 1024 * 1024

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def read_json_file_bounded(path: Path, *, max_bytes: int) -> object:
    """Read and parse a bounded JSON file."""

    text = read_text_file_bounded(path, max_bytes=max_bytes)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}") from exc


def read_json_object_file_bounded(path: Path, *, max_bytes: int) -> dict[str, object]:
    """Read and parse a bounded JSON file that must contain a top-level object."""

    payload = read_json_file_bounded(path, max_bytes=max_bytes)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return cast(dict[str, object], payload)


def read_pydantic_json_file_bounded(
    model_type: type[_ModelT],
    path: Path,
    *,
    max_bytes: int,
) -> _ModelT:
    """Read bounded JSON text and validate it against a Pydantic model."""

    text = read_text_file_bounded(path, max_bytes=max_bytes)
    try:
        return model_type.model_validate_json(text)
    except ValidationError as exc:
        raise ValueError(f"invalid {model_type.__name__} JSON in {path}") from exc


def read_yaml_file_bounded(path: Path, *, max_bytes: int) -> object:
    """Read and parse a bounded YAML file."""

    text = read_text_file_bounded(path, max_bytes=max_bytes)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc


def read_yaml_mapping_file_bounded(path: Path, *, max_bytes: int) -> dict[str, object]:
    """Read and parse a bounded YAML file that must contain a top-level mapping."""

    payload = read_yaml_file_bounded(path, max_bytes=max_bytes)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"expected a YAML mapping in {path}")
    return cast(dict[str, object], payload)


def read_toml_file_bounded(path: Path, *, max_bytes: int) -> dict[str, object]:
    """Read and parse a bounded TOML file."""

    text = read_text_file_bounded(path, max_bytes=max_bytes)
    try:
        return cast(dict[str, object], tomllib.loads(text))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML in {path}") from exc
