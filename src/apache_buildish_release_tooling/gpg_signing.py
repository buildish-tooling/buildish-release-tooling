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

"""GPG signing helpers for staged source artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from apache_buildish_release_tooling.process import run_logged_command


def _prepare_home(home_path: Path) -> None:
    home_path.mkdir(parents=True, exist_ok=True)
    home_path.chmod(0o700)


def import_private_key_from_secret(gpg_home: Path) -> None:
    """Import the armored signing key from `BUILDISH_GPG_PRIVATE_KEY` into a GNUPGHOME."""

    private_key = os.environ.get("BUILDISH_GPG_PRIVATE_KEY")
    if not private_key:
        raise ValueError("BUILDISH_GPG_PRIVATE_KEY is required for signing")
    _prepare_home(gpg_home)
    run_logged_command(
        ["gpg", "--batch", "--import"],
        env={"GNUPGHOME": str(gpg_home)},
        input_text=private_key,
        capture_output=False,
        extra_secret_values=[private_key],
    )


def _default_secret_key_fingerprint(gpg_home: Path) -> str:
    completed = run_logged_command(
        ["gpg", "--batch", "--with-colons", "--list-secret-keys"],
        env={"GNUPGHOME": str(gpg_home)},
    )
    for line in completed.stdout.splitlines():
        parts = line.split(":")
        if parts[0] == "fpr" and len(parts) > 9 and parts[9]:
            return parts[9]
    raise ValueError(f"no secret signing key available in {gpg_home}")


def secret_key_fingerprint(gpg_home: Path) -> str:
    """Return the fingerprint of the default secret key in a GNUPGHOME."""

    return _default_secret_key_fingerprint(gpg_home)


def detached_ascii_sign(gpg_home: Path, input_path: Path, output_path: Path) -> None:
    """Create a detached ASCII-armored signature for an artifact."""

    fingerprint = secret_key_fingerprint(gpg_home)
    run_logged_command(
        [
            "gpg",
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--local-user",
            fingerprint,
            "--armor",
            "--detach-sign",
            "--output",
            str(output_path),
            str(input_path),
        ],
        env={"GNUPGHOME": str(gpg_home)},
        capture_output=False,
    )
