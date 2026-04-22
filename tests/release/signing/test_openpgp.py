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

"""Integration tests for secret-safe OpenPGP signing."""

from __future__ import annotations

import io
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from buildish_release_tooling.release.command_logging import command_log_sink
from buildish_release_tooling.release.signing.openpgp import (
    OpenPgpSigner,
    OpenPgpSigningError,
    OpenPgpSigningInput,
    _effective_home,
    _gpg_environment,
    secret_key_fingerprint,
)

from tests.support import (
    cleanup_sandbox,
    command_available,
    create_build_test_sandbox,
    test_command_timeout_seconds as command_timeout_seconds,
)

_PRIVATE_KEY_ENV = "TEST_OPENPGP_PRIVATE_KEY"
_PASSPHRASE_ENV = "TEST_OPENPGP_PASSPHRASE"  # noqa: S105 - variable name, not a secret
_PROTECTED_PASSPHRASE = "fixture-passphrase-that-must-not-leak"  # noqa: S105


def _run_fixture_gpg(
    home: Path,
    arguments: list[str],
    *,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)
    return subprocess.run(
        ["gpg", "--batch", *arguments],
        env={**os.environ, "GNUPGHOME": str(home)},
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
        timeout=command_timeout_seconds(),
    )


def _generate_fixture_key(home: Path, *, identity: str, passphrase: str) -> str:
    _run_fixture_gpg(
        home,
        [
            "--pinentry-mode",
            "loopback",
            "--passphrase-fd",
            "0",
            "--quick-gen-key",
            identity,
            "ed25519",
            "sign",
            "1d",
        ],
        input_text=f"{passphrase}\n",
    )
    return _run_fixture_gpg(
        home,
        [
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--passphrase-fd",
            "0",
            "--armor",
            "--export-secret-keys",
            identity,
        ],
        input_text=f"{passphrase}\n",
    ).stdout


