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

"""Scenario models for the Buildish release harness."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

HarnessBackendName = Literal["custom", "act"]
SvnInitialState = Literal[
    "absent",
    "empty",
    "preexisting-current-rc",
    "preexisting-previous-rc",
    "preexisting-future-rc",
    "preexisting-other-version",
]


class WorkspaceFile(BaseModel):
    """A file that should exist in the scenario workspace before job execution starts."""

    model_config = ConfigDict(extra="forbid")

    path: str
    content: str
    executable: bool = False


class GitRepositoryFixture(BaseModel):
    """A disposable Git repository that should be initialized inside the workspace."""

    model_config = ConfigDict(extra="forbid")

    path: str
    default_branch: str = "main"
    commit_message: str = "initial commit"
    files: list[WorkspaceFile] = Field(default_factory=list)


class WorkflowRepositoryBranchFixture(BaseModel):
    """A branch that should exist in the workflow repository checkout before execution."""

    model_config = ConfigDict(extra="forbid")

    name: str
    start_point: str = "HEAD"


class WorkflowRepositoryTagFixture(BaseModel):
    """A tag that should exist in the workflow repository checkout before execution."""

    model_config = ConfigDict(extra="forbid")

    name: str
    target: str = "HEAD"
    annotated: bool = False
    message: str | None = None


class WorkflowRepositoryFixture(BaseModel):
    """Git refs that should be created in the workflow repository checkout before execution."""

    model_config = ConfigDict(extra="forbid")

    branches: list[WorkflowRepositoryBranchFixture] = Field(default_factory=list)
    tags: list[WorkflowRepositoryTagFixture] = Field(default_factory=list)


class SvnRepositoryFixture(BaseModel):
    """Initial ASF SVN state to create inside one harness `act` workspace."""

    model_config = ConfigDict(extra="forbid")

    initial_state: SvnInitialState = "absent"
    version: str | None = None
    rc_number: int = Field(default=0, ge=0)
    other_version: str | None = None
    dev_dist_entries: list[str] = Field(default_factory=list)
    release_dist_entries: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fixture_shape(self) -> SvnRepositoryFixture:
        """Reject impossible SVN preset combinations."""

        if self.initial_state == "preexisting-previous-rc" and self.rc_number < 1:
            raise ValueError("preexisting-previous-rc requires rc_number >= 1")
        if self.initial_state == "preexisting-other-version" and not self.other_version:
            raise ValueError("preexisting-other-version requires other_version")
        return self


class InvocationMatch(BaseModel):
    """A matcher for a single intercepted tool invocation."""

    model_config = ConfigDict(extra="forbid")

    argv: list[str] | None = None
    argv_prefix: list[str] | None = None
    cwd: str | None = None
    env_contains: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_match_shape(self) -> InvocationMatch:
        """Reject impossible or ambiguous matcher combinations."""

        if self.argv and self.argv_prefix:
            raise ValueError("only one of argv or argv_prefix may be specified")
        return self


class FileWriteAction(BaseModel):
    """A file write that a mocked tool invocation should perform."""

    model_config = ConfigDict(extra="forbid")

    path: str
    content: str
    executable: bool = False


class ToolBehaviorResult(BaseModel):
    """The mocked result of an intercepted tool invocation."""

    model_config = ConfigDict(extra="forbid")

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    summary: str = ""
    append_stdout_to_summary: bool = False
    delegate_to_real_tool: bool = False
    writes: list[FileWriteAction] = Field(default_factory=list)


class ToolBehavior(BaseModel):
    """A scripted behavior for an intercepted tool invocation."""

    model_config = ConfigDict(extra="forbid")

    match: InvocationMatch = Field(default_factory=InvocationMatch)
    result: ToolBehaviorResult = Field(default_factory=ToolBehaviorResult)
    times: int | None = None


class StepScenario(BaseModel):
    """A single shell step in a harness job."""

    model_config = ConfigDict(extra="forbid")

    id: str
    run: str
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    shell: str = "bash"


class JobScenario(BaseModel):
    """A job in the harness scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str
    needs: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    steps: list[StepScenario]


class WorkflowScenario(BaseModel):
    """A real workflow-YAML invocation executed by the `act` backend."""

    model_config = ConfigDict(extra="forbid")

    path: str
    event: Literal["workflow_dispatch"] = "workflow_dispatch"
    inputs: dict[str, str] = Field(default_factory=dict)
    harness_config: str
    real_cli_commands: list[str] = Field(default_factory=list)
    repository_fixture: WorkflowRepositoryFixture = Field(default_factory=WorkflowRepositoryFixture)
    svn_fixture: SvnRepositoryFixture = Field(default_factory=SvnRepositoryFixture)


class HarnessScenario(BaseModel):
    """A runner-agnostic integration-test scenario."""

    model_config = ConfigDict(extra="forbid")

    name: str
    backend: HarnessBackendName = "custom"
    env_capture: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    workspace_files: list[WorkspaceFile] = Field(default_factory=list)
    git_repositories: list[GitRepositoryFixture] = Field(default_factory=list)
    tool_behaviors: dict[str, list[ToolBehavior]] = Field(default_factory=dict)
    jobs: list[JobScenario] = Field(default_factory=list)
    workflow: WorkflowScenario | None = None

    @model_validator(mode="after")
    def validate_job_graph(self) -> HarnessScenario:
        """Ensure that job identifiers are unique and all dependencies are known."""

        if self.backend == "custom":
            if self.workflow is not None:
                raise ValueError("custom scenarios must not define a workflow block")
            if not self.jobs:
                raise ValueError("custom scenarios must define at least one job")
        elif self.workflow is None:
            raise ValueError("act scenarios must define a workflow block")
        elif self.jobs:
            raise ValueError("act scenarios must not define custom jobs")

        seen_job_ids: set[str] = set()
        for job in self.jobs:
            if job.id in seen_job_ids:
                raise ValueError(f"duplicate job id: {job.id}")
            seen_job_ids.add(job.id)
        for job in self.jobs:
            unknown_needs = [need for need in job.needs if need not in seen_job_ids]
            if unknown_needs:
                raise ValueError(f"job {job.id} references unknown needs: {', '.join(unknown_needs)}")
        return self


def ordered_job_ids(jobs: Sequence[JobScenario]) -> list[str]:
    """Return the job identifiers in declaration order."""

    return [job.id for job in jobs]
