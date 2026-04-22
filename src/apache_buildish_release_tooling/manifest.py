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

"""Manifest emission helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def write_manifest(path: Path, entries: Mapping[str, Any]) -> None:
    """Write a JSON manifest file for a workflow step."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dict(entries), handle, indent=2)
        handle.write("\n")
