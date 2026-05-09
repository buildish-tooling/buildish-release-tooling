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
"""Release publication command integration tests."""

"""Final Git tag publication command tests."""

# ruff: noqa: F403, F405
from tests.release.commands.release_publication_support import (
    ReleasePublicationCommandTestBase,
)
from tests.release.commands.support import *


class FinalTagPublicationCommandIntegrationTest(ReleasePublicationCommandTestBase):
    """Final Git tag publication command tests."""

    def test_create_final_tag_command_creates_remote_annotated_tag(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-final-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc3")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3-rc2^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc2",
                            f"Resolved source ref: {expected_commit}",
                        ]
                    ),
                }
            ],
            create_tag_response={"sha": "tag-object-sha"},
            create_ref_response={"ref": "refs/tags/v1.2.3"},
        )
        completed = run_cli(
            [
                "create-final-tag",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3", manifest["final_tag"])
        self.assertEqual(expected_commit, manifest["target_commit"])
        self.assertEqual("github-api", manifest["tag_creation_mode"])
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        create_tag_request = json.loads(
            (gh_state_dir / "create-tag-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual("v1.2.3", create_tag_request["tag"])
        self.assertEqual(expected_commit, create_tag_request["object"])
        create_ref_request = json.loads(
            (gh_state_dir / "create-ref-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual("refs/tags/v1.2.3", create_ref_request["ref"])
        self.assertEqual("tag-object-sha", create_ref_request["sha"])
