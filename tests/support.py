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

"""Shared test support for buildish-release-tooling."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

import yaml


def component_root() -> Path:
    """Return the root directory of the buildish-release-tooling component."""

    return Path(__file__).resolve().parent.parent


def fixture_root() -> Path:
    """Return the root directory for checked-in test fixtures."""

    return component_root() / "tests" / "fixtures"


def fixture_component_dir(component_id: str) -> Path:
    """Return the directory of a checked-in fixture component by identifier."""

    return fixture_root() / "components" / component_id


def fixture_component_config_path(component_id: str) -> Path:
    """Return the checked-in fixture release-config path for a component."""

    return fixture_component_dir(component_id) / "buildish-release-tooling" / "release-config.yaml"


def fixture_component_dispatcher_path(component_id: str) -> Path:
    """Return the checked-in fixture bash dispatcher path for a component."""

    return fixture_component_dir(component_id) / "buildish-release-tooling" / "release-tooling.sh"


def write_fixture_component_config(
    component_id: str,
    destination_path: Path,
    *,
    asf_dist_dev_base: str,
    asf_dist_release_base: str,
) -> Path:
    """Write a copy of a fixture component config with test-specific ASF SVN URLs."""

    payload = yaml.safe_load(fixture_component_config_path(component_id).read_text(encoding="utf-8")) or {}
    payload["asf_dist_dev_base"] = asf_dist_dev_base
    payload["asf_dist_release_base"] = asf_dist_release_base
    destination_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return destination_path


def create_build_test_sandbox() -> Path:
    """Create a repo-local test sandbox under `build/`."""

    sandbox_root = component_root() / "build" / "tests"
    sandbox_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="sandbox.", dir=sandbox_root))


def cleanup_sandbox(path: Path) -> None:
    """Remove a previously created sandbox directory."""

    shutil.rmtree(path, ignore_errors=True)


def init_git_origin_and_clone(sandbox_dir: Path) -> tuple[Path, Path]:
    """Create a disposable Git origin/clone pair for integration tests."""

    origin_dir = sandbox_dir / "origin"
    clone_dir = sandbox_dir / "clone"
    subprocess.run(["git", "init", "--initial-branch=main", str(origin_dir)], check=True)
    subprocess.run(
        ["git", "-C", str(origin_dir), "config", "user.name", "Release Tooling Tests"], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(origin_dir),
            "config",
            "user.email",
            "release-tooling-tests@example.invalid",
        ],
        check=True,
    )
    (origin_dir / "README.txt").write_text("root\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(origin_dir), "add", "README.txt"], check=True)
    subprocess.run(["git", "-C", str(origin_dir), "commit", "-m", "initial commit"], check=True)
    subprocess.run(["git", "clone", str(origin_dir), str(clone_dir)], check=True)
    subprocess.run(
        ["git", "-C", str(clone_dir), "config", "user.name", "Release Tooling Tests"], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(clone_dir),
            "config",
            "user.email",
            "release-tooling-tests@example.invalid",
        ],
        check=True,
    )
    return origin_dir, clone_dir


def fetch_git_origin_refs(clone_dir: Path) -> None:
    """Fetch remote heads and tags into a disposable clone."""

    subprocess.run(
        [
            "git",
            "-C",
            str(clone_dir),
            "fetch",
            "--force",
            "--prune",
            "--tags",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
        ],
        check=True,
    )


def set_github_origin_url(repo_dir: Path, repository_slug: str) -> None:
    """Rewrite `origin` to a GitHub URL for GitHub CLI integration tests."""

    subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "remote",
            "set-url",
            "origin",
            f"https://github.com/{repository_slug}.git",
        ],
        check=True,
    )


def git_create_branch(repo_dir: Path, branch_name: str, source_ref: str = "main") -> None:
    """Create a branch inside a disposable Git repository."""

    subprocess.run(
        ["git", "-C", str(repo_dir), "branch", branch_name, source_ref],
        check=True,
    )


def git_create_annotated_tag(repo_dir: Path, tag_name: str, source_ref: str = "main") -> None:
    """Create an annotated tag inside a disposable Git repository."""

    subprocess.run(
        ["git", "-C", str(repo_dir), "tag", "-a", tag_name, "-m", tag_name, source_ref],
        check=True,
    )


def git_rev_parse(repo_dir: Path, ref: str) -> str:
    """Resolve a Git ref to its commit SHA inside a disposable repository."""

    return subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", ref],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def init_svn_repo_and_checkout(sandbox_dir: Path) -> tuple[Path, str, Path]:
    """Create a detached local SVN repository and a checked-out working copy."""

    repo_dir = sandbox_dir / "svnrepo"
    working_copy_dir = sandbox_dir / "svnwc"
    repo_url = f"file://{repo_dir}"
    subprocess.run(["svnadmin", "create", str(repo_dir)], check=True)
    for path in (
        "dist",
        "dist/dev",
        "dist/dev/incubator",
        "dist/dev/incubator/buildish",
        "dist/release",
        "dist/release/incubator",
        "dist/release/incubator/buildish",
    ):
        subprocess.run(["svn", "mkdir", "-m", f"create {path}", f"{repo_url}/{path}"], check=True)
    subprocess.run(["svn", "checkout", repo_url, str(working_copy_dir)], check=True)
    return repo_dir, repo_url, working_copy_dir


def command_available(command_name: str) -> bool:
    """Return whether an external command is available on the current PATH."""

    return shutil.which(command_name) is not None


def tool_env(extra_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an environment that lets subprocesses import the local tooling sources."""

    env = dict(os.environ)
    pythonpath_parts = [str(component_root() / "src")]
    if existing := env.get("PYTHONPATH"):
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if extra_env is not None:
        env.update(extra_env)
    return env


