# Copyright 2026 The Buildish Authors
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

"""Shared job-selection helpers for Buildish release-harness backends."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def rerunnable_job_ids(
    ordered_job_ids: Sequence[str],
    needs_by_job: Mapping[str, Sequence[str]],
    statuses: Mapping[str, str],
) -> list[str]:
    """Return failed or blocked jobs and all downstream dependents in dependency order."""

    failed_or_blocked = {
        job_id for job_id, status in statuses.items() if status in {"failed", "blocked"}
    }
    if not failed_or_blocked:
        return []
    dependents: dict[str, set[str]] = {job_id: set() for job_id in ordered_job_ids}
    for job_id, needs in needs_by_job.items():
        for need in needs:
            dependents.setdefault(need, set()).add(job_id)
    selected = set(failed_or_blocked)
    stack = list(failed_or_blocked)
    while stack:
        current = stack.pop()
        for dependent in dependents.get(current, set()):
            if dependent not in selected:
                selected.add(dependent)
                stack.append(dependent)
    return [job_id for job_id in ordered_job_ids if job_id in selected]
