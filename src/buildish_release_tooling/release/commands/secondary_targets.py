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

"""Secondary-target publication commands for Git tags, images, and release assets."""

from __future__ import annotations

from argparse import Namespace
import shutil

from buildish_release_tooling.release.config import (
    latest_tag_enabled,
    moving_tags_enabled,
    require_openpgp_signing,
    secondary_target_kinds,
)
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from buildish_release_tooling.release.dockerhub import (
    parse_image_reference,
    publish_moving_aliases,
)
from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.platforms.github.checks import (
    resolve_repository_slug,
)
from buildish_release_tooling.release.platforms.github.selection import (
    asset_release_url,
)
from buildish_release_tooling.release.platforms.github.releases import (
    list_releases,
    release_by_tag,
    upload_release_assets,
)
from buildish_release_tooling.release.signing.openpgp import (
    OpenPgpSigner,
    OpenPgpSigningInput,
)
from buildish_release_tooling.release.command_manifests import (
    AttachGitHubReleaseAssetsManifest,
    PrepareReleaseAssetsManifest,
    PublishDockerhubMovingTagsManifest,
    UpdateMovingImageAliasesManifest,
    UpdateMovingTagsManifest,
)
from buildish_release_tooling.release.manifest import write_manifest
from buildish_release_tooling.release.core.models import ArtifactReference
from buildish_release_tooling.release.core.naming import (
    derive_final_tag,
    derive_moving_tags,
)
from buildish_release_tooling.release.platforms.github.direct import (
    observed_release_assets,
)
from buildish_release_tooling.release.publications._adapter import (
    DURABLE_EVIDENCE_ASSET_PREFIX,
)
from buildish_release_tooling.release.source_artifact import (
    checksum,
    write_checksum_file,
)
from buildish_release_tooling.release.summary import SummaryWriter

from buildish_release_tooling.release.commands._shared import (
    _context,
    _create_or_reuse_annotated_tag,
    _final_version_for_commit,
    _manifest_path,
    _repository_slug_or_none,
    _should_move_alias,
    _temporary_build_dir,
)


@dataclass(frozen=True)
class PreparedReleaseAssetUploads:
    """Generated checksum/signature sidecars and the final upload set for one release."""

    upload_paths: list[Path]
    checksum_algorithms: list[str]
    generated_checksum_lines: list[str]
    generated_checksum_paths: list[Path]
    generated_signature_paths: list[Path]
    gpg_fingerprint: str


def _asset_paths(arguments: Iterable[str]) -> list[Path]:
    """Resolve asset arguments to existing files."""

    asset_paths: list[Path] = []
    for argument in arguments:
        asset_path = Path(argument)
        if not asset_path.is_file():
            raise ValueError(f"asset file does not exist: {asset_path}")
        asset_paths.append(asset_path)
    if not asset_paths:
        raise ValueError("at least one asset file is required")
    return asset_paths


def _deduplicated_checksum_algorithms(algorithms: Iterable[str]) -> list[str]:
    """Return checksum algorithms in first-seen order without duplicates."""

    deduplicated: list[str] = []
    for algorithm in algorithms:
        normalized_algorithm = algorithm.lower()
        if normalized_algorithm not in deduplicated:
            deduplicated.append(normalized_algorithm)
    return deduplicated


def _assert_unique_upload_asset_names(asset_paths: Iterable[Path]) -> None:
    """Reject upload plans that would collide on GitHub asset basenames."""

    seen_names: set[str] = set()
    for asset_path in asset_paths:
        if asset_path.name in seen_names:
            raise ValueError(f"duplicate GitHub Release asset name: {asset_path.name}")
        seen_names.add(asset_path.name)