class OpenPgpSigningIntegrationTest(unittest.TestCase):
    """Verify protected and unprotected keys across the signing trust boundary."""

    fixture_root: Path
    unprotected_key: str
    unprotected_fingerprint: str
    protected_key: str
    protected_fingerprint: str

    @classmethod
    def setUpClass(cls) -> None:
        if not command_available("gpg"):
            raise unittest.SkipTest("gpg is required for OpenPGP signing integration tests")
        cls.fixture_root = create_build_test_sandbox()
        cls.addClassCleanup(cleanup_sandbox, cls.fixture_root)
        unprotected_home = cls.fixture_root / "unprotected-source"
        protected_home = cls.fixture_root / "protected-source"
        cls.unprotected_key = _generate_fixture_key(
            unprotected_home,
            identity="Unprotected Signing Test <unprotected@example.invalid>",
            passphrase="",
        )
        cls.unprotected_fingerprint = secret_key_fingerprint(unprotected_home)
        cls.protected_key = _generate_fixture_key(
            protected_home,
            identity="Protected Signing Test <protected@example.invalid>",
            passphrase=_PROTECTED_PASSPHRASE,
        )
        cls.protected_fingerprint = secret_key_fingerprint(protected_home)

    def _sandbox(self) -> Path:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        return sandbox_dir

    @staticmethod
    def _controlled_environment(**values: str) -> dict[str, str]:
        environment = dict(os.environ)
        environment.pop(_PRIVATE_KEY_ENV, None)
        environment.pop(_PASSPHRASE_ENV, None)
        environment.update(values)
        return environment

    def _sign(
        self,
        sandbox_dir: Path,
        signing_input: OpenPgpSigningInput,
    ) -> OpenPgpSigner:
        input_path = sandbox_dir / "artifact.txt"
        signature_path = sandbox_dir / "artifact.txt.asc"
        input_path.write_text("release artifact\n", encoding="utf-8")
        signer = OpenPgpSigner.from_environment(
            sandbox_dir / "target-home", signing_input
        )
        signer.sign_file(input_path, signature_path)
        _run_fixture_gpg(
            signer.gpg_home,
            ["--verify", str(signature_path), str(input_path)],
        )
        return signer

    def test_long_gpg_home_uses_short_alias(self) -> None:
        sandbox_dir = self._sandbox()
        requested_home = sandbox_dir / ("nested-" * 16) / "gnupg-home"

        effective_home = _effective_home(requested_home)

        self.assertNotEqual(requested_home, effective_home)
        self.assertTrue(effective_home.is_symlink())
        self.assertEqual(requested_home.resolve(strict=False), effective_home.resolve(strict=False))
        self.assertLess(len(str(effective_home / "S.gpg-agent.browser")), 108)

    def test_gpg_child_environment_does_not_contain_signing_secrets(self) -> None:
        sandbox_dir = self._sandbox()
        environment = self._controlled_environment(
            TEST_OPENPGP_PRIVATE_KEY="private-key-material",
            TEST_OPENPGP_PASSPHRASE=_PROTECTED_PASSPHRASE,
            BUILDISH_GPG_PRIVATE_KEY="default-private-key-material",
            BUILDISH_GPG_PASSPHRASE=_PROTECTED_PASSPHRASE,
        )

        with mock.patch.dict(os.environ, environment, clear=True):
            child_environment = _gpg_environment(
                sandbox_dir / "target-home",
                _PRIVATE_KEY_ENV,
                _PASSPHRASE_ENV,
            )

        for secret_name in (
            _PRIVATE_KEY_ENV,
            _PASSPHRASE_ENV,
            "BUILDISH_GPG_PRIVATE_KEY",
            "BUILDISH_GPG_PASSPHRASE",
        ):
            self.assertNotIn(secret_name, child_environment)

    def test_unprotected_key_signs_without_passphrase_input(self) -> None:
        sandbox_dir = self._sandbox()
        environment = self._controlled_environment(
            TEST_OPENPGP_PRIVATE_KEY=self.unprotected_key
        )

        with mock.patch.dict(os.environ, environment, clear=True):
            signer = self._sign(
                sandbox_dir,
                OpenPgpSigningInput(private_key_env=_PRIVATE_KEY_ENV),
            )

        self.assertEqual(self.unprotected_fingerprint, signer.fingerprint)

    def test_protected_key_signs_with_passphrase_from_separate_input(self) -> None:
        sandbox_dir = self._sandbox()
        environment = self._controlled_environment(
            TEST_OPENPGP_PRIVATE_KEY=self.protected_key,
            TEST_OPENPGP_PASSPHRASE=_PROTECTED_PASSPHRASE,
        )

        with mock.patch.dict(os.environ, environment, clear=True):
            signer = self._sign(
                sandbox_dir,
                OpenPgpSigningInput(
                    private_key_env=_PRIVATE_KEY_ENV,
                    passphrase_env=_PASSPHRASE_ENV,
                    expected_fingerprint=self.protected_fingerprint,
                ),
            )

        self.assertEqual(self.protected_fingerprint, signer.fingerprint)
        self.assertNotIn(_PROTECTED_PASSPHRASE, repr(signer))
        self.assertNotIn(self.protected_key, repr(signer))

    def test_protected_key_reports_missing_passphrase_configuration(self) -> None:
        sandbox_dir = self._sandbox()
        input_path = sandbox_dir / "artifact.txt"
        input_path.write_text("release artifact\n", encoding="utf-8")
        environment = self._controlled_environment(
            TEST_OPENPGP_PRIVATE_KEY=self.protected_key
        )

        with mock.patch.dict(os.environ, environment, clear=True):
            signer = OpenPgpSigner.from_environment(
                sandbox_dir / "target-home",
                OpenPgpSigningInput(private_key_env=_PRIVATE_KEY_ENV),
            )
            with self.assertRaisesRegex(
                OpenPgpSigningError,
                "requires a passphrase, but no passphrase_env is configured",
            ):
                signer.sign_file(input_path, sandbox_dir / "artifact.txt.asc")

    def test_protected_key_reports_missing_configured_passphrase(self) -> None:
        sandbox_dir = self._sandbox()
        input_path = sandbox_dir / "artifact.txt"
        input_path.write_text("release artifact\n", encoding="utf-8")
        environment = self._controlled_environment(
            TEST_OPENPGP_PRIVATE_KEY=self.protected_key
        )

        with mock.patch.dict(os.environ, environment, clear=True):
            signer = OpenPgpSigner.from_environment(
                sandbox_dir / "target-home",
                OpenPgpSigningInput(
                    private_key_env=_PRIVATE_KEY_ENV,
                    passphrase_env=_PASSPHRASE_ENV,
                ),
            )
            with self.assertRaisesRegex(
                OpenPgpSigningError,
                rf"requires a passphrase, but {_PASSPHRASE_ENV} is not set",
            ):
                signer.sign_file(input_path, sandbox_dir / "artifact.txt.asc")

    def test_protected_key_reports_incorrect_passphrase_without_disclosing_it(self) -> None:
        sandbox_dir = self._sandbox()
        input_path = sandbox_dir / "artifact.txt"
        input_path.write_text("release artifact\n", encoding="utf-8")
        signature_path = sandbox_dir / "artifact.txt.asc"
        signature_path.write_text("previous valid signature\n", encoding="utf-8")
        wrong_passphrase = "wrong-passphrase-that-must-not-leak"  # noqa: S105
        environment = self._controlled_environment(
            TEST_OPENPGP_PRIVATE_KEY=self.protected_key,
            TEST_OPENPGP_PASSPHRASE=wrong_passphrase,
        )
        command_log = io.StringIO()

        with mock.patch.dict(os.environ, environment, clear=True):
            signer = OpenPgpSigner.from_environment(
                sandbox_dir / "target-home",
                OpenPgpSigningInput(
                    private_key_env=_PRIVATE_KEY_ENV,
                    passphrase_env=_PASSPHRASE_ENV,
                ),
            )
            with command_log_sink(command_log, echo_to_stderr=False):
                with self.assertRaisesRegex(
                    OpenPgpSigningError,
                    "configured passphrase is incorrect",
                ) as raised:
                    signer.sign_file(input_path, signature_path)

        combined_output = f"{raised.exception}\n{command_log.getvalue()}"
        self.assertNotIn(wrong_passphrase, combined_output)
        self.assertNotIn(self.protected_key, combined_output)
        self.assertNotIn("--passphrase ", combined_output)
        self.assertIn("--passphrase-fd 0", combined_output)
        self.assertEqual(
            "previous valid signature\n",
            signature_path.read_text(encoding="utf-8"),
        )

    def test_fingerprint_mismatch_is_rejected_before_signing(self) -> None:
        sandbox_dir = self._sandbox()
        environment = self._controlled_environment(
            TEST_OPENPGP_PRIVATE_KEY=self.unprotected_key
        )
        mismatched_fingerprint = "F" * 40

        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                OpenPgpSigningError,
                rf"expected {mismatched_fingerprint}, found {self.unprotected_fingerprint}",
            ):
                OpenPgpSigner.from_environment(
                    sandbox_dir / "target-home",
                    OpenPgpSigningInput(
                        private_key_env=_PRIVATE_KEY_ENV,
                        expected_fingerprint=mismatched_fingerprint,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
