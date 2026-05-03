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

from pydantic import ConfigDict, Field, RootModel, model_validator

from apache_buildish_release_tooling.docs.documentation import (
    ConsumerOwnedAuthoredModel,
    RuntimeDerivedModel,
    SchemaExportSpecification,
)

HarnessBackendName = Literal["custom", "act"]
GpgFixtureMode = Literal["disabled", "generated-signing-key"]
HarnessJobStatus = Literal["success", "failed", "blocked"]
SvnInitialState = Literal[
    "absent",
    "empty",
    "preexisting-current-rc",
    "preexisting-previous-rc",
    "preexisting-future-rc",
    "preexisting-other-version",
]


class WorkspaceFile(ConsumerOwnedAuthoredModel):
    """A file that should exist in the scenario workspace before job execution starts."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    content: str = Field(description="Literal file content that the harness should write or that the mocked tool should emit.")
    executable: bool = Field(default=False, description="Whether the written file should have the executable bit set in the harness workspace.")


class GitRepositoryFixture(ConsumerOwnedAuthoredModel):
    """A disposable Git repository that should be initialized inside the workspace."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    default_branch: str = Field(default="main", description="Branch name that the harness should create as the default branch in the disposable Git repository fixture.")
    commit_message: str = Field(default="initial commit", description="Commit message that the harness should use when creating the initial commit in the disposable Git repository fixture.")
    files: list[WorkspaceFile] = Field(description="Workspace files that the harness should create inside the related fixture repository before execution begins.", default_factory=list)


class WorkflowRepositoryBranchFixture(ConsumerOwnedAuthoredModel):
    """A branch that should exist in the workflow repository checkout before execution."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Stable name for the related object, branch, tag, release, or harness step.")
    start_point: str = Field(default="HEAD", description="Commit, ref, or symbolic start point that the harness should use when creating the related branch or tag.")


class WorkflowRepositoryTagFixture(ConsumerOwnedAuthoredModel):
    """A tag that should exist in the workflow repository checkout before execution."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Stable name for the related object, branch, tag, release, or harness step.")
    target: str = Field(default="HEAD", description="Target commit, ref, or identifier that the related fixture or release record should point at.")
    annotated: bool = Field(default=False, description="Whether the related Git tag fixture should be created as an annotated tag instead of a lightweight tag.")
    message: str | None = Field(default=None, description="Human-readable message body associated with the related verification failure, harness tag object, or fixture definition.")


class WorkflowRepositoryFixture(ConsumerOwnedAuthoredModel):
    """Git refs that should be created in the workflow repository checkout before execution."""

    model_config = ConfigDict(extra="forbid")

    branches: list[WorkflowRepositoryBranchFixture] = Field(description="Git branches that the harness should create in the workflow repository fixture before execution begins.", default_factory=list)
    tags: list[WorkflowRepositoryTagFixture] = Field(description="Git tags that the harness should create in the workflow repository fixture before execution begins.", default_factory=list)


class SvnRepositoryFixture(ConsumerOwnedAuthoredModel):
    """Initial ASF SVN state to create inside one harness `act` workspace."""

    model_config = ConfigDict(extra="forbid")

    initial_state: SvnInitialState = Field(default="absent", description="Named SVN fixture preset that describes what ASF dist state the harness should create before the run begins.")
    version: str | None = Field(default=None, description="Release version string without a leading `v` prefix.")
    rc_number: int = Field(description="Numeric RC sequence selected for the related version.", default=0, ge=0)
    other_version: str | None = Field(default=None, description="Additional release version that the SVN harness fixture should materialize for preset scenarios that require another version line.")
    dev_dist_entries: list[str] = Field(description="Initial SVN entries that the harness should create under the simulated ASF `dist/dev` tree.", default_factory=list)
    release_dist_entries: list[str] = Field(description="Initial SVN entries that the harness should create under the simulated ASF `dist/release` tree.", default_factory=list)
    repository_files: list[WorkspaceFile] = Field(description="Files that the harness should create inside the simulated SVN repository fixture before execution begins.", default_factory=list)

    @model_validator(mode="after")
    def validate_fixture_shape(self) -> SvnRepositoryFixture:
        """Reject impossible SVN preset combinations."""

        if self.initial_state == "preexisting-previous-rc" and self.rc_number < 1:
            raise ValueError("preexisting-previous-rc requires rc_number >= 1")
        if self.initial_state == "preexisting-other-version" and not self.other_version:
            raise ValueError("preexisting-other-version requires other_version")
        return self