def env_with_prepend_path(
    extra_env: Mapping[str, str] | None = None,
    *,
    prepend_dirs: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Return env overrides with explicit PATH prepends applied."""

    env = dict(extra_env or {})
    existing_path = env.get("PATH") or os.environ.get("PATH", "")
    path_parts = [str(path) for path in prepend_dirs]
    if existing_path:
        path_parts.append(existing_path)
    deduplicated_parts: list[str] = []
    for part in path_parts:
        if part and part not in deduplicated_parts:
            deduplicated_parts.append(part)
    env["PATH"] = os.pathsep.join(deduplicated_parts)
    return env


def cli_env(
    manifest_path: Path,
    *,
    extra_env: Mapping[str, str] | None = None,
    prepend_dirs: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Return explicit env overrides for CLI tests that require manifest and summary paths."""

    env = {
        "MANIFEST_PATH": str(manifest_path),
        "GITHUB_STEP_SUMMARY": str(manifest_path.with_suffix(".summary.md")),
    }
    if extra_env is not None:
        env.update(extra_env)
    return env_with_prepend_path(env, prepend_dirs=prepend_dirs)


def create_fake_uv_launcher(sandbox_dir: Path) -> Path:
    """Create a lightweight `uv` shim for dispatcher subprocess smoke tests."""

    launcher_dir = sandbox_dir / "bin"
    launcher_path = launcher_dir / "uv"
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'if [[ "${1:-}" != "run" ]]; then',
                '  printf "fake uv only supports \'uv run\'\\n" >&2',
                "  exit 2",
                "fi",
                "shift",
                'project_dir=""',
                'while [[ $# -gt 0 ]]; do',
                '  case "$1" in',
                '    --project)',
                '      project_dir="$2"',
                "      shift 2",
                "      ;;",
                "    --frozen)",
                "      shift",
                "      ;;",
                "    buildish-release-tooling)",
                "      shift",
                '      if [[ -z "$project_dir" ]]; then',
                '        printf "fake uv requires --project\\n" >&2',
                "        exit 2",
                "      fi",
                '      export PYTHONPATH="$project_dir/src${PYTHONPATH:+:$PYTHONPATH}"',
                '      exec "${BUILDISH_TEST_PYTHON:?}" -m apache_buildish_release_tooling "$@"',
                "      ;;",
                "    *)",
                '      printf "unexpected fake uv arguments: %s\\n" "$*" >&2',
                "      exit 2",
                "      ;;",
                "  esac",
                "done",
                'printf "fake uv did not receive a command\\n" >&2',
                "exit 2",
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)
    return launcher_dir


