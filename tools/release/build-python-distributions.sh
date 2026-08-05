#!/usr/bin/env bash
#
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

set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'usage: %s <version> <source-commit> <output-directory>\n' "$0" >&2
  exit 2
fi

release_version="$1"
expected_source_commit="$2"
output_dir="$3"
repository_root="$(git rev-parse --show-toplevel)"
actual_source_commit="$(git rev-parse 'HEAD^{commit}')"

if [[ "$actual_source_commit" != "$expected_source_commit" ]]; then
  printf 'checked-out source commit %s does not match expected commit %s\n' \
    "$actual_source_commit" "$expected_source_commit" >&2
  exit 1
fi

python3 - "$repository_root/pyproject.toml" "$release_version" <<'PY'
import sys
import tomllib
from pathlib import Path

pyproject_path = Path(sys.argv[1])
expected_version = sys.argv[2]
project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
actual_name = project["name"]
actual_version = project["version"]
if actual_name != "buildish-release-tooling":
    raise SystemExit(
        f"pyproject project name {actual_name!r} is not 'buildish-release-tooling'"
    )
if actual_version != expected_version:
    raise SystemExit(
        f"pyproject version {actual_version!r} does not match release version "
        f"{expected_version!r}"
    )
PY

mkdir -p "$output_dir"
if find "$output_dir" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
  printf 'distribution output directory is not empty: %s\n' "$output_dir" >&2
  exit 1
fi

temporary_root="$(mktemp -d)"
trap 'rm -rf "$temporary_root"' EXIT
first_build="$temporary_root/first"
second_build="$temporary_root/second"
sdist_build="$temporary_root/from-sdist"
mkdir -p "$first_build" "$second_build" "$sdist_build"

export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH="$(git show -s --format=%ct "$expected_source_commit")"
wheel_name="buildish_release_tooling-${release_version}-py3-none-any.whl"
sdist_name="buildish_release_tooling-${release_version}.tar.gz"

build_distributions() {
  local destination="$1"
  uv build \
    --python 3.11 \
    --no-build-logs \
    --no-create-gitignore \
    --out-dir "$destination" \
    "$repository_root"
}

build_distributions "$first_build"
build_distributions "$second_build"

for expected_name in "$wheel_name" "$sdist_name"; do
  if [[ ! -f "$first_build/$expected_name" ]]; then
    printf 'first build did not produce expected distribution: %s\n' "$expected_name" >&2
    exit 1
  fi
  if ! cmp "$first_build/$expected_name" "$second_build/$expected_name"; then
    printf 'distribution is not byte reproducible: %s\n' "$expected_name" >&2
    exit 1
  fi
done

if [[ "$(find "$first_build" -maxdepth 1 -type f | wc -l)" -ne 2 ]]; then
  printf 'distribution build produced files outside the expected wheel and sdist set\n' >&2
  find "$first_build" -maxdepth 1 -type f -printf '%f\n' >&2
  exit 1
fi

uv build \
  --python 3.11 \
  --wheel \
  --no-build-logs \
  --no-create-gitignore \
  --out-dir "$sdist_build" \
  "$first_build/$sdist_name"
if ! cmp "$first_build/$wheel_name" "$sdist_build/$wheel_name"; then
  printf 'wheel rebuilt from the sdist does not match the source-tree wheel\n' >&2
  exit 1
fi

python3 - \
  "$first_build/$wheel_name" \
  "$first_build/$sdist_name" \
  "$release_version" <<'PY'
import email
import sys
import tarfile
import zipfile
from pathlib import Path

wheel_path = Path(sys.argv[1])
sdist_path = Path(sys.argv[2])
expected_version = sys.argv[3]
dist_info = f"buildish_release_tooling-{expected_version}.dist-info"
sdist_root = f"buildish_release_tooling-{expected_version}"

with zipfile.ZipFile(wheel_path) as wheel:
    names = set(wheel.namelist())
    metadata = email.message_from_bytes(wheel.read(f"{dist_info}/METADATA"))
    expected_wheel_legal = {
        f"{dist_info}/licenses/LICENSE",
        f"{dist_info}/licenses/NOTICE",
    }
    if not expected_wheel_legal.issubset(names):
        raise SystemExit("wheel is missing required LICENSE or NOTICE files")

with tarfile.open(sdist_path, mode="r:gz") as sdist:
    names = set(sdist.getnames())
    metadata_file = sdist.extractfile(f"{sdist_root}/PKG-INFO")
    if metadata_file is None:
        raise SystemExit("sdist is missing PKG-INFO")
    metadata_sdist = email.message_from_bytes(metadata_file.read())
    expected_sdist_legal = {
        f"{sdist_root}/dist-release-legal/LICENSE",
        f"{sdist_root}/dist-release-legal/NOTICE",
    }
    if not expected_sdist_legal.issubset(names):
        raise SystemExit("sdist is missing required LICENSE or NOTICE files")

for artifact_kind, artifact_metadata in (
    ("wheel", metadata),
    ("sdist", metadata_sdist),
):
    if artifact_metadata["Name"] != "buildish-release-tooling":
        raise SystemExit(f"{artifact_kind} has an unexpected project name")
    if artifact_metadata["Version"] != expected_version:
        raise SystemExit(f"{artifact_kind} has an unexpected project version")
PY

uv run --isolated --no-project --python 3.11 \
  --with "$first_build/$wheel_name" \
  buildish-release-tooling --help >/dev/null
uv run --isolated --no-project --python 3.11 \
  --with "$first_build/$wheel_name" \
  buildish-release-harness --help >/dev/null
uv run --isolated --no-project --python 3.11 \
  --with "$first_build/$sdist_name" \
  buildish-release-tooling --help >/dev/null
uv run --isolated --no-project --python 3.11 \
  --with "$first_build/$sdist_name" \
  buildish-release-harness --help >/dev/null

install -m 0644 "$first_build/$wheel_name" "$output_dir/$wheel_name"
install -m 0644 "$first_build/$sdist_name" "$output_dir/$sdist_name"
sha256sum "$output_dir/$wheel_name" "$output_dir/$sdist_name"
