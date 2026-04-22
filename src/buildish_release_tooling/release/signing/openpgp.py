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

"""Secret-safe OpenPGP signing in an isolated GnuPG home."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from buildish_release_tooling.release.command_logging import sanitize_text
from buildish_release_tooling.release.core.config import OpenPgpSigningConfig
from buildish_release_tooling.release.process import CommandExecutionError, run_logged_command

_UNIX_SOCKET_PATH_LIMIT = 108
_LONGEST_GPG_AGENT_SOCKET_NAME = "S.gpg-agent.browser"
_SHORT_HOME_CACHE: dict[str, Path] = {}
_FINGERPRINT_PATTERN = re.compile(r"(?:[0-9A-F]{40}|[0-9A-F]{64})")
_PASSPHRASE_FAILURE_MARKERS = (
    "bad passphrase",
    "no passphrase given",
    "inappropriate ioctl for device",
    "operation cancelled",
)
_KNOWN_SIGNING_SECRET_ENV_NAMES = (
    "BUILDISH_GPG_PRIVATE_KEY",
    "BUILDISH_GPG_PASSPHRASE",
)


class OpenPgpSigningError(RuntimeError):
    """Raised when an OpenPGP key cannot be imported or used safely."""


@dataclass(frozen=True)
class OpenPgpSigningInput:
    """Names and public constraints needed to load an OpenPGP signing identity."""

    private_key_env: str
    passphrase_env: str | None = None
    expected_fingerprint: str | None = None

    @classmethod
    def from_config(cls, config: OpenPgpSigningConfig) -> OpenPgpSigningInput:
        """Build runtime signing inputs from component-authored policy."""

        return cls(
            private_key_env=config.private_key_env,
            passphrase_env=config.passphrase_env,
            expected_fingerprint=config.expected_fingerprint,
        )


@dataclass(frozen=True)
class OpenPgpSigner:
    """One imported OpenPGP signing identity scoped to an isolated GnuPG home."""

    gpg_home: Path
    fingerprint: str
    _passphrase: str | None = field(repr=False, compare=False)
    _passphrase_supplied: bool
    _private_key_env: str
    _passphrase_env: str | None
    _secret_values: tuple[str, ...] = field(repr=False, compare=False)

    @classmethod
    def from_environment(
        cls,
        gpg_home: Path,
        signing_input: OpenPgpSigningInput,
    ) -> OpenPgpSigner:
        """Import the configured private key and return its validated signer identity."""

        private_key = os.environ.get(signing_input.private_key_env)
        if not private_key:
            raise OpenPgpSigningError(
                f"{signing_input.private_key_env} is required for OpenPGP signing"
            )
        passphrase_supplied = (
            signing_input.passphrase_env is not None
            and signing_input.passphrase_env in os.environ
        )
        passphrase = (
            os.environ.get(signing_input.passphrase_env)
            if signing_input.passphrase_env is not None
            else None
        )
        import_secret_values = tuple(
            value for value in (private_key, passphrase) if value
        )
        effective_home = _effective_home(gpg_home)
        child_env = _gpg_environment(
            effective_home,
            signing_input.private_key_env,
            signing_input.passphrase_env,
        )
        try:
            run_logged_command(
                ["gpg", "--batch", "--import"],
                env=child_env,
                inherit_parent_env=False,
                input_text=private_key,
                extra_secret_values=import_secret_values,
            )
        except CommandExecutionError as exc:
            detail = sanitize_text(str(exc), import_secret_values)
            raise OpenPgpSigningError(f"OpenPGP private-key import failed: {detail}") from exc

        fingerprint = _default_secret_key_fingerprint(
            effective_home,
            child_env=child_env,
            secret_values=import_secret_values,
        )
        expected_fingerprint = signing_input.expected_fingerprint
        if expected_fingerprint is not None and fingerprint != expected_fingerprint:
            raise OpenPgpSigningError(
                "imported OpenPGP signing fingerprint does not match expected_fingerprint: "
                f"expected {expected_fingerprint}, found {fingerprint}"
            )
        return cls(
            gpg_home=effective_home,
            fingerprint=fingerprint,
            _passphrase=passphrase,
            _passphrase_supplied=passphrase_supplied,
            _private_key_env=signing_input.private_key_env,
            _passphrase_env=signing_input.passphrase_env,
            _secret_values=tuple(value for value in (passphrase,) if value),
        )

    def sign_file(self, input_path: Path, output_path: Path) -> None:
        """Create a detached ASCII-armored signature without exposing the passphrase."""

        temporary_output = _temporary_signature_path(output_path)
        command = [
            "gpg",
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--passphrase-fd",
            "0",
            "--local-user",
            self.fingerprint,
            "--armor",
            "--detach-sign",
            "--output",
            str(temporary_output),
            str(input_path),
        ]
        child_env = _gpg_environment(
            self.gpg_home,
            self._private_key_env,
            self._passphrase_env,
        )
        try:
            run_logged_command(
                command,
                env=child_env,
                inherit_parent_env=False,
                input_text=f"{self._passphrase or ''}\n",
                extra_secret_values=self._secret_values,
            )
            temporary_output.replace(output_path)
        except CommandExecutionError as exc:
            detail = sanitize_text(str(exc), self._secret_values)
            if any(marker in detail.lower() for marker in _PASSPHRASE_FAILURE_MARKERS):
                if self._passphrase_supplied:
                    message = "OpenPGP signing failed because the configured passphrase is incorrect"
                elif self._passphrase_env is not None:
                    message = (
                        "OpenPGP signing key requires a passphrase, but "
                        f"{self._passphrase_env} is not set"
                    )
                else:
                    message = (
                        "OpenPGP signing key requires a passphrase, but no passphrase_env "
                        "is configured"
                    )
                raise OpenPgpSigningError(message) from exc
            raise OpenPgpSigningError(f"OpenPGP signing failed: {detail}") from exc
        finally:
            temporary_output.unlink(missing_ok=True)


def _prepare_home(home_path: Path) -> None:
    home_path.mkdir(parents=True, exist_ok=True)
    home_path.chmod(0o700)


def _needs_short_socket_path(home_path: Path) -> bool:
    return len(str(home_path / _LONGEST_GPG_AGENT_SOCKET_NAME)) >= _UNIX_SOCKET_PATH_LIMIT


def _effective_home(home_path: Path) -> Path:
    requested_home = home_path.resolve(strict=False)
    _prepare_home(requested_home)
    if not _needs_short_socket_path(requested_home):
        return requested_home
    cache_key = str(requested_home)
    cached_home = _SHORT_HOME_CACHE.get(cache_key)
    if cached_home is not None and cached_home.exists():
        return cached_home
    short_parent = Path(tempfile.mkdtemp(prefix="buildish-gpg-home."))
    short_home = short_parent / "home"
    short_home.symlink_to(requested_home, target_is_directory=True)
    _SHORT_HOME_CACHE[cache_key] = short_home
    return short_home


def _gpg_environment(
    gpg_home: Path,
    private_key_env: str | None = None,
    passphrase_env: str | None = None,
) -> dict[str, str]:
    child_env = dict(os.environ)
    for name in (*_KNOWN_SIGNING_SECRET_ENV_NAMES, private_key_env, passphrase_env):
        if name is not None:
            child_env.pop(name, None)
    child_env["GNUPGHOME"] = str(gpg_home)
    return child_env


def _temporary_signature_path(output_path: Path) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(descriptor)
    return Path(temporary_name)


def _default_secret_key_fingerprint(
    gpg_home: Path,
    *,
    child_env: dict[str, str] | None = None,
    secret_values: tuple[str, ...] = (),
) -> str:
    effective_home = _effective_home(gpg_home)
    completed = run_logged_command(
        ["gpg", "--batch", "--with-colons", "--fingerprint", "--list-secret-keys"],
        env=child_env or _gpg_environment(effective_home),
        inherit_parent_env=False,
        extra_secret_values=secret_values,
    )
    primary_fingerprints: list[str] = []
    awaiting_primary_fingerprint = False
    for line in completed.stdout.splitlines():
        parts = line.split(":")
        record_type = parts[0]
        if record_type == "sec":
            awaiting_primary_fingerprint = True
        elif record_type == "ssb":
            awaiting_primary_fingerprint = False
        elif record_type == "fpr" and awaiting_primary_fingerprint:
            fingerprint = parts[9].upper() if len(parts) > 9 else ""
            if _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
                raise OpenPgpSigningError("GnuPG returned an invalid primary-key fingerprint")
            primary_fingerprints.append(fingerprint)
            awaiting_primary_fingerprint = False
    if not primary_fingerprints:
        raise OpenPgpSigningError(f"no secret signing key available in {gpg_home}")
    if len(primary_fingerprints) != 1:
        raise OpenPgpSigningError(
            "OpenPGP private-key input must contain exactly one primary secret key"
        )
    return primary_fingerprints[0]


def secret_key_fingerprint(gpg_home: Path) -> str:
    """Return the sole primary secret-key fingerprint in a GnuPG home."""

    return _default_secret_key_fingerprint(gpg_home)


def detached_ascii_sign(gpg_home: Path, input_path: Path, output_path: Path) -> None:
    """Sign with an already-imported unprotected key, primarily for verifier fixtures."""

    fingerprint = secret_key_fingerprint(gpg_home)
    signer = OpenPgpSigner(
        gpg_home=_effective_home(gpg_home),
        fingerprint=fingerprint,
        _passphrase=None,
        _passphrase_supplied=False,
        _private_key_env="BUILDISH_GPG_PRIVATE_KEY",
        _passphrase_env=None,
        _secret_values=(),
    )
    signer.sign_file(input_path, output_path)
