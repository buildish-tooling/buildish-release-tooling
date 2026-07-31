---
title: "Harness scenario and runtime result types"
description: "Harness scenario inputs, mocked tool behavior contracts, and machine-readable run results."
---

<!--
Copyright 2026 The Buildish Authors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

Harness scenario inputs, mocked tool behavior contracts, and machine-readable run results.

Back to the [reference overview](../release-model-schema-reference/).

## Type index

- [FileWriteAction](#filewriteaction) — A file write that a mocked tool invocation should perform.
- [GitRepositoryFixture](#gitrepositoryfixture) — A disposable Git repository that should be initialized inside the workspace.
- [HarnessBuiltinGhRelease](#harnessbuiltinghrelease) — Synthetic GitHub Release retained by the stateful harness shim.
- [HarnessBuiltinGhReleaseAsset](#harnessbuiltinghreleaseasset) — Synthetic GitHub Release asset retained by the stateful harness shim.
- [HarnessBuiltinGhTagObject](#harnessbuiltinghtagobject) — Synthetic GitHub tag-object payload retained by the harness shim.
- [HarnessCommandTraceEntry](#harnesscommandtraceentry) — One persisted command-trace entry recorded by harness tool shims.
- [HarnessInspectablePaths](#harnessinspectablepaths) — Stable inspectable workspace paths exposed by the harness CLI.
- [HarnessRunResultJson](#harnessrunresultjson) — Machine-readable JSON payload for one harness run or rerun.
- [HarnessScenario](#harnessscenario) — A runner-agnostic integration-test scenario.
- [HarnessSequenceEntryJson](#harnesssequenceentryjson) — One sequence-run entry returned by the harness CLI.
- [HarnessSequenceRunResultJson](#harnesssequencerunresultjson) — Machine-readable JSON payload for one harness sequence run.
- [HarnessShimState](#harnessshimstate) — Persisted subprocess-facing harness shim state.
- [InvocationMatch](#invocationmatch) — A matcher for a single intercepted tool invocation.
- [JobScenario](#jobscenario) — A job in the harness scenario.
- [StepScenario](#stepscenario) — A single shell step in a harness job.
- [SvnRepositoryFixture](#svnrepositoryfixture) — Initial ASF SVN state to create inside one harness `act` workspace.
- [ToolBehavior](#toolbehavior) — A scripted behavior for an intercepted tool invocation.
- [ToolBehaviorResult](#toolbehaviorresult) — The mocked result of an intercepted tool invocation.
- [WorkflowRepositoryBranchFixture](#workflowrepositorybranchfixture) — A branch that should exist in the workflow repository checkout before execution.
- [WorkflowRepositoryFixture](#workflowrepositoryfixture) — Git refs that should be created in the workflow repository checkout before execution.
- [WorkflowRepositoryTagFixture](#workflowrepositorytagfixture) — A tag that should exist in the workflow repository checkout before execution.
- [WorkflowScenario](#workflowscenario) — A real workflow-YAML invocation executed by the `act` backend.
- [WorkspaceFile](#workspacefile) — A file that should exist in the scenario workspace before job execution starts.

<a id="filewriteaction"></a>
### FileWriteAction

A file write that a mocked tool invocation should perform.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="filewriteaction-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="filewriteaction-content"></a>`content` | str | yes | Literal file content that the harness should write or that the mocked tool should emit. |
| <a id="filewriteaction-executable"></a>`executable` | bool | no | Whether the written file should have the executable bit set in the harness workspace. |

<a id="gitrepositoryfixture"></a>
### GitRepositoryFixture

A disposable Git repository that should be initialized inside the workspace.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="gitrepositoryfixture-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="gitrepositoryfixture-default-branch"></a>`default_branch` | str | no | Branch name that the harness should create as the default branch in the disposable Git repository fixture. |
| <a id="gitrepositoryfixture-commit-message"></a>`commit_message` | str | no | Commit message that the harness should use when creating the initial commit in the disposable Git repository fixture. |
| <a id="gitrepositoryfixture-files"></a>`files` | list[[WorkspaceFile](#workspacefile)] | no | Workspace files that the harness should create inside the related fixture repository before execution begins. |

<a id="harnessbuiltinghrelease"></a>
### HarnessBuiltinGhRelease

Synthetic GitHub Release retained by the stateful harness shim.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessbuiltinghrelease-id"></a>`id` | int | yes | Synthetic GitHub Release identifier. |
| <a id="harnessbuiltinghrelease-repository"></a>`repository` | str | yes | GitHub repository identity associated with the release. |
| <a id="harnessbuiltinghrelease-tag-name"></a>`tag_name` | str | yes | Exact tag associated with the release. |
| <a id="harnessbuiltinghrelease-name"></a>`name` | str | yes | Release title. |
| <a id="harnessbuiltinghrelease-body"></a>`body` | str | yes | Release body. |
| <a id="harnessbuiltinghrelease-draft"></a>`draft` | bool | yes | Whether the release remains a draft. |
| <a id="harnessbuiltinghrelease-prerelease"></a>`prerelease` | bool | yes | Whether the release is a prerelease. |
| <a id="harnessbuiltinghrelease-html-url"></a>`html_url` | str | yes | Synthetic browser-facing release URL. |
| <a id="harnessbuiltinghrelease-url"></a>`url` | str | yes | Synthetic API-facing release URL. |
| <a id="harnessbuiltinghrelease-assets"></a>`assets` | list[[HarnessBuiltinGhReleaseAsset](#harnessbuiltinghreleaseasset)] | no | Synthetic assets currently attached to the retained GitHub Release. |

<a id="harnessbuiltinghreleaseasset"></a>
### HarnessBuiltinGhReleaseAsset

Synthetic GitHub Release asset retained by the stateful harness shim.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessbuiltinghreleaseasset-id"></a>`id` | int | yes | Synthetic GitHub Release asset identifier. |
| <a id="harnessbuiltinghreleaseasset-name"></a>`name` | str | yes | Release asset basename. |
| <a id="harnessbuiltinghreleaseasset-size"></a>`size` | int | yes | Release asset size in bytes. |
| <a id="harnessbuiltinghreleaseasset-digest"></a>`digest` | str | yes | GitHub-style algorithm-prefixed asset digest. |
| <a id="harnessbuiltinghreleaseasset-stored-path"></a>`stored_path` | str | yes | Workspace-relative path containing the retained bytes. |

<a id="harnessbuiltinghtagobject"></a>
### HarnessBuiltinGhTagObject

Synthetic GitHub tag-object payload retained by the harness shim.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessbuiltinghtagobject-tag"></a>`tag` | str | no | Tag name associated with the related release, workflow fixture, or synthetic GitHub tag-object payload. |
| <a id="harnessbuiltinghtagobject-message"></a>`message` | str | no | Human-readable message body associated with the related verification failure, harness tag object, or fixture definition. |
| <a id="harnessbuiltinghtagobject-object"></a>`object` | str | no | Git object SHA that the synthetic annotated-tag payload ultimately points at. |

<a id="harnesscommandtraceentry"></a>
### HarnessCommandTraceEntry

One persisted command-trace entry recorded by harness tool shims.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`harness-command-trace-entry.schema.json`](/components/release-tooling/schemas/harness-command-trace-entry.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnesscommandtraceentry-tool"></a>`tool` | str | yes | Tool name associated with the recorded harness command trace entry. |
| <a id="harnesscommandtraceentry-argv"></a>`argv` | list[str] | no | Exact argv list that the harness should match or that it recorded for the related command invocation. |
| <a id="harnesscommandtraceentry-cwd"></a>`cwd` | str | yes | Working directory that the harness should use or that it observed for the related command invocation. |
| <a id="harnesscommandtraceentry-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="harnesscommandtraceentry-exit-code"></a>`exit_code` | int | yes | Process exit code that the harness recorded or should synthesize for the related tool invocation. |
| <a id="harnesscommandtraceentry-stdout"></a>`stdout` | str | no | Captured stdout that the harness recorded or should synthesize for the related tool invocation. |
| <a id="harnesscommandtraceentry-stderr"></a>`stderr` | str | no | Captured stderr that the harness recorded or should synthesize for the related tool invocation. |
| <a id="harnesscommandtraceentry-delegated"></a>`delegated` | bool | no | Whether the recorded harness command invocation delegated to the real tool implementation. |

<a id="harnessinspectablepaths"></a>
### HarnessInspectablePaths

Stable inspectable workspace paths exposed by the harness CLI.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessinspectablepaths-workspace-root"></a>`workspace_root` | str | yes | Filesystem path of the harness workspace root used by the persisted shim state. |
| <a id="harnessinspectablepaths-primary-git-checkout"></a>`primary_git_checkout` | str | yes | Harness workspace path of the primary repository checkout used for the workflow-under-test. |
| <a id="harnessinspectablepaths-rewritten-workflows"></a>`rewritten_workflows` | str | yes | Harness workspace path that contains workflow YAML files rewritten for local execution. |
| <a id="harnessinspectablepaths-harness-root"></a>`harness_root` | str | yes | Harness workspace path that contains persisted harness state, rewritten workflows, and generated helper files. |
| <a id="harnessinspectablepaths-generated-actions"></a>`generated_actions` | str | yes | Harness workspace path that contains generated helper scripts or wrapper actions. |
| <a id="harnessinspectablepaths-repo-sources"></a>`repo_sources` | str | yes | Harness workspace path that contains repository source templates or seed inputs used to build fixture checkouts. |
| <a id="harnessinspectablepaths-git-origins"></a>`git_origins` | str | yes | Harness workspace path that contains the origin repositories used to seed local Git checkouts. |
| <a id="harnessinspectablepaths-self-git-origin"></a>`self_git_origin` | str | yes | Harness workspace path of the local Git origin repository used to simulate GitHub-side mutations for the primary repository. |
| <a id="harnessinspectablepaths-git-checkouts"></a>`git_checkouts` | str | yes | Harness workspace path that contains generated Git working-copy checkouts. |
| <a id="harnessinspectablepaths-svn-root"></a>`svn_root` | str | yes | Harness workspace path that contains all simulated SVN repository and working-copy state. |
| <a id="harnessinspectablepaths-svn-repository"></a>`svn_repository` | str | yes | Harness workspace path that contains the simulated backing SVN repository state. |
| <a id="harnessinspectablepaths-svn-working-copy"></a>`svn_working_copy` | str | yes | Harness workspace path of the simulated SVN working copy used during the run. |
| <a id="harnessinspectablepaths-step-summaries"></a>`step_summaries` | str | yes | Harness workspace path that contains per-step summary files emitted during the run. |
| <a id="harnessinspectablepaths-job-summaries"></a>`job_summaries` | str | yes | Harness workspace path that contains one rendered markdown or text summary per job. |
| <a id="harnessinspectablepaths-job-statuses"></a>`job_statuses` | str | yes | Final per-job status map emitted by the harness for the reported workflow or sequence run. |
| <a id="harnessinspectablepaths-command-trace"></a>`command_trace` | str | yes | Harness workspace path of the structured command-trace log emitted during the run. |

<a id="harnessrunresultjson"></a>
### HarnessRunResultJson

Machine-readable JSON payload for one harness run or rerun.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`harness-run-result-json.schema.json`](/components/release-tooling/schemas/harness-run-result-json.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessrunresultjson-workspace"></a>`workspace` | str | yes | Filesystem path of the harness workspace directory for the related run. |
| <a id="harnessrunresultjson-inspectable-paths"></a>`inspectable_paths` | [HarnessInspectablePaths](#harnessinspectablepaths) | yes | Paths that a harness caller can inspect after the run to understand rewritten workflows, summaries, and persisted state. |
| <a id="harnessrunresultjson-selected-job-ids"></a>`selected_job_ids` | list[str] | no | Harness job ids selected for execution in the reported run. |
| <a id="harnessrunresultjson-failed-job-ids"></a>`failed_job_ids` | list[str] | no | Harness job ids that finished with a failure outcome in the reported run. |
| <a id="harnessrunresultjson-blocked-job-ids"></a>`blocked_job_ids` | list[str] | no | Harness job ids that were not run because an upstream dependency failed or was blocked. |
| <a id="harnessrunresultjson-job-statuses"></a>`job_statuses` | dict[str, [HarnessJobStatus](../release-shared-types-reference/#harnessjobstatus)] | no | Final per-job status map emitted by the harness for the reported workflow or sequence run. |

<a id="harnessscenario"></a>
### HarnessScenario

A runner-agnostic integration-test scenario.

- category: `authored`
- ownership: `consumer-owned`
- schema file: [`harness-scenario.schema.json`](/components/release-tooling/schemas/harness-scenario.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: `harness/scenarios/*.yaml`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessscenario-name"></a>`name` | str | yes | Stable name for the related object, branch, tag, release, or harness step. |
| <a id="harnessscenario-backend"></a>`backend` | [HarnessBackendName](../release-shared-types-reference/#harnessbackendname) | no | Execution backend name that performed the related Buildish action or reproducibility run. |
| <a id="harnessscenario-env-capture"></a>`env_capture` | list[str] | no | Environment variable names that the harness shim should retain in trace output. |
| <a id="harnessscenario-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="harnessscenario-secrets"></a>`secrets` | dict[str, str] | no | Secret environment variables that the harness should expose to the scenario while keeping them logically separate from ordinary environment variables. |
| <a id="harnessscenario-workspace-files"></a>`workspace_files` | list[[WorkspaceFile](#workspacefile)] | no | Files that the harness should create directly in the scenario workspace before execution begins. |
| <a id="harnessscenario-git-repositories"></a>`git_repositories` | list[[GitRepositoryFixture](#gitrepositoryfixture)] | no | Disposable Git repositories that the harness should create in the scenario workspace before execution begins. |
| <a id="harnessscenario-tool-behaviors"></a>`tool_behaviors` | dict[str, list[[ToolBehavior](#toolbehavior)]] | no | Scripted intercepted-tool behaviors keyed by tool name in the related harness scenario or runtime state. |
| <a id="harnessscenario-jobs"></a>`jobs` | list[[JobScenario](#jobscenario)] | no | Jobs that the harness should execute for the related custom scenario. |
| <a id="harnessscenario-workflow"></a>`workflow` | [WorkflowScenario](#workflowscenario) | no | Nested workflow block for an `act` harness scenario, or the workflow name recorded in provenance. |

<a id="harnesssequenceentryjson"></a>
### HarnessSequenceEntryJson

One sequence-run entry returned by the harness CLI.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnesssequenceentryjson-scenario"></a>`scenario` | str | yes | Scenario name associated with the related harness sequence result entry. |
| <a id="harnesssequenceentryjson-workspace"></a>`workspace` | str | yes | Filesystem path of the harness workspace directory for the related run. |
| <a id="harnesssequenceentryjson-inspectable-paths"></a>`inspectable_paths` | [HarnessInspectablePaths](#harnessinspectablepaths) | yes | Paths that a harness caller can inspect after the run to understand rewritten workflows, summaries, and persisted state. |
| <a id="harnesssequenceentryjson-selected-job-ids"></a>`selected_job_ids` | list[str] | no | Harness job ids selected for execution in the reported run. |
| <a id="harnesssequenceentryjson-failed-job-ids"></a>`failed_job_ids` | list[str] | no | Harness job ids that finished with a failure outcome in the reported run. |
| <a id="harnesssequenceentryjson-blocked-job-ids"></a>`blocked_job_ids` | list[str] | no | Harness job ids that were not run because an upstream dependency failed or was blocked. |
| <a id="harnesssequenceentryjson-job-statuses"></a>`job_statuses` | dict[str, [HarnessJobStatus](../release-shared-types-reference/#harnessjobstatus)] | no | Final per-job status map emitted by the harness for the reported workflow or sequence run. |

<a id="harnesssequencerunresultjson"></a>
### HarnessSequenceRunResultJson

Machine-readable JSON payload for one harness sequence run.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`harness-sequence-run-result-json.schema.json`](/components/release-tooling/schemas/harness-sequence-run-result-json.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnesssequencerunresultjson-sequence"></a>`sequence` | list[[HarnessSequenceEntryJson](#harnesssequenceentryjson)] | no | Ordered per-scenario results retained for one multi-scenario harness sequence run. |
| <a id="harnesssequencerunresultjson-final-workspace"></a>`final_workspace` | str | yes | Filesystem path of the final harness workspace retained after a multi-scenario sequence run. |

<a id="harnessshimstate"></a>
### HarnessShimState

Persisted subprocess-facing harness shim state.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`harness-shim-state.schema.json`](/components/release-tooling/schemas/harness-shim-state.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessshimstate-workspace-root"></a>`workspace_root` | str | yes | Filesystem path of the harness workspace root used by the persisted shim state. |
| <a id="harnessshimstate-trace-file"></a>`trace_file` | str | yes | Filesystem path where the harness shim appends structured command trace entries. |
| <a id="harnessshimstate-env-capture"></a>`env_capture` | list[str] | no | Environment variable names that the harness shim should retain in trace output. |
| <a id="harnessshimstate-tool-behaviors"></a>`tool_behaviors` | dict[str, list[[ToolBehavior](#toolbehavior)]] | no | Scripted intercepted-tool behaviors keyed by tool name in the related harness scenario or runtime state. |
| <a id="harnessshimstate-counts"></a>`counts` | dict[str, int] | no | Per-tool or per-key invocation counts retained in harness runtime state. |
| <a id="harnessshimstate-gh-tag-objects"></a>`gh_tag_objects` | dict[str, [HarnessBuiltinGhTagObject](#harnessbuiltinghtagobject)] | no | Synthetic GitHub annotated-tag payloads persisted in harness shim state for later ref mutation handling. |
| <a id="harnessshimstate-gh-releases"></a>`gh_releases` | dict[str, [HarnessBuiltinGhRelease](#harnessbuiltinghrelease)] | no | Synthetic GitHub Releases keyed by exact tag. |
| <a id="harnessshimstate-gh-next-release-id"></a>`gh_next_release_id` | int | no | Next synthetic GitHub Release identifier allocated by the stateful shim. |
| <a id="harnessshimstate-gh-next-asset-id"></a>`gh_next_asset_id` | int | no | Next synthetic GitHub Release asset identifier allocated by the stateful shim. |

<a id="invocationmatch"></a>
### InvocationMatch

A matcher for a single intercepted tool invocation.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="invocationmatch-argv"></a>`argv` | list[str] | no | Exact argv list that the harness should match or that it recorded for the related command invocation. |
| <a id="invocationmatch-argv-prefix"></a>`argv_prefix` | list[str] | no | Command-line prefix that the intercepted argv list must start with before the harness behavior matches. |
| <a id="invocationmatch-argv-contains"></a>`argv_contains` | list[str] | no | Command-line fragments that must appear somewhere in the intercepted argv list before the harness behavior matches. |
| <a id="invocationmatch-cwd"></a>`cwd` | str | no | Working directory that the harness should use or that it observed for the related command invocation. |
| <a id="invocationmatch-env-contains"></a>`env_contains` | dict[str, str] | no | Subset of required environment entries that a harness tool matcher must observe. |

<a id="jobscenario"></a>
### JobScenario

A job in the harness scenario.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="jobscenario-id"></a>`id` | str | yes | Stable identifier for the related harness job, step, or scenario element. |
| <a id="jobscenario-needs"></a>`needs` | list[str] | no | Job ids that must complete successfully before the related harness job is allowed to run. |
| <a id="jobscenario-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="jobscenario-steps"></a>`steps` | list[[StepScenario](#stepscenario)] | yes | Ordered shell steps that the harness should run for the related custom job. |

<a id="stepscenario"></a>
### StepScenario

A single shell step in a harness job.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="stepscenario-id"></a>`id` | str | yes | Stable identifier for the related harness job, step, or scenario element. |
| <a id="stepscenario-run"></a>`run` | str | yes | Shell command body that the harness should execute for the related step. |
| <a id="stepscenario-cwd"></a>`cwd` | str | no | Working directory that the harness should use or that it observed for the related command invocation. |
| <a id="stepscenario-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="stepscenario-shell"></a>`shell` | str | no | Shell executable name or mode that the harness should use for the related step. |

<a id="svnrepositoryfixture"></a>
### SvnRepositoryFixture

Initial ASF SVN state to create inside one harness `act` workspace.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="svnrepositoryfixture-initial-state"></a>`initial_state` | [SvnInitialState](../release-shared-types-reference/#svninitialstate) | no | Named SVN fixture preset that describes what ASF dist state the harness should create before the run begins. |
| <a id="svnrepositoryfixture-version"></a>`version` | str | no | Release version string without a leading `v` prefix. |
| <a id="svnrepositoryfixture-rc-number"></a>`rc_number` | int | no | Numeric RC sequence selected for the related version. |
| <a id="svnrepositoryfixture-other-version"></a>`other_version` | str | no | Additional release version that the SVN harness fixture should materialize for preset scenarios that require another version line. |
| <a id="svnrepositoryfixture-dev-dist-entries"></a>`dev_dist_entries` | list[str] | no | Initial SVN entries that the harness should create under the simulated ASF `dist/dev` tree. |
| <a id="svnrepositoryfixture-release-dist-entries"></a>`release_dist_entries` | list[str] | no | Initial SVN entries that the harness should create under the simulated ASF `dist/release` tree. |
| <a id="svnrepositoryfixture-repository-files"></a>`repository_files` | list[[WorkspaceFile](#workspacefile)] | no | Files that the harness should create inside the simulated SVN repository fixture before execution begins. |

<a id="toolbehavior"></a>
### ToolBehavior

A scripted behavior for an intercepted tool invocation.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="toolbehavior-match"></a>`match` | [InvocationMatch](#invocationmatch) | no | Tool-invocation matcher that decides when the related scripted harness behavior should be applied. |
| <a id="toolbehavior-result"></a>`result` | [ToolBehaviorResult](#toolbehaviorresult) | no | Scripted harness tool result that should be returned when the matching invocation is observed. |
| <a id="toolbehavior-times"></a>`times` | int | no | Maximum number of times that the harness should apply the scripted tool behavior before it stops matching. |

<a id="toolbehaviorresult"></a>
### ToolBehaviorResult

The mocked result of an intercepted tool invocation.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="toolbehaviorresult-exit-code"></a>`exit_code` | int | no | Process exit code that the harness recorded or should synthesize for the related tool invocation. |
| <a id="toolbehaviorresult-stdout"></a>`stdout` | str | no | Captured stdout that the harness recorded or should synthesize for the related tool invocation. |
| <a id="toolbehaviorresult-stderr"></a>`stderr` | str | no | Captured stderr that the harness recorded or should synthesize for the related tool invocation. |
| <a id="toolbehaviorresult-summary"></a>`summary` | str | no | Human-readable short summary for the related result or mocked tool behavior. |
| <a id="toolbehaviorresult-append-stdout-to-summary"></a>`append_stdout_to_summary` | bool | no | Whether the harness should append mocked stdout to the rendered step or job summary output. |
| <a id="toolbehaviorresult-delegate-to-real-tool"></a>`delegate_to_real_tool` | bool | no | Whether the harness should fall through to the real external tool instead of returning the mocked result directly. |
| <a id="toolbehaviorresult-writes"></a>`writes` | list[[FileWriteAction](#filewriteaction)] | no | Files that the mocked tool behavior should write when the invocation matches. |

<a id="workflowrepositorybranchfixture"></a>
### WorkflowRepositoryBranchFixture

A branch that should exist in the workflow repository checkout before execution.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowrepositorybranchfixture-name"></a>`name` | str | yes | Stable name for the related object, branch, tag, release, or harness step. |
| <a id="workflowrepositorybranchfixture-start-point"></a>`start_point` | str | no | Commit, ref, or symbolic start point that the harness should use when creating the related branch or tag. |

<a id="workflowrepositoryfixture"></a>
### WorkflowRepositoryFixture

Git refs that should be created in the workflow repository checkout before execution.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowrepositoryfixture-branches"></a>`branches` | list[[WorkflowRepositoryBranchFixture](#workflowrepositorybranchfixture)] | no | Git branches that the harness should create in the workflow repository fixture before execution begins. |
| <a id="workflowrepositoryfixture-tags"></a>`tags` | list[[WorkflowRepositoryTagFixture](#workflowrepositorytagfixture)] | no | Git tags that the harness should create in the workflow repository fixture before execution begins. |

<a id="workflowrepositorytagfixture"></a>
### WorkflowRepositoryTagFixture

A tag that should exist in the workflow repository checkout before execution.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowrepositorytagfixture-name"></a>`name` | str | yes | Stable name for the related object, branch, tag, release, or harness step. |
| <a id="workflowrepositorytagfixture-target"></a>`target` | str | no | Target commit, ref, or identifier that the related fixture or release record should point at. |
| <a id="workflowrepositorytagfixture-annotated"></a>`annotated` | bool | no | Whether the related Git tag fixture should be created as an annotated tag instead of a lightweight tag. |
| <a id="workflowrepositorytagfixture-message"></a>`message` | str | no | Human-readable message body associated with the related verification failure, harness tag object, or fixture definition. |

<a id="workflowscenario"></a>
### WorkflowScenario

A real workflow-YAML invocation executed by the `act` backend.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowscenario-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="workflowscenario-event"></a>`event` | Literal['workflow_dispatch'] | no | Workflow event name that the harness should simulate for the related workflow scenario. |
| <a id="workflowscenario-inputs"></a>`inputs` | dict[str, str] | no | Workflow-dispatch inputs that the harness should pass to the selected workflow invocation. |
| <a id="workflowscenario-harness-config"></a>`harness_config` | str | yes | Path to the harness configuration file that the `act` workflow scenario should load. |
| <a id="workflowscenario-release-config"></a>`release_config` | dict[str, object] | no | Optional complete release configuration used only inside the disposable workflow workspace. |
| <a id="workflowscenario-real-cli-commands"></a>`real_cli_commands` | list[str] | no | External CLI command names that the `act` harness workflow may run directly instead of through shim wrappers. |
| <a id="workflowscenario-repository-fixture"></a>`repository_fixture` | [WorkflowRepositoryFixture](#workflowrepositoryfixture) | no | Workflow-repository ref fixture that the harness should materialize before running the selected workflow. |
| <a id="workflowscenario-gpg-fixture"></a>`gpg_fixture` | [GpgFixtureMode](../release-shared-types-reference/#gpgfixturemode) | no | GPG fixture mode that the harness should prepare for the related workflow scenario. |
| <a id="workflowscenario-svn-fixture"></a>`svn_fixture` | [SvnRepositoryFixture](#svnrepositoryfixture) | no | SVN fixture preset that the `act` workflow scenario should create before execution begins. |

<a id="workspacefile"></a>
### WorkspaceFile

A file that should exist in the scenario workspace before job execution starts.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workspacefile-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="workspacefile-content"></a>`content` | str | yes | Literal file content that the harness should write or that the mocked tool should emit. |
| <a id="workspacefile-executable"></a>`executable` | bool | no | Whether the written file should have the executable bit set in the harness workspace. |