class InvocationMatch(ConsumerOwnedAuthoredModel):
    """A matcher for a single intercepted tool invocation."""

    model_config = ConfigDict(extra="forbid")

    argv: list[str] | None = Field(default=None, description="Exact argv list that the harness should match or that it recorded for the related command invocation.")
    argv_prefix: list[str] | None = Field(default=None, description="Command-line prefix that the intercepted argv list must start with before the harness behavior matches.")
    argv_contains: list[str] = Field(description="Command-line fragments that must appear somewhere in the intercepted argv list before the harness behavior matches.", default_factory=list)
    cwd: str | None = Field(default=None, description="Working directory that the harness should use or that it observed for the related command invocation.")
    env_contains: dict[str, str] = Field(description="Subset of required environment entries that a harness tool matcher must observe.", default_factory=dict)

    @model_validator(mode="after")
    def validate_match_shape(self) -> InvocationMatch:
        """Reject impossible or ambiguous matcher combinations."""

        if self.argv and self.argv_prefix:
            raise ValueError("only one of argv or argv_prefix may be specified")
        return self


class FileWriteAction(ConsumerOwnedAuthoredModel):
    """A file write that a mocked tool invocation should perform."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    content: str = Field(description="Literal file content that the harness should write or that the mocked tool should emit.")
    executable: bool = Field(default=False, description="Whether the written file should have the executable bit set in the harness workspace.")


class ToolBehaviorResult(ConsumerOwnedAuthoredModel):
    """The mocked result of an intercepted tool invocation."""

    model_config = ConfigDict(extra="forbid")

    exit_code: int = Field(default=0, description="Process exit code that the harness recorded or should synthesize for the related tool invocation.")
    stdout: str = Field(default="", description="Captured stdout that the harness recorded or should synthesize for the related tool invocation.")
    stderr: str = Field(default="", description="Captured stderr that the harness recorded or should synthesize for the related tool invocation.")
    summary: str = Field(default="", description="Human-readable short summary for the related result or mocked tool behavior.")
    append_stdout_to_summary: bool = Field(default=False, description="Whether the harness should append mocked stdout to the rendered step or job summary output.")
    delegate_to_real_tool: bool = Field(default=False, description="Whether the harness should fall through to the real external tool instead of returning the mocked result directly.")
    writes: list[FileWriteAction] = Field(description="Files that the mocked tool behavior should write when the invocation matches.", default_factory=list)


class ToolBehavior(ConsumerOwnedAuthoredModel):
    """A scripted behavior for an intercepted tool invocation."""

    model_config = ConfigDict(extra="forbid")

    match: InvocationMatch = Field(description="Tool-invocation matcher that decides when the related scripted harness behavior should be applied.", default_factory=InvocationMatch)
    result: ToolBehaviorResult = Field(description="Scripted harness tool result that should be returned when the matching invocation is observed.", default_factory=ToolBehaviorResult)
    times: int | None = Field(default=None, description="Maximum number of times that the harness should apply the scripted tool behavior before it stops matching.")


class HarnessBuiltinGhTagObject(RuntimeDerivedModel):
    """Synthetic GitHub tag-object payload retained by the harness shim."""

    model_config = ConfigDict(extra="allow")

    tag: str | None = Field(default=None, description="Tag name associated with the related release, workflow fixture, or synthetic GitHub tag-object payload.")
    message: str | None = Field(default=None, description="Human-readable message body associated with the related verification failure, harness tag object, or fixture definition.")
    object: str | None = Field(default=None, description="Git object SHA that the synthetic annotated-tag payload ultimately points at.")


class HarnessShimState(RuntimeDerivedModel):
    """Persisted subprocess-facing harness shim state."""

    model_config = ConfigDict(extra="forbid")

    workspace_root: str = Field(description="Filesystem path of the harness workspace root used by the persisted shim state.")
    trace_file: str = Field(description="Filesystem path where the harness shim appends structured command trace entries.")
    env_capture: list[str] = Field(description="Environment variable names that the harness shim should retain in trace output.", default_factory=list)
    tool_behaviors: dict[str, list[ToolBehavior]] = Field(description="Scripted intercepted-tool behaviors keyed by tool name in the related harness scenario or runtime state.", default_factory=dict)
    counts: dict[str, int] = Field(description="Per-tool or per-key invocation counts retained in harness runtime state.", default_factory=dict)
    gh_tag_objects: dict[str, HarnessBuiltinGhTagObject] = Field(description="Synthetic GitHub annotated-tag payloads persisted in harness shim state for later ref mutation handling.", default_factory=dict)


class StepScenario(ConsumerOwnedAuthoredModel):
    """A single shell step in a harness job."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for the related harness job, step, or scenario element.")
    run: str = Field(description="Shell command body that the harness should execute for the related step.")
    cwd: str | None = Field(default=None, description="Working directory that the harness should use or that it observed for the related command invocation.")
    env: dict[str, str] = Field(description="Environment-variable mapping supplied to the related build, scenario, or command step.", default_factory=dict)
    shell: str = Field(default="bash", description="Shell executable name or mode that the harness should use for the related step.")


