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

"""Secondary-artifact registration commands."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from buildish_release_tooling.release.artifact_registration import (
    build_artifact_registration,
)
from buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationBundle,
)
from buildish_release_tooling.release.command_manifests import (
    RecordArtifactManifest,
)
from buildish_release_tooling.release.contracts import SecondaryArtifactManifestV1
from buildish_release_tooling.release.manifest import write_manifest

from buildish_release_tooling.release.commands._shared import (
    _append_github_outputs,
    _artifact_output_dir,
    _context,
    _manifest_path,
)


def _registration_output_paths(args: Namespace, component_id: str) -> tuple[Path, Path]:
    output_path_text = getattr(args, "output_path", None)
    output_dir_text = getattr(args, "output_dir", None)
    if output_path_text and output_dir_text:
        raise ValueError("record-artifact accepts at most one of --output-path or --output-dir")
    if output_path_text:
        manifest_path = Path(output_path_text).resolve()
        return manifest_path.parent, manifest_path
    if output_dir_text:
        bundle_dir = Path(output_dir_text).resolve()
    else:
        bundle_dir = (
            _artifact_output_dir(component_id) / "secondary-artifacts" / args.artifact_id
        ).resolve()
    return bundle_dir, bundle_dir / "artifact-manifest.json"


def _registration_bundle(
    args: Namespace,
    *,
    component_id: str,
) -> ArtifactRegistrationBundle:
    bundle_dir, manifest_path = _registration_output_paths(args, component_id)
    registration = build_artifact_registration(args, bundle_dir)
    manifest_payload = SecondaryArtifactManifestV1(
        secondary_artifacts=[registration.secondary_artifact]
    )
    write_manifest(manifest_path, manifest_payload, exclude_none=True)
    return ArtifactRegistrationBundle(
        bundle_dir=bundle_dir,
        manifest_path=manifest_path,
        manifest_payload=manifest_payload,
        inventory_paths=registration.inventory_paths,
    )


def run_record_artifact(args: Namespace) -> Path:
    """Write one typed secondary-artifact manifest fragment."""

    context = _context(args)
    bundle = _registration_bundle(args, component_id=context.release_config.component.id)
    action_manifest_path = _manifest_path(
        context.release_config.component.id,
        f"record-artifact-{args.artifact_id}",
    )
    write_manifest(
        action_manifest_path,
        RecordArtifactManifest(
            component=context.release_config.component.id,
            artifact_id=args.artifact_id,
            kind=args.kind,
            artifact_manifest_path=str(bundle.manifest_path),
            artifact_bundle_dir=str(bundle.bundle_dir),
            inventory_paths=[str(path) for path in bundle.inventory_paths],
        ),
    )
    _append_github_outputs(
        {
            "artifact_id": args.artifact_id,
            "artifact_kind": args.kind,
            "artifact_manifest_path": str(bundle.manifest_path),
            "artifact_bundle_dir": str(bundle.bundle_dir),
        }
    )
    return bundle.manifest_path
