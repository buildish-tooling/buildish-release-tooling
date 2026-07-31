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

"""Integration tests for GPG signing helpers."""

from __future__ import annotations

import os
import subprocess
import unittest

from buildish_release_tooling.release.signing.openpgp import (
    _effective_home,
    detached_ascii_sign,
    import_private_key_from_secret,
)

from tests.support import cleanup_sandbox, create_build_test_sandbox


class GpgSigningIntegrationTest(unittest.TestCase):
    """Verify detached signing with an imported test key."""

    def test_long_gpg_home_uses_short_alias(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        requested_home = sandbox_dir / ("nested-" * 16) / "gnupg-home"

        effective_home = _effective_home(requested_home)

        self.assertNotEqual(requested_home, effective_home)
        self.assertTrue(effective_home.is_symlink())
        self.assertEqual(requested_home.resolve(strict=False), effective_home.resolve(strict=False))
        self.assertLess(len(str(effective_home / "S.gpg-agent.browser")), 108)

    def test_import_private_key_and_sign(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        source_home = sandbox_dir / "gpg-source"
        target_home = sandbox_dir / ("nested-" * 16) / "gpg-target"
        verify_home = sandbox_dir / "gpg-verify"
        input_path = sandbox_dir / "source.tar.gz"
        signature_path = sandbox_dir / "source.tar.gz.asc"
        secret_key_path = sandbox_dir / "private.asc"
        public_key_path = sandbox_dir / "public.asc"
        source_home.mkdir(parents=True, exist_ok=True)
        verify_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)
        verify_home.chmod(0o700)
        input_path.write_text("artifact\n", encoding="utf-8")

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        secret_key_path.write_text(
            subprocess.run(
                [
                    "gpg",
                    "--armor",
                    "--export-secret-keys",
                    "Release Tooling Tests <release-tooling-tests@example.invalid>",
                ],
                env={**os.environ, "GNUPGHOME": str(source_home)},
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
            encoding="utf-8",
        )
        public_key_path.write_text(
            subprocess.run(
                [
                    "gpg",
                    "--armor",
                    "--export",
                    "Release Tooling Tests <release-tooling-tests@example.invalid>",
                ],
                env={**os.environ, "GNUPGHOME": str(source_home)},
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
            encoding="utf-8",
        )

        original_env = dict(os.environ)
        def restore_env() -> None:
            os.environ.clear()
            os.environ.update(original_env)

        self.addCleanup(restore_env)
        os.environ["BUILDISH_GPG_PRIVATE_KEY"] = secret_key_path.read_text(encoding="utf-8")
        import_private_key_from_secret(target_home)
        detached_ascii_sign(target_home, input_path, signature_path)

        subprocess.run(
            ["gpg", "--import", str(public_key_path)],
            env={**os.environ, "GNUPGHOME": str(verify_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["gpg", "--verify", str(signature_path), str(input_path)],
            env={**os.environ, "GNUPGHOME": str(verify_home)},
            check=True,
            capture_output=True,
            text=True,
        )