class JobScenario(ConsumerOwnedAuthoredModel):
    """A job in the harness scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for the related harness job, step, or scenario element.")
    needs: list[str] = Field(description="Job ids that must complete successfully before the related harness job is allowed to run.", default_factory=list)
    env: dict[str, str] = Field(description="Environment-variable mapping supplied to the related build, scenario, or command step.", default_factory=dict)
    steps: list[StepScenario] = Field(description="Ordered shell steps that the harness should run for the related custom job.")


class WorkflowScenario(ConsumerOwnedAuthoredModel):
    """A real workflow-YAML invocation executed by the `act` backend."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Filesystem path, relative artifact path, or retained evidence path associated with the related record.")
    event: Literal["workflow_dispatch"] = Field(default="workflow_dispatch", description="Workflow event name that the harness should simulate for the related workflow scenario.")
    inputs: dict[str, str] = Field(description="Workflow-dispatch inputs that the harness should pass to the selected workflow invocation.", default_factory=dict)
    harness_config: str = Field(description="Path to the harness configuration file that the `act` workflow scenario should load.")
    real_cli_commands: list[str] = Field(description="External CLI command names that the `act` harness workflow may run directly instead of through shim wrappers.", default_factory=list)
    repository_fixture: WorkflowRepositoryFixture = Field(description="Workflow-repository ref fixture that the harness should materialize before running the selected workflow.", default_factory=WorkflowRepositoryFixture)
    gpg_fixture: GpgFixtureMode = Field(default="disabled", description="GPG fixture mode that the harness should prepare for the related workflow scenario.")
    svn_fixture: SvnRepositoryFixture = Field(description="SVN fixture preset that the `act` workflow scenario should create before execution begins.", default_factory=SvnRepositoryFixture)


