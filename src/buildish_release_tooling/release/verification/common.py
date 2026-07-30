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

"""Shared cryptographic and fetch-validation helpers for `verify-rc`."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from buildish_release_tooling.release.rc_vote_manifest import DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES
from buildish_release_tooling.release.contracts import SignatureVerificationPayload
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.process import run_logged_command
from buildish_release_tooling.release.source_artifact import checksum
from buildish_release_tooling.shared.io import read_text_file_bounded

_GPG_ALGORITHM_NAMES = {
    "1": "rsa",
    "16": "elgamal",
    "17": "dsa",
    "18": "ecdh",
    "19": "ecdsa",
    "22": "ed25519",
}

_DIGEST_LENGTHS = {
    "sha256": 64,
    "sha512": 128,
}


@dataclass(frozen=True)
class SignatureVerification:
    """Structured details about one detached-signature verification."""

    signer_fingerprint: str
    signer_user_id: str | None
    trust_label: str | None
    key_algorithm: str | None
    key_size_bits: int | None


class GpgVerifier:
    """Small helper for detached-signature verification against one imported KEYS file."""

    def __init__(self, home_dir: Path, keys_path: Path) -> None:
        self.home_dir = home_dir
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.home_dir.chmod(0o700)
        run_logged_command(
            ["gpg", "--batch", "--quiet", "--import", str(keys_path)],
            env={"GNUPGHOME": str(self.home_dir)},
            log_command=False,
        )

    def verify_detached(self, *, target_path: Path, signature_path: Path) -> SignatureVerification:
        completed = run_logged_command(
            [
                "gpg",
                "--batch",
                "--status-fd",
                "1",
                "--verify",
                str(signature_path),
                str(target_path),
            ],
            env={"GNUPGHOME": str(self.home_dir)},
            log_command=False,
        )
        return _signature_verification_from_status(
            completed.stdout,
            home_dir=self.home_dir,
        )


def signature_payload(signature: SignatureVerification) -> SignatureVerificationPayload:
    """Return one typed detached-signature verification payload."""

    return SignatureVerificationPayload(**asdict(signature))


def signature_summary(signature: SignatureVerification) -> str:
    """Return one compact human-readable detached-signature verification summary."""

    if signature.signer_user_id:
        return f"{signature.signer_fingerprint} ({signature.signer_user_id})"
    return signature.signer_fingerprint


def emit_title(reporter: ProgressReporter, title: str) -> None:
    """Emit one top-level heading for the verification transcript."""

    reporter.emit_styled(title, sgr="1")
    reporter.emit_styled("=" * len(title), sgr="1")


def emit_section(reporter: ProgressReporter, title: str) -> None:
    """Emit one section heading for the verification transcript."""

    reporter.emit("")
    reporter.emit_styled(title, sgr="1;36")
    reporter.emit_styled("-" * len(title), sgr="1;36")


def emit_info(reporter: ProgressReporter, message: str) -> None:
    """Emit one informational transcript line."""

    reporter.emit(f"• {message}")


def update_info(reporter: ProgressReporter, message: str) -> None:
    """Emit one rate-limited informational transcript line."""

    reporter.update(f"• {message}")


def emit_detail(reporter: ProgressReporter, label: str, value: str) -> None:
    """Emit one indented detail line."""

    reporter.emit(f"  {label}: {value}")


def emit_success(reporter: ProgressReporter, message: str) -> None:
    """Emit one success transcript line."""

    reporter.emit_styled(f"✓ {message}", sgr="32")


def emit_warning(reporter: ProgressReporter, message: str) -> None:
    """Emit one warning transcript line."""

    reporter.emit_styled(f"⚠ {message}", sgr="33")


def emit_failure(reporter: ProgressReporter, message: str) -> None:
    """Emit one failure transcript line."""

    reporter.emit_styled(f"✗ {message}", sgr="31")


def validate_fetch_uri(
    uri: str,
    *,
    allow_non_production_release_targets: bool,
    purpose: str,
) -> None:
    """Validate that one fetched URI uses an allowed scheme for the current mode."""

    parsed = urlparse(uri)
    if parsed.scheme == "https":
        return
    if allow_non_production_release_targets and parsed.scheme in {"file", "http"}:
        return
    raise ValueError(
        f"{purpose} must use https; pass --allow-non-production-release-targets only for local file:// or http:// test inputs: {uri}"
    )


def verify_checksum_sidecar(
    target_path: Path,
    sidecar_path: Path,
    *,
    algorithm: str,
    purpose: str,
) -> str:
    """Verify one detached checksum sidecar against downloaded artifact bytes."""

    normalized_algorithm = algorithm.lower()
    expected_length = _DIGEST_LENGTHS.get(normalized_algorithm)
    if expected_length is None:
        raise ValueError(f"unsupported checksum algorithm for sidecar verification: {algorithm}")
    actual_digest = checksum(target_path, normalized_algorithm)
    sidecar_text = read_text_file_bounded(
        sidecar_path,
        max_bytes=DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
    )
    fields = sidecar_text.strip().split()
    if not fields or not fields[0]:
        raise ValueError(f"invalid .{normalized_algorithm} sidecar contents for {purpose}: {sidecar_path}")
    declared_digest = fields[0].strip().lower()
    if len(declared_digest) != expected_length or any(character not in "0123456789abcdef" for character in declared_digest):
        raise ValueError(
            f"invalid .{normalized_algorithm} sidecar digest for {purpose}: {sidecar_path}"
        )
    if declared_digest != actual_digest:
        raise ValueError(
            f"{purpose} .{normalized_algorithm} sidecar does not match the downloaded bytes: "
            f"{declared_digest} != {actual_digest}"
        )
    return actual_digest


def _signature_verification_from_status(status_output: str, *, home_dir: Path) -> SignatureVerification:
    fingerprint: str | None = None
    user_id: str | None = None
    trust_label: str | None = None
    for line in status_output.splitlines():
        if line.startswith("[GNUPG:] VALIDSIG "):
            fields = line.split()
            if len(fields) > 2:
                fingerprint = fields[2]
        elif line.startswith("[GNUPG:] GOODSIG "):
            fields = line.split(maxsplit=3)
            if len(fields) > 3:
                user_id = fields[3]
        elif line.startswith("[GNUPG:] TRUST_"):
            trust_label = line.removeprefix("[GNUPG:] ").strip()
    if fingerprint is None:
        raise ValueError("gpg verification did not report a signer fingerprint")

    completed = run_logged_command(
        ["gpg", "--batch", "--with-colons", "--list-keys", fingerprint],
        env={"GNUPGHOME": str(home_dir)},
        log_command=False,
    )
    key_algorithm: str | None = None
    key_size_bits: int | None = None
    for line in completed.stdout.splitlines():
        parts = line.split(":")
        if parts and parts[0] == "pub":
            if len(parts) > 3 and parts[3]:
                key_algorithm = _GPG_ALGORITHM_NAMES.get(parts[3], parts[3])
            if len(parts) > 2 and parts[2].isdigit():
                key_size_bits = int(parts[2])
            break
    return SignatureVerification(
        signer_fingerprint=fingerprint,
        signer_user_id=user_id,
        trust_label=trust_label,
        key_algorithm=key_algorithm,
        key_size_bits=key_size_bits,
    )
