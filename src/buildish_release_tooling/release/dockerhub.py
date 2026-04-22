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

"""Docker Hub helpers for release-time moving tag publication."""

from __future__ import annotations

import os
from dataclasses import dataclass

from buildish_release_tooling.release.process import run_logged_command


@dataclass(frozen=True, slots=True)
class ImageReference:
    """Structured view of one container-image reference string."""

    repository: str
    tag: str | None
    digest: str | None


def dockerhub_credentials_from_environment() -> tuple[str, str]:
    """Return the Docker Hub username and token required for remote alias publication."""

    user = os.environ.get("DOCKERHUB_USER", "").strip()
    token = os.environ.get("DOCKERHUB_TOKEN", "").strip()
    if not user or not token:
        raise ValueError("DOCKERHUB_USER and DOCKERHUB_TOKEN are required for Docker Hub publication")
    return user, token


def parse_image_reference(reference: str) -> ImageReference:
    """Parse a registry image reference into repository, tag, and digest components."""

    main_part, at_sign, digest = reference.partition("@")
    digest_value = digest if at_sign else None
    last_slash = main_part.rfind("/")
    last_colon = main_part.rfind(":")
    tag_value: str | None = None
    repository = main_part
    if last_colon > last_slash:
        repository = main_part[:last_colon]
        tag_value = main_part[last_colon + 1 :]
    if not repository:
        raise ValueError(f"invalid image reference: {reference}")
    return ImageReference(repository=repository, tag=tag_value or None, digest=digest_value or None)


def login_to_dockerhub() -> str:
    """Authenticate the Docker CLI against Docker Hub and return the login username."""

    user, token = dockerhub_credentials_from_environment()
    run_logged_command(
        ["docker", "login", "docker.io", "--username", user, "--password-stdin"],
        input_text=f"{token}\n",
        extra_secret_values=(user, token),
    )
    return user


def publish_moving_aliases(*, source_image: str, target_alias_refs: list[str]) -> list[str]:
    """Publish moving Docker Hub aliases that point at one already-pushed source image."""

    if not target_alias_refs:
        return []
    _user = login_to_dockerhub()
    published_alias_refs: list[str] = []
    for target_alias_ref in target_alias_refs:
        run_logged_command(
            [
                "docker",
                "buildx",
                "imagetools",
                "create",
                "--prefer-index=false",
                "--tag",
                target_alias_ref,
                source_image,
            ]
        )
        published_alias_refs.append(target_alias_ref)
    return published_alias_refs