class HarnessScenario(ConsumerOwnedAuthoredModel):
    """A runner-agnostic integration-test scenario."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Stable name for the related object, branch, tag, release, or harness step.")
    backend: HarnessBackendName = Field(default="custom", description="Execution backend name that performed the related Buildish action or reproducibility run.")
    env_capture: list[str] = Field(description="Environment variable names that the harness shim should retain in trace output.", default_factory=list)
    env: dict[str, str] = Field(description="Environment-variable mapping supplied to the related build, scenario, or command step.", default_factory=dict)
    secrets: dict[str, str] = Field(description="Secret environment variables that the harness should expose to the scenario while keeping them logically separate from ordinary environment variables.", default_factory=dict)
    workspace_files: list[WorkspaceFile] = Field(description="Files that the harness should create directly in the scenario workspace before execution begins.", default_factory=list)
    git_repositories: list[GitRepositoryFixture] = Field(description="Disposable Git repositories that the harness should create in the scenario workspace before execution begins.", default_factory=list)
    tool_behaviors: dict[str, list[ToolBehavior]] = Field(description="Scripted intercepted-tool behaviors keyed by tool name in the related harness scenario or runtime state.", default_factory=dict)
    jobs: list[JobScenario] = Field(description="Jobs that the harness should execute for the related custom scenario.", default_factory=list)
    workflow: WorkflowScenario | None = Field(default=None, description="Nested workflow block for an `act` harness scenario, or the workflow name recorded in provenance.")

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


class HarnessCommandTraceEntry(RuntimeDerivedModel):
    """One persisted command-trace entry recorded by harness tool shims."""

    model_config = ConfigDict(extra="forbid")

    tool: str = Field(description="Tool name associated with the recorded harness command trace entry.")
    argv: list[str] = Field(description="Exact argv list that the harness should match or that it recorded for the related command invocation.", default_factory=list)
    cwd: str = Field(description="Working directory that the harness should use or that it observed for the related command invocation.")
    env: dict[str, str] = Field(description="Environment-variable mapping supplied to the related build, scenario, or command step.", default_factory=dict)
    exit_code: int = Field(description="Process exit code that the harness recorded or should synthesize for the related tool invocation.")
    stdout: str = Field(default="", description="Captured stdout that the harness recorded or should synthesize for the related tool invocation.")
    stderr: str = Field(default="", description="Captured stderr that the harness recorded or should synthesize for the related tool invocation.")
    delegated: bool = Field(default=False, description="Whether the recorded harness command invocation delegated to the real tool implementation.")


class HarnessJobStatusesFile(RootModel[dict[str, HarnessJobStatus]]):
    """Persisted per-job harness execution statuses."""

    root: dict[str, HarnessJobStatus] = Field(
        description="Final per-job status map emitted by the harness for the reported workflow or sequence run."
    )


class HarnessInspectablePaths(RuntimeDerivedModel):
    """Stable inspectable workspace paths exposed by the harness CLI."""

    model_config = ConfigDict(extra="forbid")

    workspace_root: str = Field(description="Filesystem path of the harness workspace root used by the persisted shim state.")
    primary_git_checkout: str = Field(description="Harness workspace path of the primary repository checkout used for the workflow-under-test.")
    rewritten_workflows: str = Field(description="Harness workspace path that contains workflow YAML files rewritten for local execution.")
    harness_root: str = Field(description="Harness workspace path that contains persisted harness state, rewritten workflows, and generated helper files.")
    generated_actions: str = Field(description="Harness workspace path that contains generated helper scripts or wrapper actions.")
    repo_sources: str = Field(description="Harness workspace path that contains repository source templates or seed inputs used to build fixture checkouts.")
    git_origins: str = Field(description="Harness workspace path that contains the origin repositories used to seed local Git checkouts.")
    self_git_origin: str = Field(description="Harness workspace path of the local Git origin repository used to simulate GitHub-side mutations for the primary repository.")
    git_checkouts: str = Field(description="Harness workspace path that contains generated Git working-copy checkouts.")
    svn_root: str = Field(description="Harness workspace path that contains all simulated SVN repository and working-copy state.")
    svn_repository: str = Field(description="Harness workspace path that contains the simulated backing SVN repository state.")
    svn_working_copy: str = Field(description="Harness workspace path of the simulated SVN working copy used during the run.")
    step_summaries: str = Field(description="Harness workspace path that contains per-step summary files emitted during the run.")
    job_summaries: str = Field(description="Harness workspace path that contains one rendered markdown or text summary per job.")
    job_statuses: str = Field(description="Final per-job status map emitted by the harness for the reported workflow or sequence run.")
    command_trace: str = Field(description="Harness workspace path of the structured command-trace log emitted during the run.")


class HarnessRunResultJson(RuntimeDerivedModel):
    """Machine-readable JSON payload for one harness run or rerun."""

    model_config = ConfigDict(extra="forbid")

    workspace: str = Field(description="Filesystem path of the harness workspace directory for the related run.")
    inspectable_paths: HarnessInspectablePaths = Field(description="Paths that a harness caller can inspect after the run to understand rewritten workflows, summaries, and persisted state.")
    selected_job_ids: list[str] = Field(description="Harness job ids selected for execution in the reported run.", default_factory=list)
    failed_job_ids: list[str] = Field(description="Harness job ids that finished with a failure outcome in the reported run.", default_factory=list)
    blocked_job_ids: list[str] = Field(description="Harness job ids that were not run because an upstream dependency failed or was blocked.", default_factory=list)
    job_statuses: dict[str, HarnessJobStatus] = Field(description="Final per-job status map emitted by the harness for the reported workflow or sequence run.", default_factory=dict)


class HarnessSequenceEntryJson(RuntimeDerivedModel):
    """One sequence-run entry returned by the harness CLI."""

    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(description="Scenario name associated with the related harness sequence result entry.")
    workspace: str = Field(description="Filesystem path of the harness workspace directory for the related run.")
    inspectable_paths: HarnessInspectablePaths = Field(description="Paths that a harness caller can inspect after the run to understand rewritten workflows, summaries, and persisted state.")
    selected_job_ids: list[str] = Field(description="Harness job ids selected for execution in the reported run.", default_factory=list)
    failed_job_ids: list[str] = Field(description="Harness job ids that finished with a failure outcome in the reported run.", default_factory=list)
    blocked_job_ids: list[str] = Field(description="Harness job ids that were not run because an upstream dependency failed or was blocked.", default_factory=list)
    job_statuses: dict[str, HarnessJobStatus] = Field(description="Final per-job status map emitted by the harness for the reported workflow or sequence run.", default_factory=dict)


class HarnessSequenceRunResultJson(RuntimeDerivedModel):
    """Machine-readable JSON payload for one harness sequence run."""

    model_config = ConfigDict(extra="forbid")

    sequence: list[HarnessSequenceEntryJson] = Field(description="Ordered per-scenario results retained for one multi-scenario harness sequence run.", default_factory=list)
    final_workspace: str = Field(description="Filesystem path of the final harness workspace retained after a multi-scenario sequence run.")


def ordered_job_ids(jobs: Sequence[JobScenario]) -> list[str]:
    """Return the job identifiers in declaration order."""

    return [job.id for job in jobs]


HarnessShimState.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Persisted subprocess-facing harness shim state used by intercepted tool wrappers.",
)
HarnessScenario.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    file_path="harness/scenarios/*.yaml",
    summary="Harness scenario contract for synthetic or `act`-backed release-workflow integration tests.",
)
HarnessCommandTraceEntry.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Structured command-trace record emitted by the harness shim for one intercepted invocation.",
)
HarnessRunResultJson.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Machine-readable JSON result for one harness scenario run.",
)
HarnessSequenceRunResultJson.schema_export = SchemaExportSpecification(
    audience="internal",
    stability="stable",
    summary="Machine-readable JSON result for a multi-scenario harness sequence run.",
)