def _sign_release_assets(
    asset_paths: list[Path], signing_input: OpenPgpSigningInput
) -> tuple[list[Path], str]:
    """Generate detached ASCII-armored signatures for one set of release assets."""

    with _temporary_build_dir("attach-github-release-assets") as temp_root:
        gpg_home = temp_root / "gnupg"
        signer = OpenPgpSigner.from_environment(gpg_home, signing_input)
        signature_paths: list[Path] = []
        for asset_path in asset_paths:
            signature_path = asset_path.with_name(f"{asset_path.name}.asc")
            signer.sign_file(asset_path, signature_path)
            signature_paths.append(signature_path)
        return signature_paths, signer.fingerprint


def _prepare_release_asset_uploads(
    asset_paths: list[Path],
    checksum_algorithms: list[str],
    *,
    sign: bool,
    signing_input: OpenPgpSigningInput | None,
) -> PreparedReleaseAssetUploads:
    """Generate checksum/signature sidecars and the final GitHub Release upload set."""

    upload_paths = list(asset_paths)
    generated_checksum_lines: list[str] = []
    generated_checksum_paths: list[Path] = []
    for asset_path in asset_paths:
        for algorithm in checksum_algorithms:
            digest_value = checksum(asset_path, algorithm)
            checksum_path = write_checksum_file(asset_path, algorithm, digest_value)
            generated_checksum_lines.append(
                f"{algorithm}:{digest_value}  {asset_path.name}"
            )
            generated_checksum_paths.append(checksum_path)
            upload_paths.append(checksum_path)

    generated_signature_paths: list[Path] = []
    gpg_fingerprint = ""
    if sign:
        if signing_input is None:
            raise ValueError("signing_input is required when sign is enabled")
        generated_signature_paths, gpg_fingerprint = _sign_release_assets(
            asset_paths, signing_input
        )
        upload_paths.extend(generated_signature_paths)

    return PreparedReleaseAssetUploads(
        upload_paths=upload_paths,
        checksum_algorithms=checksum_algorithms,
        generated_checksum_lines=generated_checksum_lines,
        generated_checksum_paths=generated_checksum_paths,
        generated_signature_paths=generated_signature_paths,
        gpg_fingerprint=gpg_fingerprint,
    )


def run_prepare_release_assets(args: Namespace) -> Path:
    """Copy primary assets and create every configured integrity sidecar."""

    context = _context(args)
    source_paths = _asset_paths(args.assets)
    _assert_unique_upload_asset_names(source_paths)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError(
            f"prepared release-asset output directory is not empty: {output_dir}"
        )

    primary_paths: list[Path] = []
    for source_path in source_paths:
        target_path = output_dir / source_path.name
        shutil.copyfile(source_path, target_path)
        target_path.chmod(0o644)
        primary_paths.append(target_path)

    signing_config = context.release_config.artifacts.signing
    expected_fingerprint = args.expected_signing_fingerprint
    if expected_fingerprint is not None:
        normalized_expected = "".join(expected_fingerprint.split()).upper()
        configured_expected = (
            signing_config.expected_fingerprint if signing_config is not None else None
        )
        if normalized_expected != configured_expected:
            raise ValueError(
                "runtime signing fingerprint does not match the release configuration"
            )

    prepared = _prepare_release_asset_uploads(
        primary_paths,
        _deduplicated_checksum_algorithms(context.release_config.artifacts.checksums),
        sign=signing_config is not None,
        signing_input=(
            OpenPgpSigningInput.from_config(signing_config)
            if signing_config is not None
            else None
        ),
    )
    _assert_unique_upload_asset_names(prepared.upload_paths)

    result = PrepareReleaseAssetsManifest(
        component=context.release_config.component.id,
        output_directory=str(output_dir.resolve()),
        primary_asset_names=[path.name for path in primary_paths],
        prepared_asset_names=[path.name for path in prepared.upload_paths],
        generated_checksum_asset_names=[
            path.name for path in prepared.generated_checksum_paths
        ],
        generated_signature_asset_names=[
            path.name for path in prepared.generated_signature_paths
        ],
        checksum_algorithms=prepared.checksum_algorithms,
        gpg_fingerprint=prepared.gpg_fingerprint,
    )
    result_path = _manifest_path(
        context.release_config.component.id,
        "prepare-release-assets",
    )
    write_manifest(result_path, result)
    summary = SummaryWriter.from_environment()
    summary.append_heading("Prepare release assets")
    summary.append_plaintext_block("Output directory", str(output_dir.resolve()))
    summary.append_plaintext_block(
        "Prepared assets",
        "\n".join(path.name for path in prepared.upload_paths),
    )
    if prepared.gpg_fingerprint:
        summary.append_plaintext_block("GPG signing key", prepared.gpg_fingerprint)
    return result_path