def create_fake_act_launcher(sandbox_dir: Path) -> tuple[Path, Path]:
    """Create a lightweight `act` shim that records invocations and writes job-status files."""

    state_dir = sandbox_dir / "fake-act"
    launcher_dir = sandbox_dir / "act-bin"
    launcher_path = launcher_dir / "act"
    state_dir.mkdir(parents=True, exist_ok=True)
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher_path.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                "from __future__ import annotations",
                "",
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                "import yaml",
                "",
                "",
                "def normalize_needs(raw_needs: object) -> list[str]:",
                "    if raw_needs is None:",
                "        return []",
                "    if isinstance(raw_needs, str):",
                "        return [raw_needs]",
                "    if isinstance(raw_needs, list):",
                "        return [str(item) for item in raw_needs]",
                "    raise SystemExit(f'unsupported fake act needs value: {raw_needs!r}')",
                "",
                "",
                "def ordered_jobs(jobs: dict[str, dict[str, object]], selected: set[str]) -> list[str]:",
                "    ordered: list[str] = []",
                "    resolved: set[str] = set()",
                "    pending = dict(jobs)",
                "    while pending:",
                "        progress_made = False",
                "        for job_id, payload in jobs.items():",
                "            if job_id not in pending or job_id not in selected:",
                "                if job_id in pending and job_id not in selected:",
                "                    del pending[job_id]",
                "                continue",
                "            needs = [need for need in normalize_needs(payload.get('needs')) if need in selected]",
                "            if all(need in resolved for need in needs):",
                "                ordered.append(job_id)",
                "                resolved.add(job_id)",
                "                del pending[job_id]",
                "                progress_made = True",
                "        if not progress_made:",
                "            raise SystemExit(f'cyclic fake act jobs: {sorted(pending)}')",
                "    return ordered",
                "",
                "",
                "def main() -> int:",
                "    state_dir = Path(os.environ['FAKE_ACT_STATE_DIR'])",
                "    workflow_path = ''",
                "    event_path = ''",
                "    secret_file = ''",
                "    selected_jobs: list[str] = []",
                "    event_name = ''",
                "    args = sys.argv[1:]",
                "    index = 0",
                "    while index < len(args):",
                "        current = args[index]",
                "        if not current.startswith('-') and not event_name:",
                "            event_name = current",
                "            index += 1",
                "            continue",
                "        if current in ('-W', '--workflows'):",
                "            workflow_path = args[index + 1]",
                "            index += 2",
                "            continue",
                "        if current in ('-e', '--eventpath'):",
                "            event_path = args[index + 1]",
                "            index += 2",
                "            continue",
                "        if current in ('-j', '--job'):",
                "            selected_jobs.append(args[index + 1])",
                "            index += 2",
                "            continue",
                "        if current == '--secret-file':",
                "            secret_file = args[index + 1]",
                "            index += 2",
                "            continue",
                "        index += 1",
                "    payload = yaml.safe_load(Path(workflow_path).read_text(encoding='utf-8')) or {}",
                "    jobs = payload.get('jobs') or {}",
                "    if not isinstance(jobs, dict):",
                "        raise SystemExit('fake act expected a jobs mapping')",
                "    selected = set(selected_jobs or jobs.keys())",
                "    ordered = ordered_jobs({str(job_id): dict(job_payload) for job_id, job_payload in jobs.items()}, selected)",
                "    state_path = state_dir / 'state.json'",
                "    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'runs': 0}",
                "    state['runs'] = int(state.get('runs', 0)) + 1",
                "    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding='utf-8')",
                "    invocation_path = state_dir / f\"invocation-{state['runs']}.json\"",
                "    invocation_path.write_text(",
                "        json.dumps(",
                "            {",
                "                'argv': sys.argv[1:],",
                "                'cwd': os.getcwd(),",
                "                'workflow_path': workflow_path,",
                "                'event_path': event_path,",
                "                'secret_file': secret_file,",
                "                'event_name': event_name,",
                "                'selected_jobs': list(selected_jobs),",
                "            },",
                "            indent=2,",
                "            sort_keys=True,",
                "        ),",
                "        encoding='utf-8',",
                "    )",
                "    fail_once_job = os.environ.get('FAKE_ACT_FAIL_ONCE_JOB')",
                "    stdout_text = os.environ.get('FAKE_ACT_STDOUT_TEXT', '')",
                "    stderr_text = os.environ.get('FAKE_ACT_STDERR_TEXT', '')",
                "    should_fail_once = fail_once_job and state['runs'] == 1",
                "    status_dir = Path(os.getcwd()) / '.buildish-release-harness' / 'job-statuses'",
                "    status_dir.mkdir(parents=True, exist_ok=True)",
                "    if stdout_text:",
                "        sys.stdout.write(stdout_text)",
                "    if stderr_text:",
                "        sys.stderr.write(stderr_text)",
                "    failed = False",
                "    for job_id in ordered:",
                "        if failed:",
                "            break",
                "        status_path = status_dir / f'{job_id}.status'",
                "        if should_fail_once and job_id == fail_once_job:",
                "            status_path.write_text('failure\\n', encoding='utf-8')",
                "            failed = True",
                "            continue",
                "        status_path.write_text('success\\n', encoding='utf-8')",
                "    return 1 if failed else 0",
                "",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)
    return launcher_dir, state_dir


