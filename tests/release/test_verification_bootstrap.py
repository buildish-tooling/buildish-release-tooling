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

"""Unit tests for verify-rc bootstrap asset rendering."""

from __future__ import annotations

import unittest

from buildish_release_tooling.release.verification.bootstrap import (
    VERIFY_RC_BOOTSTRAP_SCRIPT_NAME,
    render_verify_rc_bootstrap_invoker,
    render_verify_rc_bootstrap_script,
)


class VerificationBootstrapTemplateTest(unittest.TestCase):
    """Verify the signed bootstrap UX text stays inspectable and stable."""

    def test_render_verify_rc_bootstrap_script_uses_pinned_tooling_commit_and_release_cli(self) -> None:
        script = render_verify_rc_bootstrap_script()

        self.assertIn("manifest provenance.tooling.git_commit_sha must be a full commit SHA", script)
        self.assertIn("git clone --quiet", script)
        self.assertIn("checkout --quiet --detach", script)
        self.assertIn("-m buildish_release_tooling.release verify-rc", script)
        self.assertIn("--work-dir \"$work_dir/verify-rc\"", script)

    def test_render_verify_rc_bootstrap_invoker_references_expected_assets(self) -> None:
        invoker = render_verify_rc_bootstrap_invoker(
            manifest_url=(
                "https://dist.apache.org/repos/dist/dev/incubator/example/example-project/1.2.3-rc0/"
                "rc-vote-manifest.json"
            ),
            keys_url="https://downloads.apache.org/incubator/example/KEYS",
        )

        self.assertIn(f"curl -fsSLO \"$bootstrap_base_url/{VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}\"", invoker)
        self.assertIn("sha512sum -c verify-rc-bootstrap.sh.sha512", invoker)
        self.assertIn("gpg --batch --quiet --verify verify-rc-bootstrap.sh.asc verify-rc-bootstrap.sh", invoker)
        self.assertIn("'https://downloads.apache.org/incubator/example/KEYS'", invoker)
