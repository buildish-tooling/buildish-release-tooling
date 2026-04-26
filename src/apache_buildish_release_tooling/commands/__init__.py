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

"""Command handlers and orchestration helpers for the `buildish-release-tooling` CLI."""

from apache_buildish_release_tooling.commands.branching import (
    run_create_release_branch,
    run_verify_source_ref_checks,
)
from apache_buildish_release_tooling.commands.materialization import (
    run_create_rc_materialization_tag,
    run_materialize_rc_git_content,
)
from apache_buildish_release_tooling.commands.rc_preparation import (
    run_build_source_rc,
    run_cleanup_dev_svn_rcs,
    run_create_source_artifact,
    run_prepare_rc,
)
from apache_buildish_release_tooling.commands.release_publication import (
    run_create_final_tag,
    run_finalize_draft_github_release,
    run_prune_older_line_releases,
    run_publish_source_release_svn,
    run_release_version,
    run_sync_draft_github_release,
    run_verify_rc,
)
from apache_buildish_release_tooling.commands.secondary_targets import (
    run_attach_github_release_assets,
    run_publish_dockerhub_moving_tags,
    run_update_moving_image_aliases,
    run_update_moving_tags,
)
from apache_buildish_release_tooling.commands.vote_materials import (
    run_finalize_rc_vote_materials,
)

__all__ = [
    "run_attach_github_release_assets",
    "run_build_source_rc",
    "run_cleanup_dev_svn_rcs",
    "run_create_final_tag",
    "run_create_rc_materialization_tag",
    "run_create_release_branch",
    "run_create_source_artifact",
    "run_finalize_draft_github_release",
    "run_finalize_rc_vote_materials",
    "run_materialize_rc_git_content",
    "run_prepare_rc",
    "run_prune_older_line_releases",
    "run_publish_dockerhub_moving_tags",
    "run_publish_source_release_svn",
    "run_release_version",
    "run_sync_draft_github_release",
    "run_update_moving_image_aliases",
    "run_update_moving_tags",
    "run_verify_rc",
    "run_verify_source_ref_checks",
]