def create_fake_gh_launcher(
    sandbox_dir: Path,
    *,
    list_response: object,
    create_response: object | None = None,
    update_release_response: object | None = None,
    create_tag_response: object | None = None,
    create_ref_response: object | None = None,
    update_ref_response: object | None = None,
) -> tuple[Path, Path]:
    """Create a lightweight `gh` shim for deterministic API and release-upload behavior."""

    state_dir = sandbox_dir / "fake-gh"
    launcher_dir = sandbox_dir / "gh-bin"
    launcher_path = launcher_dir / "gh"
    state_dir.mkdir(parents=True, exist_ok=True)
    launcher_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "list-releases.json").write_text(json.dumps(list_response), encoding="utf-8")
    (state_dir / "create-release-response.json").write_text(
        json.dumps(create_response if create_response is not None else {}),
        encoding="utf-8",
    )
    (state_dir / "update-release-response.json").write_text(
        json.dumps(update_release_response if update_release_response is not None else {}),
        encoding="utf-8",
    )
    (state_dir / "create-tag-response.json").write_text(
        json.dumps(create_tag_response if create_tag_response is not None else {}),
        encoding="utf-8",
    )
    (state_dir / "create-ref-response.json").write_text(
        json.dumps(create_ref_response if create_ref_response is not None else {}),
        encoding="utf-8",
    )
    (state_dir / "update-ref-response.json").write_text(
        json.dumps(update_ref_response if update_ref_response is not None else {}),
        encoding="utf-8",
    )
    launcher_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'state_dir="${FAKE_GH_STATE_DIR:?}"',
                'if [[ "${1:-}" == "release" && "${2:-}" == "upload" ]]; then',
                "  shift 2",
                '  tag="${1:-}"',
                '  if [[ -z "$tag" ]]; then',
                '    printf "fake gh release upload requires a tag\\n" >&2',
                "    exit 2",
                "  fi",
                "  shift",
                '  repo=""',
                '  clobber="false"',
                '  : > "$state_dir/release-upload-files.log"',
                '  while [[ $# -gt 0 ]]; do',
                '    case "$1" in',
                '      -R|--repo)',
                '        repo="$2"',
                "        shift 2",
                "        ;;",
                '      --clobber)',
                '        clobber="true"',
                "        shift",
                "        ;;",
                '      --*)',
                "        shift",
                "        ;;",
                "      *)",
                '        printf "%s\\n" "$1" >> "$state_dir/release-upload-files.log"',
                "        shift",
                "        ;;",
                "    esac",
                "  done",
                '  printf "%s\\n" "$tag" > "$state_dir/release-upload-tag.txt"',
                '  printf "%s\\n" "$repo" > "$state_dir/release-upload-repo.txt"',
                '  printf "%s\\n" "$clobber" > "$state_dir/release-upload-clobber.txt"',
                "  exit 0",
                "fi",
                'if [[ "${1:-}" != "api" ]]; then',
                '  printf "fake gh only supports gh api and gh release upload\\n" >&2',
                "  exit 2",
                "fi",
                "shift",
                'method="GET"',
                'input_target=""',
                'endpoint=""',
                'while [[ $# -gt 0 ]]; do',
                '  case "$1" in',
                '    -X)',
                '      method="$2"',
                "      shift 2",
                "      ;;",
                '    -H)',
                "      shift 2",
                "      ;;",
                '    --input)',
                '      input_target="$2"',
                "      shift 2",
                "      ;;",
                '    repos/*)',
                '      endpoint="$1"',
                "      shift",
                "      ;;",
                "    *)",
                "      shift",
                "      ;;",
                "  esac",
                "done",
                'printf "%s %s\\n" "$method" "$endpoint" >> "$state_dir/requests.log"',
                'case "$method:$endpoint" in',
                '  GET:repos/*/releases\\?per_page=100)',
                '    cat "$state_dir/list-releases.json"',
                "    ;;",
                '  DELETE:repos/*/releases/assets/*)',
                '    printf "%s\\n" "$endpoint" >> "$state_dir/deleted-asset-endpoints.log"',
                "    ;;",
                '  DELETE:repos/*/releases/*)',
                '    printf "%s\\n" "$endpoint" >> "$state_dir/deleted-endpoints.log"',
                "    ;;",
                '  POST:repos/*/releases)',
                '    if [[ "$input_target" == "-" ]]; then',
                '      cat > "$state_dir/create-release-request.json"',
                "    else",
                '      : > "$state_dir/create-release-request.json"',
                "    fi",
                '    cat "$state_dir/create-release-response.json"',
                "    ;;",
                '  PATCH:repos/*/releases/*)',
                '    if [[ "$input_target" == "-" ]]; then',
                '      cat > "$state_dir/update-release-request.json"',
                "    else",
                '      : > "$state_dir/update-release-request.json"',
                "    fi",
                '    cat "$state_dir/update-release-response.json"',
                "    ;;",
                '  POST:repos/*/git/tags)',
                '    if [[ "$input_target" == "-" ]]; then',
                '      cat > "$state_dir/create-tag-request.json"',
                "    else",
                '      : > "$state_dir/create-tag-request.json"',
                "    fi",
                '    cat "$state_dir/create-tag-response.json"',
                "    ;;",
                '  POST:repos/*/git/refs)',
                '    if [[ "$input_target" == "-" ]]; then',
                '      cat > "$state_dir/create-ref-request.json"',
                "    else",
                '      : > "$state_dir/create-ref-request.json"',
                "    fi",
                '    cat "$state_dir/create-ref-response.json"',
                "    ;;",
                '  PATCH:repos/*/git/refs/tags/*)',
                '    if [[ "$input_target" == "-" ]]; then',
                '      cat > "$state_dir/update-ref-request.json"',
                "    else",
                '      : > "$state_dir/update-ref-request.json"',
                "    fi",
                '    cat "$state_dir/update-ref-response.json"',
                "    ;;",
                "  *)",
                '    printf "unsupported fake gh request: %s %s\\n" "$method" "$endpoint" >&2',
                "    exit 2",
                "    ;;",
                "esac",
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)
    return launcher_path, state_dir


