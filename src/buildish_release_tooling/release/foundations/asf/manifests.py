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

"""Typed ASF publication and vote extensions for stable release manifests."""

from typing import Literal

from pydantic import Field

from buildish_release_tooling.docs.documentation import ToolingDerivedModel
from buildish_release_tooling.release.core.manifests import AuthenticityReference


class AsfCandidatePublication(ToolingDerivedModel):
    """ASF dist/dev publication evidence for one exact candidate."""

    kind: Literal["asf-candidate-publication"] = Field(
        default="asf-candidate-publication", description="Extension discriminator."
    )
    dist_uri: str = Field(description="Exact ASF dist/dev candidate directory URI.")
    svn_revision: int = Field(ge=1, description="Committed ASF dist SVN revision.")


class AsfFinalPublication(ToolingDerivedModel):
    """ASF dist/release publication evidence for one final release."""

    kind: Literal["asf-final-publication"] = Field(
        default="asf-final-publication", description="Extension discriminator."
    )
    dist_uri: str = Field(description="Exact ASF dist/release version directory URI.")
    svn_revision: int = Field(ge=1, description="Committed ASF dist SVN revision.")


class AsfVoteExtension(ToolingDerivedModel):
    """ASF-specific vote rendering, trust-root, and disclaimer evidence."""

    kind: Literal["asf-vote"] = Field(
        default="asf-vote", description="Vote extension discriminator."
    )
    style: Literal["pmc", "ppmc-ipmc"] = Field(description="ASF vote terminology style.")
    keys: AuthenticityReference = Field(description="ASF KEYS trust-root reference.")
    disclaimer_uri: str | None = Field(
        default=None, description="Optional Incubator disclaimer evidence URI."
    )
