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

"""Reproducible source-artifact creation helpers."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from apache_buildish_release_tooling.release.command_logging import log_command_output, print_command

_SUPPORTED_CHECKSUM_ALGORITHMS = frozenset({"sha256", "sha512"})


def fixed_mtime() -> str:
    """Return the fixed mtime used for reproducible source archives."""

    return "1980-02-01 00:00:00 UTC"


def create_from_git(
    repo_path: Path,
    ref: str,
    archive_prefix: str,
    output_path: Path,
    *,
    log_commands: bool = True,
) -> None:
    """Build a reproducible source tarball from Git using a fixed mtime and gzip settings."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    git_command = [
        "git",
        "-C",
        str(repo_path),
        "archive",
        f"--prefix={archive_prefix}",
        "--format=tar",
        f"--mtime={fixed_mtime()}",
        ref,
    ]
    gzip_command = ["gzip", "-6", "--no-name"]
    print_command(git_command, stderr_enabled=log_commands)
    print_command(gzip_command, stderr_enabled=log_commands)
    with (
        output_path.open("wb") as handle,
        tempfile.TemporaryFile() as archive_stderr_file,
        tempfile.TemporaryFile() as gzip_stderr_file,
    ):
        archive_process = subprocess.Popen(  # noqa: S603
            git_command,
            stdout=subprocess.PIPE,
            stderr=archive_stderr_file,
        )
        gzip_process = subprocess.Popen(  # noqa: S603
            gzip_command,
            stdin=archive_process.stdout,
            stdout=handle,
            stderr=gzip_stderr_file,
        )
        if archive_process.stdout is not None:
            archive_process.stdout.close()
        archive_return_code = archive_process.wait()
        gzip_return_code = gzip_process.wait()
        archive_stderr_file.seek(0)
        gzip_stderr_file.seek(0)
        archive_stderr = archive_stderr_file.read().decode("utf-8", errors="replace")
        gzip_stderr = gzip_stderr_file.read().decode("utf-8", errors="replace")
    log_command_output("stderr", archive_stderr)
    log_command_output("stderr", gzip_stderr)
    if archive_return_code != 0:
        raise RuntimeError("git archive failed while creating the source artifact")
    if gzip_return_code != 0:
        raise RuntimeError("gzip failed while creating the source artifact")


def checksum(artifact_path: Path, algorithm: str) -> str:
    """Compute a supported checksum for an artifact."""

    normalized_algorithm = algorithm.lower()
    if normalized_algorithm not in _SUPPORTED_CHECKSUM_ALGORITHMS:
        raise ValueError(f"unsupported checksum algorithm: {algorithm}")
    digest = hashlib.new(normalized_algorithm)
    with artifact_path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum_file(artifact_path: Path, algorithm: str, digest_value: str) -> Path:
    """Write the standard checksum sidecar file for an artifact."""

    normalized_algorithm = algorithm.lower()
    if normalized_algorithm not in _SUPPORTED_CHECKSUM_ALGORITHMS:
        raise ValueError(f"unsupported checksum algorithm: {algorithm}")
    checksum_path = artifact_path.with_name(f"{artifact_path.name}.{normalized_algorithm}")
    checksum_path.write_text(f"{digest_value}  {artifact_path.name}\n", encoding="utf-8")
    return checksum_path


def sha512(artifact_path: Path) -> str:
    """Compute the SHA512 checksum for an artifact."""

    return checksum(artifact_path, "sha512")


def write_sha512_file(artifact_path: Path, digest_value: str) -> Path:
    """Write the standard `.sha512` sidecar file for an artifact."""

    return write_checksum_file(artifact_path, "sha512", digest_value)