def create_fake_docker_launcher(sandbox_dir: Path) -> tuple[Path, Path]:
    """Create a lightweight `docker` shim for Docker Hub tagging integration tests."""

    state_dir = sandbox_dir / "fake-docker"
    launcher_dir = sandbox_dir / "docker-bin"
    launcher_path = launcher_dir / "docker"
    state_dir.mkdir(parents=True, exist_ok=True)
    launcher_dir.mkdir(parents=True, exist_ok=True)
    launcher_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'state_dir="${FAKE_DOCKER_STATE_DIR:?}"',
                'if [[ "${1:-}" == "login" ]]; then',
                "  shift",
                '  registry=""',
                '  user=""',
                '  while [[ $# -gt 0 ]]; do',
                '    case "$1" in',
                '      --username|-u)',
                '        user="$2"',
                "        shift 2",
                "        ;;",
                '      --password-stdin)',
                "        shift",
                "        ;;",
                "      *)",
                '        registry="$1"',
                "        shift",
                "        ;;",
                "    esac",
                "  done",
                '  cat > "$state_dir/login-password.txt"',
                '  printf "%s\\n" "$user" > "$state_dir/login-user.txt"',
                '  printf "%s\\n" "$registry" > "$state_dir/login-registry.txt"',
                "  exit 0",
                "fi",
                'if [[ "${1:-}" == "buildx" && "${2:-}" == "imagetools" && "${3:-}" == "create" ]]; then',
                "  shift 3",
                '  source_image=""',
                '  target_tag=""',
                '  prefer_index=""',
                '  while [[ $# -gt 0 ]]; do',
                '    case "$1" in',
                '      --prefer-index=false)',
                '        prefer_index="false"',
                "        shift",
                "        ;;",
                '      --tag|-t)',
                '        target_tag="$2"',
                "        shift 2",
                "        ;;",
                "      *)",
                '        source_image="$1"',
                "        shift",
                "        ;;",
                "    esac",
                "  done",
                '  printf "%s|%s|%s\\n" "$target_tag" "$source_image" "$prefer_index" >> "$state_dir/imagetools-create.log"',
                "  exit 0",
                "fi",
                'printf "unsupported fake docker invocation: %s\\n" "$*" >&2',
                "exit 2",
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)
    return launcher_path, state_dir


def dispatcher_env(
    sandbox_dir: Path,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an environment suitable for testing the bash dispatcher wrappers."""

    launcher_dir = create_fake_uv_launcher(sandbox_dir)
    env = tool_env(
        env_with_prepend_path(
            extra_env,
            prepend_dirs=(launcher_dir, Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin")),
        )
    )
    env["BUILDISH_TEST_PYTHON"] = sys.executable
    env.setdefault("BUILDISH_RELEASE_TOOLING_DIR", str(component_root()))
    return env


def read_json(path: Path) -> dict[str, str]:
    """Read a JSON object from disk and coerce keys and values to strings."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in payload.items()}


def run_cli(arguments: list[str], *, cwd: Path, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the CLI in a subprocess with the local source tree on `PYTHONPATH`."""

    return subprocess.run(
        [sys.executable, "-m", "apache_buildish_release_tooling", *arguments],
        cwd=str(cwd),
        env=tool_env(env),
        text=True,
        capture_output=True,
        check=False,
    )