def run_update_moving_tags(args: Namespace) -> Path:
    """Move Git tag-backed aliases such as GitHub Action major/minor tags without rollback."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    if "github-action" not in secondary_target_kinds(context.release_config):
        raise ValueError(
            "update-moving-tags currently supports only github-action aliases"
        )
    final_tag = derive_final_tag(version)
    if not repo.tag_exists(final_tag):
        raise ValueError(f"final tag does not exist: {final_tag}")
    target_commit = repo.resolve_commit(final_tag)
    repository_slug = _repository_slug_or_none(repo)
    moving_tags = derive_moving_tags(
        version,
        secondary_target_kinds(context.release_config),
        moving_tags_enabled(context.release_config),
        latest_tag_enabled(context.release_config),
    )
    updated_tags: list[str] = []
    skipped_tags: list[str] = []
    tag_update_modes: list[str] = []
    for moving_tag in moving_tags:
        current_version: str | None = None
        if repo.tag_exists(moving_tag):
            current_version = _final_version_for_commit(
                repo, repo.resolve_commit(moving_tag)
            )
            if current_version is None:
                raise ValueError(
                    f"moving alias does not point at a known final release: {moving_tag}"
                )
        if not _should_move_alias(moving_tag, version, current_version):
            skipped_tags.append(moving_tag)
            continue
        tag_update_mode, _updated_ref = _create_or_reuse_annotated_tag(
            repo=repo,
            repository_slug=repository_slug,
            tag_name=moving_tag,
            target_commit=target_commit,
            message=f"Move {moving_tag} to {final_tag}",
            allow_update=True,
        )
        updated_tags.append(moving_tag)
        tag_update_modes.append(f"{moving_tag}:{tag_update_mode}")
    manifest_path = _manifest_path(
        context.release_config.component.id, "update-moving-tags"
    )
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        UpdateMovingTagsManifest(
            component=context.release_config.component.id,
            version=version,
            final_tag=final_tag,
            target_commit=target_commit,
            updated_tags=updated_tags,
            skipped_tags=skipped_tags,
            tag_update_modes=tag_update_modes,
        ),
    )
    summary.append_heading("Update moving tags")
    summary.append_plaintext_block("Final tag", final_tag)
    summary.append_plaintext_block("Target commit", target_commit)
    summary.append_plaintext_block(
        "Updated aliases", "\n".join(updated_tags) if updated_tags else "<none>"
    )
    summary.append_plaintext_block(
        "Skipped aliases", "\n".join(skipped_tags) if skipped_tags else "<none>"
    )
    return manifest_path


def run_update_moving_image_aliases(args: Namespace) -> Path:
    """Resolve the concrete moving container-image aliases for a released version."""

    context = _context(args)
    version = args.version
    image_aliases = derive_moving_tags(
        version,
        secondary_target_kinds(context.release_config),
        moving_tags_enabled(context.release_config),
        latest_tag_enabled(context.release_config),
    )
    manifest_path = _manifest_path(
        context.release_config.component.id, "update-moving-image-aliases"
    )
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        UpdateMovingImageAliasesManifest(
            component=context.release_config.component.id,
            version=version,
            exact_image_tag=version,
            image_aliases=image_aliases,
        ),
    )
    summary.append_heading("Update moving image aliases")
    summary.append_plaintext_block("Exact image tag", version)
    summary.append_plaintext_block(
        "Derived image aliases",
        " ".join(image_aliases) if image_aliases else "<none>",
    )
    return manifest_path


def run_publish_dockerhub_moving_tags(args: Namespace) -> Path:
    """Publish moving Docker Hub aliases for one already-pushed exact image reference."""

    context = _context(args)
    if "dockerhub" not in secondary_target_kinds(context.release_config):
        raise ValueError(
            "publish-dockerhub-moving-tags requires the dockerhub secondary target"
        )
    version = args.version
    source_image = args.source_image
    image_reference = parse_image_reference(source_image)
    if image_reference.tag is None and image_reference.digest is None:
        raise ValueError(
            "source image must include the released version tag or an exact digest"
        )
    if (
        image_reference.tag is not None
        and image_reference.digest is None
        and image_reference.tag != version
    ):
        raise ValueError(
            f"source image tag {image_reference.tag} does not match released version {version}"
        )
    image_aliases = derive_moving_tags(
        version,
        secondary_target_kinds(context.release_config),
        moving_tags_enabled(context.release_config),
        latest_tag_enabled(context.release_config),
    )
    target_alias_refs = [
        f"{image_reference.repository}:{alias}" for alias in image_aliases
    ]
    published_alias_refs = publish_moving_aliases(
        source_image=source_image,
        target_alias_refs=target_alias_refs,
    )
    manifest_path = _manifest_path(
        context.release_config.component.id, "publish-dockerhub-moving-tags"
    )
    summary = SummaryWriter.from_environment()
    write_manifest(
        manifest_path,
        PublishDockerhubMovingTagsManifest(
            component=context.release_config.component.id,
            version=version,
            source_image=source_image,
            image_repository=image_reference.repository,
            published_alias_refs=published_alias_refs,
        ),
    )
    summary.append_heading("Publish Docker Hub moving tags")
    summary.append_plaintext_block("Source image", source_image)
    summary.append_plaintext_block("Image repository", image_reference.repository)
    summary.append_plaintext_block(
        "Published alias refs",
        "\n".join(published_alias_refs) if published_alias_refs else "<none>",
    )
    return manifest_path


def run_attach_github_release_assets(args: Namespace) -> Path:
    """Upload one or more convenience assets to the GitHub Release for one final version."""

    context = _context(args)
    repo = GitRepository.from_current_worktree()
    version = args.version
    final_tag = derive_final_tag(version)
    repository_slug = resolve_repository_slug(repo.path)
    release_payload = release_by_tag(list_releases(repository_slug), tag_name=final_tag)
    release_id = release_payload.get("id")
    if not isinstance(release_id, int):
        raise ValueError(
            f"GitHub Release for {final_tag} does not include a numeric id"
        )
    asset_paths = _asset_paths(args.assets)
    if args.immutable and (args.sign or args.checksum_algorithms):
        raise ValueError(
            "immutable GitHub Release asset attachment does not generate sidecars"
        )
    if args.immutable and any(
        not path.name.startswith(DURABLE_EVIDENCE_ASSET_PREFIX) for path in asset_paths
    ):
        raise ValueError(
            "immutable verification-evidence asset names must use the reserved prefix: "
            f"{DURABLE_EVIDENCE_ASSET_PREFIX}"
        )
    prepared_uploads = _prepare_release_asset_uploads(
        asset_paths,
        _deduplicated_checksum_algorithms(args.checksum_algorithms),
        sign=args.sign,
        signing_input=(
            OpenPgpSigningInput.from_config(
                require_openpgp_signing(context.release_config)
            )
            if args.sign
            else None
        ),
    )
    _assert_unique_upload_asset_names(prepared_uploads.upload_paths)
    primary_assets = [
        ArtifactReference(
            kind="verification-evidence" if args.immutable else "release-asset",
            logical_name=asset_path.name,
            digests={"sha256": checksum(asset_path, "sha256")},
            size_bytes=asset_path.stat().st_size,
        )
        for asset_path in asset_paths
    ]
    uploaded_paths: list[Path]
    if args.immutable:
        observed_before = observed_release_assets(release_payload)
        uploaded_paths = []
        for asset_path, asset in zip(asset_paths, primary_assets, strict=True):
            observed = observed_before.get(asset.logical_name)
            if observed is None:
                uploaded_paths.append(asset_path)
            elif (
                observed.size_bytes != asset.size_bytes
                or observed.digest != f"sha256:{asset.digests['sha256']}"
            ):
                raise ValueError(
                    f"immutable GitHub Release asset already differs: {asset.logical_name}"
                )
        if uploaded_paths:
            upload_release_assets(
                repository_slug,
                tag_name=final_tag,
                asset_paths=uploaded_paths,
                clobber=False,
            )
    else:
        uploaded_paths = prepared_uploads.upload_paths
        upload_release_assets(
            repository_slug,
            tag_name=final_tag,
            asset_paths=prepared_uploads.upload_paths,
            clobber=True,
        )
    release_payload = release_by_tag(list_releases(repository_slug), tag_name=final_tag)
    observed_assets = observed_release_assets(release_payload)
    for asset in primary_assets:
        observed = observed_assets.get(asset.logical_name)
        if (
            observed is None
            or observed.size_bytes != asset.size_bytes
            or observed.digest != f"sha256:{asset.digests['sha256']}"
        ):
            raise ValueError(
                f"GitHub Release evidence asset differs after upload: {asset.logical_name}"
            )

    manifest_path = _manifest_path(
        context.release_config.component.id, "attach-github-release-assets"
    )
    summary = SummaryWriter.from_environment()
    release_name = release_payload.get("name")
    release_tag = release_payload.get("tag_name")
    release_url = asset_release_url(release_payload)
    write_manifest(
        manifest_path,
        AttachGitHubReleaseAssetsManifest(
            component=context.release_config.component.id,
            version=version,
            repository_slug=repository_slug,
            release_id=str(release_id),
            release_name=str(release_name or ""),
            release_tag=str(release_tag or ""),
            release_url=release_url,
            primary_asset_names=[asset_path.name for asset_path in asset_paths],
            primary_assets=primary_assets,
            uploaded_asset_names=[upload_path.name for upload_path in uploaded_paths],
            generated_checksum_asset_names=[
                checksum_path.name
                for checksum_path in prepared_uploads.generated_checksum_paths
            ],
            generated_signature_asset_names=[
                signature_path.name
                for signature_path in prepared_uploads.generated_signature_paths
            ],
            checksum_algorithms=prepared_uploads.checksum_algorithms,
            gpg_fingerprint=prepared_uploads.gpg_fingerprint,
        ),
    )
    summary.append_heading("Attach GitHub Release assets")
    summary.append_plaintext_block("GitHub repository", repository_slug)
    summary.append_plaintext_block(
        "GitHub Release",
        "\n".join(
            [
                f"id: {release_id}",
                f"name: {release_name or ''}",
                f"tag: {release_tag or ''}",
                f"url: {release_url}",
            ]
        ),
    )
    summary.append_plaintext_block(
        "Uploaded assets",
        "\n".join(upload_path.name for upload_path in uploaded_paths),
    )
    if prepared_uploads.checksum_algorithms:
        summary.append_plaintext_block(
            "Checksum sidecars",
            "\n".join(prepared_uploads.generated_checksum_lines),
        )
    if prepared_uploads.generated_signature_paths:
        summary.append_plaintext_block(
            "Signature sidecars",
            "\n".join(
                signature_path.name
                for signature_path in prepared_uploads.generated_signature_paths
            ),
        )
        summary.append_plaintext_block(
            "GPG signing key", prepared_uploads.gpg_fingerprint
        )
    return manifest_path
