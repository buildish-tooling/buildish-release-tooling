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

"""Backend registry for the Buildish release harness."""

from __future__ import annotations

from apache_buildish_release_tooling.harness.backends.act import ACT_BACKEND
from apache_buildish_release_tooling.harness.backends.base import Backend
from apache_buildish_release_tooling.harness.backends.custom import CUSTOM_BACKEND
from apache_buildish_release_tooling.harness.models import HarnessBackendName

_BACKENDS: dict[HarnessBackendName, Backend] = {
    CUSTOM_BACKEND.name: CUSTOM_BACKEND,
    ACT_BACKEND.name: ACT_BACKEND,
}


def get_backend(name: HarnessBackendName) -> Backend:
    """Return one registered backend by name."""

    return _BACKENDS[name]


def supported_backends() -> tuple[HarnessBackendName, ...]:
    """Return the backend names exposed by the harness CLI."""

    return tuple(_BACKENDS)


__all__ = [
    "ACT_BACKEND",
    "CUSTOM_BACKEND",
    "Backend",
    "get_backend",
    "supported_backends",
]
