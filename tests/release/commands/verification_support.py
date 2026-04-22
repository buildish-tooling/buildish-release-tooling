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

"""Shared verify-rc command integration test support."""

from __future__ import annotations

from collections.abc import Callable
from argparse import Namespace
from dataclasses import dataclass
from subprocess import CompletedProcess
from typing import cast
import unittest

from buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    build_maven_repository_registration,
)
from buildish_release_tooling.release.artifact_registration.kinds.oci_image import (
    build_oci_image_registration,
)
from buildish_release_tooling.release.artifact_registration.kinds.python_distribution import (
    build_python_distribution_registration,
)
from buildish_release_tooling.release.signing.openpgp import (
    _effective_home,
    secret_key_fingerprint,
)
from buildish_release_tooling.release.source_artifact import create_from_git

from tests.release.archive_support import write_tgz_archive, write_zip_archive
from tests.release.commands.support import (
    Path,
    ReleaseCommandsIntegrationTestSupport,
    base64,
    cleanup_sandbox,
    cli_env,
    command_available,
    copy_test_tree,
    create_build_test_sandbox,
    create_fake_docker_launcher,
    git_create_annotated_tag,
    git_rev_parse,
    hashlib,
    init_git_origin_repo,
    json,
    os,
    run_quiet,
    run_cli,
)


@dataclass(frozen=True)
class VerificationFixture:
    """Reusable signed verification input set for one verify-rc integration test."""

    config_path: Path
    keys_url: str
    manifest_url: str
    manifest_output_path: Path
    inspection_bundle_path: Path
    origin_dir: Path
    log_path: Path
    report_json_path: Path
    report_md_path: Path
    source_commit_sha: str
    source_date_epoch: int
    work_dir: Path
    extra_env: dict[str, str]
    prepend_dirs: tuple[Path, ...]


@dataclass(frozen=True)
class BundleMetadataShapeCase:
    """One verify-rc full-mode fixture used for bundle-metadata shape coverage."""

    name: str
    build_fixture: Callable[[Path], VerificationFixture]
    expected: dict[str, dict[str, object]]


@dataclass(frozen=True)
class VerificationOriginTemplateKey:
    """Cache key for reusable origin repositories with reproducibility helper scripts."""

    include_generic_file_reproducibility: bool = False
    drift_generic_file_reproducibility: bool = False
    archive_generic_file_reproducibility: bool = False
    include_python_distribution_reproducibility: bool = False
    drift_python_distribution_reproducibility: bool = False
    archive_python_distribution_reproducibility: bool = False
    include_npm_package_reproducibility: bool = False
    drift_npm_package_reproducibility: bool = False
    archive_npm_package_reproducibility: bool = False
    include_maven_repository_reproducibility: bool = False
    drift_maven_repository_reproducibility: bool = False
    include_unrelated_local_maven_repository_files: bool = False
    include_oci_image_reproducibility: bool = False
    drift_oci_image_reproducibility: bool = False
    drift_oci_image_reproducibility_platform: bool = False


@dataclass(frozen=True)
class VerificationReproducibilityOptions:
    """Grouped fixture switches for reproducibility profiles and rebuild scripts."""

    include_generic_file: bool = False
    drift_generic_file: bool = False
    archive_generic_file: bool = False
    include_python_distribution: bool = False
    drift_python_distribution: bool = False
    archive_python_distribution: bool = False
    include_npm_package: bool = False
    drift_npm_package: bool = False
    archive_npm_package: bool = False
    include_maven_repository: bool = False
    drift_maven_repository: bool = False
    include_unrelated_local_maven_repository_files: bool = False
    include_oci_image: bool = False
    drift_oci_image: bool = False
    drift_oci_image_platform: bool = False

    def origin_template_key(self) -> VerificationOriginTemplateKey:
        return VerificationOriginTemplateKey(
            include_generic_file_reproducibility=self.include_generic_file,
            drift_generic_file_reproducibility=self.drift_generic_file,
            archive_generic_file_reproducibility=self.archive_generic_file,
            include_python_distribution_reproducibility=self.include_python_distribution,
            drift_python_distribution_reproducibility=self.drift_python_distribution,
            archive_python_distribution_reproducibility=self.archive_python_distribution,
            include_npm_package_reproducibility=self.include_npm_package,
            drift_npm_package_reproducibility=self.drift_npm_package,
            archive_npm_package_reproducibility=self.archive_npm_package,
            include_maven_repository_reproducibility=self.include_maven_repository,
            drift_maven_repository_reproducibility=self.drift_maven_repository,
            include_unrelated_local_maven_repository_files=(
                self.include_unrelated_local_maven_repository_files
            ),
            include_oci_image_reproducibility=self.include_oci_image,
            drift_oci_image_reproducibility=self.drift_oci_image,
            drift_oci_image_reproducibility_platform=self.drift_oci_image_platform,
        )

    def profile_lines(
        self,
        *,
        generic_file_kind: str | None,
        include_maven_sidecar_path_rules: bool,
        extra_lines: tuple[str, ...],
    ) -> tuple[str, ...]:
        lines: list[str] = []
        if self.include_generic_file:
            lines.extend(
                [
                    "    bootstrap-zip:",
                    f"      kind: {generic_file_kind}",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-bootstrap.sh",
                    "        output_globs:",
                    "          - dist/buildish-example-bootstrap.zip",
                    "      comparison:",
                    "        mode: exact-bytes",
                ]
            )
        if self.include_python_distribution:
            lines.extend(
                [
                    "    pypi-wheel:",
                    "      kind: python-distribution",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-wheel.sh",
                    "        output_globs:",
                    "          - dist/example-1.2.3-py3-none-any.whl",
                    "      comparison:",
                    "        mode: exact-bytes",
                ]
            )
        if self.include_npm_package:
            lines.extend(
                [
                    "    npm-package-main:",
                    "      kind: npm-package",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-npm-package.sh",
                    "        output_globs:",
                    "          - dist/buildish-example-1.2.3.tgz",
                    "      comparison:",
                    "        mode: exact-bytes",
                ]
            )
        if self.include_maven_repository:
            lines.extend(
                [
                    "    maven-staging:",
                    "      kind: maven-repository",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-maven-staging.sh",
                    "        output_globs:",
                    "          - .buildish-out/m2repo/**",
                    "      comparison:",
                    "        mode: repository-tree",
                    "        repository_dir: .buildish-out/m2repo",
                    "        require_signatures: true",
                    "        path_rules:",
                    "          - pattern: .+\\.(jar|war|zip)$",
                    "            mode: content-only",
                    "          - pattern: .+\\.(pom|module)$",
                    "            mode: exact-bytes",
                    "          - pattern: ^.*/maven-metadata\\.xml(\\..+)?$",
                    "            mode: remote-only",
                ]
            )
            if include_maven_sidecar_path_rules:
                lines.extend(
                    [
                        "          - pattern: .+\\.(asc|sha512|md5)$",
                        "            mode: remote-only",
                    ]
                )
        if self.include_oci_image:
            lines.extend(
                [
                    "    oci-main-image:",
                    "      kind: oci-image",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-oci-image.sh",
                    "        output_globs:",
                    "          - .buildish-out/oci-image-rebuilt.marker",
                    "      comparison:",
                    "        mode: platform-digest",
                    "        image_ref: ghcr.io/buildish-tooling/buildish-example:rebuild-local",
                ]
            )
        lines.extend(extra_lines)
        return tuple(lines)


@dataclass(frozen=True)
class CachedCommandResult:
    """In-memory copy of one finished CLI invocation used by fixture-family caches."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CachedVerificationFamily:
    """Prepared verification sandbox plus its finished verify-rc result."""

    cache_root: Path
    fixture: VerificationFixture
    verify_completed: CachedCommandResult


class VerificationCommandsIntegrationTestBase(ReleaseCommandsIntegrationTestSupport):
    """Shared fixture and assertion support for verify-rc command tests."""

    _baseline_root: Path

    _origin_template: Path

    _gpg_home_template: Path

    _origin_templates: dict[VerificationOriginTemplateKey, Path]

    _cached_verification_families: dict[str, CachedVerificationFamily]

    _cached_inspect_results: dict[tuple[str, tuple[str, ...]], CachedCommandResult]

    _public_key: str

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not command_available("gpg"):
            raise unittest.SkipTest(
                "gpg is required for verify-rc integration coverage"
            )
        cls._baseline_root = create_build_test_sandbox()
        cls._origin_template = init_git_origin_repo(
            cls._baseline_root, dir_name="origin-template"
        )
        cls._origin_templates = {}
        cls._cached_verification_families = {}
        cls._cached_inspect_results = {}
        gpg_home = cls._baseline_root / "gpg-home-template"
        gpg_home.mkdir(parents=True, exist_ok=True)
        gpg_home.chmod(0o700)
        run_quiet(
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
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        )
        cls._public_key = run_quiet(
            [
                "gpg",
                "--armor",
                "--export",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        ).stdout
        run_quiet(
            ["gpgconf", "--kill", "all"],
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        )
        for stale_path in gpg_home.glob("S.gpg-agent*"):
            stale_path.unlink(missing_ok=True)
        cls._gpg_home_template = gpg_home

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_sandbox(cls._baseline_root)
        super().tearDownClass()

    @classmethod
    def _origin_template_for(
        cls,
        key: VerificationOriginTemplateKey,
    ) -> Path:
        if not any(key.__dict__.values()):
            return cls._origin_template
        cached = cls._origin_templates.get(key)
        if cached is not None:
            return cached

        template_index = len(cls._origin_templates) + 1
        template_path = copy_test_tree(
            cls._origin_template,
            cls._baseline_root / f"origin-template-{template_index:02d}",
        )
        cls._materialize_origin_template(template_path, key)
        cls._origin_templates[key] = template_path
        return template_path

    @classmethod
    def _materialize_origin_template(
        cls,
        origin_dir: Path,
        key: VerificationOriginTemplateKey,
    ) -> None:
        if key.include_generic_file_reproducibility:
            rebuild_script = (
                origin_dir / "buildish-release-tooling" / "rebuild-bootstrap.sh"
            )
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            if key.archive_generic_file_reproducibility:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            "python - <<'PY'",
                            "from pathlib import Path",
                            "import zipfile",
                            "archive_path = Path('dist/buildish-example-bootstrap.zip')",
                            "payload = b'bootstrap zip bytes\\n'",
                            (
                                "payload = b'bootstrap zip drift\\n'"
                                if key.drift_generic_file_reproducibility
                                else "payload = payload"
                            ),
                            "with zipfile.ZipFile(archive_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:",
                            "    info = zipfile.ZipInfo('bootstrap.txt', date_time=(2026, 4, 30, 12, 0, 1))",
                            "    info.compress_type = zipfile.ZIP_DEFLATED",
                            "    info.external_attr = 0o100644 << 16",
                            "    archive.writestr(info, payload)",
                            "PY",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            else:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            (
                                "printf 'bootstrap zip bytes\\n' > dist/buildish-example-bootstrap.zip"
                                if not key.drift_generic_file_reproducibility
                                else "printf 'bootstrap zip drift\\n' > dist/buildish-example-bootstrap.zip"
                            ),
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            rebuild_script.chmod(0o755)
            local_override_script = (
                origin_dir / "buildish-release-tooling" / "rebuild-bootstrap-local.sh"
            )
            local_override_script.write_text(
                rebuild_script.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            local_override_script.chmod(0o755)
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "add",
                    "buildish-release-tooling/rebuild-bootstrap.sh",
                    "buildish-release-tooling/rebuild-bootstrap-local.sh",
                ],
                check=True,
            )
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "commit",
                    "-m",
                    "add bootstrap rebuild script",
                ],
                check=True,
            )

        if key.include_python_distribution_reproducibility:
            rebuild_script = (
                origin_dir / "buildish-release-tooling" / "rebuild-wheel.sh"
            )
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            if key.archive_python_distribution_reproducibility:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            "python - <<'PY'",
                            "from pathlib import Path",
                            "import zipfile",
                            "archive_path = Path('dist/example-1.2.3-py3-none-any.whl')",
                            "payload = b'wheel payload\\n'",
                            (
                                "payload = b'wheel payload drift\\n'"
                                if key.drift_python_distribution_reproducibility
                                else "payload = payload"
                            ),
                            "with zipfile.ZipFile(archive_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:",
                            "    info = zipfile.ZipInfo('example/__init__.py', date_time=(2026, 4, 30, 12, 0, 1))",
                            "    info.compress_type = zipfile.ZIP_DEFLATED",
                            "    info.external_attr = 0o100644 << 16",
                            "    archive.writestr(info, payload)",
                            "PY",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            else:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            (
                                "printf 'wheel payload\\n' > dist/example-1.2.3-py3-none-any.whl"
                                if not key.drift_python_distribution_reproducibility
                                else "printf 'wheel payload drift\\n' > dist/example-1.2.3-py3-none-any.whl"
                            ),
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            rebuild_script.chmod(0o755)
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "add",
                    "buildish-release-tooling/rebuild-wheel.sh",
                ],
                check=True,
            )
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "commit",
                    "-m",
                    "add wheel rebuild script",
                ],
                check=True,
            )

        if key.include_npm_package_reproducibility:
            rebuild_script = (
                origin_dir / "buildish-release-tooling" / "rebuild-npm-package.sh"
            )
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            if key.archive_npm_package_reproducibility:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            "python - <<'PY'",
                            "from io import BytesIO",
                            "from pathlib import Path",
                            "import tarfile",
                            "archive_path = Path('dist/buildish-example-1.2.3.tgz')",
                            "payload = b'npm package payload\\n'",
                            (
                                "payload = b'npm package payload drift\\n'"
                                if key.drift_npm_package_reproducibility
                                else "payload = payload"
                            ),
                            "with tarfile.open(archive_path, mode='w:gz') as archive:",
                            "    info = tarfile.TarInfo('package/package.json')",
                            "    info.size = len(payload)",
                            "    info.mtime = 1714435201",
                            "    info.mode = 0o644",
                            "    archive.addfile(info, BytesIO(payload))",
                            "PY",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            else:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            (
                                "printf 'npm package payload\\n' > dist/buildish-example-1.2.3.tgz"
                                if not key.drift_npm_package_reproducibility
                                else "printf 'npm package payload drift\\n' > dist/buildish-example-1.2.3.tgz"
                            ),
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            rebuild_script.chmod(0o755)
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "add",
                    "buildish-release-tooling/rebuild-npm-package.sh",
                ],
                check=True,
            )
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "commit",
                    "-m",
                    "add npm rebuild script",
                ],
                check=True,
            )

        if key.include_maven_repository_reproducibility:
            rebuild_script = (
                origin_dir / "buildish-release-tooling" / "rebuild-maven-staging.sh"
            )
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            rebuild_script.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env sh",
                        "set -eu",
                        "repo_root=.buildish-out/m2repo/org/example/app/1.0.0",
                        'mkdir -p "$repo_root"',
                        "python - <<'PY'",
                        "from pathlib import Path",
                        "import zipfile",
                        "repo_root = Path('.buildish-out/m2repo/org/example/app/1.0.0')",
                        "jar_path = repo_root / 'app-1.0.0.jar'",
                        "with zipfile.ZipFile(jar_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:",
                        "    info = zipfile.ZipInfo('app.txt', date_time=(2026, 4, 30, 12, 0, 2))",
                        "    info.compress_type = zipfile.ZIP_DEFLATED",
                        "    archive.writestr(info, b'jar payload\\n')",
                        "PY",
                        (
                            "printf '<project>drift</project>\\n' > \"$repo_root/app-1.0.0.pom\""
                            if key.drift_maven_repository_reproducibility
                            else "printf '<project>stable</project>\\n' > \"$repo_root/app-1.0.0.pom\""
                        ),
                        (
                            "\n".join(
                                [
                                    "extra_root=.buildish-out/m2repo/com/example/dependency/2.0.0",
                                    'mkdir -p "$extra_root"',
                                    "printf 'dependency bytes\\n' > \"$extra_root/dependency-2.0.0.jar\"",
                                ]
                            )
                            if key.include_unrelated_local_maven_repository_files
                            else ""
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rebuild_script.chmod(0o755)
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "add",
                    "buildish-release-tooling/rebuild-maven-staging.sh",
                ],
                check=True,
            )
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "commit",
                    "-m",
                    "add maven rebuild script",
                ],
                check=True,
            )

        if key.include_oci_image_reproducibility:
            rebuild_script = (
                origin_dir / "buildish-release-tooling" / "rebuild-oci-image.sh"
            )
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            rebuilt_top_level_digest = "sha256:" + (
                (
                    "e5"
                    if key.drift_oci_image_reproducibility
                    or key.drift_oci_image_reproducibility_platform
                    else "d4"
                )
                * 32
            )
            rebuilt_amd64_digest = "sha256:" + ("a1" * 32)
            rebuilt_arm64_digest = "sha256:" + (
                ("c3" if key.drift_oci_image_reproducibility_platform else "b2") * 32
            )
            rebuild_script.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env sh",
                        "set -eu",
                        "mkdir -p .buildish-out",
                        "printf 'rebuilt\\n' > .buildish-out/oci-image-rebuilt.marker",
                        "cat > \"$FAKE_DOCKER_STATE_DIR/imagetools-inspect-response.json\" <<'JSON'",
                        json.dumps(
                            {
                                "schemaVersion": 2,
                                "mediaType": "application/vnd.oci.image.index.v1+json",
                                "digest": rebuilt_top_level_digest,
                                "manifests": [
                                    {
                                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                        "digest": rebuilt_amd64_digest,
                                        "platform": {
                                            "architecture": "amd64",
                                            "os": "linux",
                                        },
                                    },
                                    {
                                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                        "digest": rebuilt_arm64_digest,
                                        "platform": {
                                            "architecture": "arm64",
                                            "os": "linux",
                                        },
                                    },
                                ],
                            }
                        ),
                        "JSON",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rebuild_script.chmod(0o755)
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "add",
                    "buildish-release-tooling/rebuild-oci-image.sh",
                ],
                check=True,
            )
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "commit",
                    "-m",
                    "add oci rebuild script",
                ],
                check=True,
            )

    @staticmethod
    def _repro_shape(payload: dict[str, object] | None) -> dict[str, object] | None:
        if payload is None:
            return None
        canonical_recipe = payload.get("canonical_recipe")
        effective_execution = payload.get("effective_execution")
        override = payload.get("override")
        return {
            "keys": list(payload),
            "verdict": payload.get("verdict"),
            "profile_id": payload.get("profile_id"),
            "comparison_mode": payload.get("comparison_mode"),
            "canonical_recipe_keys": list(canonical_recipe)
            if isinstance(canonical_recipe, dict)
            else None,
            "effective_execution_keys": (
                list(effective_execution)
                if isinstance(effective_execution, dict)
                else None
            ),
            "override_keys": list(override) if isinstance(override, dict) else None,
            "override_applied": override.get("applied")
            if isinstance(override, dict)
            else None,
        }

    def _report_shape(self, payload: dict[str, object]) -> dict[str, object]:
        source_verification = payload["source_artifact_verification"]
        if not isinstance(source_verification, dict):
            self.fail("source_artifact_verification must be an object")
        secondary_verifications = payload["secondary_artifact_verifications"]
        if not isinstance(secondary_verifications, list):
            self.fail("secondary_artifact_verifications must be a list")
        failures = payload["failures"]
        if not isinstance(failures, list):
            self.fail("failures must be a list")
        inspection_bundle = payload.get("inspection_bundle")
        if inspection_bundle is not None and not isinstance(inspection_bundle, dict):
            self.fail("inspection_bundle must be an object when present")
        return {
            "top_level_keys": list(payload),
            "verdict": payload["verdict"],
            "failure_count": len(failures),
            "inspection_bundle_keys": list(inspection_bundle)
            if inspection_bundle is not None
            else None,
            "source_repro": self._repro_shape(
                source_verification.get("reproducibility")
            ),
            "secondary_repro": {
                verification["artifact_id"]: self._repro_shape(
                    verification.get("reproducibility")
                )
                for verification in secondary_verifications
                if isinstance(verification, dict)
            },
        }

    def _bundle_metadata_shape(
        self,
        bundle_root: Path,
        *,
        metadata_path: str,
    ) -> dict[str, object]:
        payload = json.loads((bundle_root / metadata_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            self.fail("inspection bundle metadata payload must be an object")
        canonical_recipe = payload.get("canonical_recipe")
        effective_execution = payload.get("effective_execution")
        override = payload.get("override")
        archive_analysis = payload.get("archive_analysis")
        return {
            "keys": list(payload),
            "kind": payload.get("kind"),
            "profile_id": payload.get("profile_id"),
            "comparison_mode": payload.get("comparison_mode"),
            "canonical_recipe_keys": list(canonical_recipe)
            if isinstance(canonical_recipe, dict)
            else None,
            "effective_execution_keys": (
                list(effective_execution)
                if isinstance(effective_execution, dict)
                else None
            ),
            "override_keys": list(override) if isinstance(override, dict) else None,
            "override_applied": override.get("applied")
            if isinstance(override, dict)
            else None,
            "archive_analysis_keys": list(archive_analysis)
            if isinstance(archive_analysis, dict)
            else None,
        }

    def _bundle_artifact_metadata_path(
        self, bundle_root: Path, *, artifact_id: str
    ) -> Path:
        bundle_manifest = json.loads(
            (bundle_root / "inspection-bundle.json").read_text(encoding="utf-8")
        )
        for artifact in bundle_manifest["artifacts"]:
            if artifact["artifact_id"] == artifact_id:
                return bundle_root / artifact["metadata_path"]
        self.fail(f"bundle artifact metadata not found for {artifact_id}")
        raise AssertionError("unreachable")

    @staticmethod
    def _cached_command_result(completed: CompletedProcess[str]) -> CachedCommandResult:
        return CachedCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @staticmethod
    def _verify_rc_command(
        fixture: VerificationFixture,
        *,
        mode: str | None = None,
        progress: bool = False,
        report_markdown: bool = False,
        inspection_bundle: bool = False,
        repro_override_file: Path | None = None,
    ) -> list[str]:
        command = [
            "verify-rc",
            "--component-config",
            str(fixture.config_path),
            "--test-target-mode",
        ]
        if mode is not None:
            command.extend(["--mode", mode])
        if progress:
            command.extend(["--progress", "on"])
        command.extend(
            [
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
            ]
        )
        if report_markdown:
            command.extend(["--report-md", str(fixture.report_md_path)])
        if inspection_bundle:
            command.extend(["--inspection-bundle", str(fixture.inspection_bundle_path)])
        if repro_override_file is not None:
            command.extend(["--repro-override-file", str(repro_override_file)])
        command.extend([fixture.manifest_url, fixture.keys_url])
        return command

    @classmethod
    def _rebase_fixture(
        cls,
        fixture: VerificationFixture,
        *,
        old_root: Path,
        new_root: Path,
    ) -> VerificationFixture:
        old_root_str = str(old_root)
        new_root_str = str(new_root)
        old_root_uri = old_root.as_uri()
        new_root_uri = new_root.as_uri()

        def rebase_path(path: Path) -> Path:
            return new_root / path.relative_to(old_root)

        def rebase_text(value: str) -> str:
            if value.startswith(old_root_uri):
                return value.replace(old_root_uri, new_root_uri, 1)
            if value.startswith(old_root_str):
                return value.replace(old_root_str, new_root_str, 1)
            return value

        return VerificationFixture(
            config_path=rebase_path(fixture.config_path),
            keys_url=rebase_text(fixture.keys_url),
            manifest_url=rebase_text(fixture.manifest_url),
            manifest_output_path=rebase_path(fixture.manifest_output_path),
            inspection_bundle_path=rebase_path(fixture.inspection_bundle_path),
            origin_dir=rebase_path(fixture.origin_dir),
            log_path=rebase_path(fixture.log_path),
            report_json_path=rebase_path(fixture.report_json_path),
            report_md_path=rebase_path(fixture.report_md_path),
            source_commit_sha=fixture.source_commit_sha,
            source_date_epoch=fixture.source_date_epoch,
            work_dir=rebase_path(fixture.work_dir),
            extra_env={
                key: rebase_text(value) for key, value in fixture.extra_env.items()
            },
            prepend_dirs=tuple(rebase_path(path) for path in fixture.prepend_dirs),
        )

    def _build_cached_verification_family(
        self,
        sandbox_dir: Path,
        *,
        build_fixture: Callable[[Path], VerificationFixture],
        verify_command: Callable[[VerificationFixture], list[str]],
    ) -> CachedVerificationFamily:
        fixture = build_fixture(sandbox_dir)
        completed = run_cli(
            verify_command(fixture),
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )
        return CachedVerificationFamily(
            cache_root=sandbox_dir,
            fixture=fixture,
            verify_completed=self._cached_command_result(completed),
        )

    def _ensure_cached_verification_family(
        self,
        cache_name: str,
        *,
        build_family: Callable[[Path], CachedVerificationFamily],
    ) -> CachedVerificationFamily:
        cached = self._cached_verification_families.get(cache_name)
        if cached is not None:
            return cached
        cache_root = self._baseline_root / "cached-verification-families" / cache_name
        cache_root.parent.mkdir(parents=True, exist_ok=True)
        cleanup_sandbox(cache_root)
        cached = build_family(cache_root)
        self._cached_verification_families[cache_name] = cached
        return cached

    def _materialize_cached_verification_family(
        self,
        sandbox_dir: Path,
        *,
        cache_name: str,
        build_family: Callable[[Path], CachedVerificationFamily],
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        cached = self._ensure_cached_verification_family(
            cache_name,
            build_family=build_family,
        )
        cleanup_sandbox(sandbox_dir)
        copy_test_tree(cached.cache_root, sandbox_dir)
        return (
            self._rebase_fixture(
                cached.fixture, old_root=cached.cache_root, new_root=sandbox_dir
            ),
            cached.verify_completed,
        )

    def _cached_inspect_repro_result(
        self,
        cache_name: str,
        *,
        build_family: Callable[[Path], CachedVerificationFamily],
        inspect_args: tuple[str, ...] = (),
    ) -> CachedCommandResult:
        cache_key = (cache_name, inspect_args)
        cached = self._cached_inspect_results.get(cache_key)
        if cached is not None:
            return cached
        family = self._ensure_cached_verification_family(
            cache_name,
            build_family=build_family,
        )
        completed = run_cli(
            ["inspect-repro", *inspect_args, str(family.fixture.report_json_path)],
            cwd=family.fixture.origin_dir,
            env=self._fixture_cli_env(family.fixture),
        )
        cached = self._cached_command_result(completed)
        self._cached_inspect_results[cache_key] = cached
        return cached

    def _prepare_generic_file_fixture(
        self,
        sandbox_dir: Path,
        *,
        kind: str = "generic-file",
        include_reproducibility: bool = False,
        drift_reproducibility: bool = False,
        archive_reproducibility: bool = False,
        mismatched_digest: bool = False,
        include_second_shared_profile: bool = False,
        extra_verify_rc_profile_lines: tuple[str, ...] = (),
    ) -> VerificationFixture:
        return self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind=kind,
            include_generic_file_reproducibility=include_reproducibility,
            drift_generic_file_reproducibility=drift_reproducibility,
            archive_generic_file_reproducibility=archive_reproducibility,
            mismatched_secondary_digest=mismatched_digest,
            include_second_generic_file_shared_profile=include_second_shared_profile,
            extra_verify_rc_profile_lines=extra_verify_rc_profile_lines,
        )

    def _prepare_python_distribution_fixture(
        self,
        sandbox_dir: Path,
        *,
        include_reproducibility: bool = False,
        drift_reproducibility: bool = False,
        archive_reproducibility: bool = False,
        missing_index_entry: bool = False,
    ) -> VerificationFixture:
        return self._prepare_verification_fixture(
            sandbox_dir,
            include_python_distribution=True,
            include_python_distribution_reproducibility=include_reproducibility,
            drift_python_distribution_reproducibility=drift_reproducibility,
            archive_python_distribution_reproducibility=archive_reproducibility,
            missing_python_index_entry=missing_index_entry,
        )

    def _prepare_npm_package_fixture(
        self,
        sandbox_dir: Path,
        *,
        include_reproducibility: bool = False,
        drift_reproducibility: bool = False,
        archive_reproducibility: bool = False,
        drift_registry_integrity: bool = False,
    ) -> VerificationFixture:
        return self._prepare_verification_fixture(
            sandbox_dir,
            include_npm_package=True,
            include_npm_package_reproducibility=include_reproducibility,
            drift_npm_package_reproducibility=drift_reproducibility,
            archive_npm_package_reproducibility=archive_reproducibility,
            drift_npm_registry_integrity=drift_registry_integrity,
        )

    def _prepare_maven_repository_fixture(
        self,
        sandbox_dir: Path,
        *,
        include_reproducibility: bool = False,
        drift_repository: bool = False,
        drift_reproducibility: bool = False,
        include_unrelated_local_repo_files: bool = False,
        omit_sidecar_path_rules: bool = False,
    ) -> VerificationFixture:
        return self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
            drift_maven_repository=drift_repository,
            include_maven_repository_reproducibility=include_reproducibility,
            drift_maven_repository_reproducibility=drift_reproducibility,
            include_unrelated_local_maven_repository_files=include_unrelated_local_repo_files,
            omit_maven_repository_sidecar_path_rules=omit_sidecar_path_rules,
        )

    def _prepare_oci_image_fixture(
        self,
        sandbox_dir: Path,
        *,
        include_reproducibility: bool = False,
        drift_registry_image: bool = False,
        drift_reproducibility: bool = False,
        drift_reproducibility_platform: bool = False,
    ) -> VerificationFixture:
        return self._prepare_verification_fixture(
            sandbox_dir,
            include_oci_image=True,
            drift_oci_image=drift_registry_image,
            include_oci_image_reproducibility=include_reproducibility,
            drift_oci_image_reproducibility=drift_reproducibility,
            drift_oci_image_reproducibility_platform=drift_reproducibility_platform,
        )

    def _materialize_cached_generic_file_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="generic-file-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_generic_file_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    progress=True,
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_generic_file_drift_inspect_result(
        self,
        *inspect_args: str,
    ) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "generic-file-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_generic_file_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    progress=True,
                    inspection_bundle=True,
                ),
            ),
            inspect_args=tuple(inspect_args),
        )

    def _materialize_cached_generic_file_archive_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="generic-file-archive-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_generic_file_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                    archive_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_generic_file_archive_drift_inspect_result(self) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "generic-file-archive-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_generic_file_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                    archive_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_source_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="source-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    progress=True,
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_source_drift_inspect_result(self) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "source-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    progress=True,
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_source_and_generic_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="source-and-generic-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_selected_failure_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="source-generic-maven-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                    include_maven_repository=True,
                    include_maven_repository_reproducibility=True,
                    drift_maven_repository_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_mixed_failure_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="mixed-failures-all-kinds",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                    include_maven_repository=True,
                    include_maven_repository_reproducibility=True,
                    drift_maven_repository_reproducibility=True,
                    include_oci_image=True,
                    include_oci_image_reproducibility=True,
                    drift_oci_image_reproducibility_platform=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_python_distribution_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="python-distribution-archive-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: (
                    self._prepare_python_distribution_fixture(
                        family_dir,
                        include_reproducibility=True,
                        drift_reproducibility=True,
                        archive_reproducibility=True,
                    )
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_python_distribution_drift_inspect_result(self) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "python-distribution-archive-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: (
                    self._prepare_python_distribution_fixture(
                        family_dir,
                        include_reproducibility=True,
                        drift_reproducibility=True,
                        archive_reproducibility=True,
                    )
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_npm_package_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="npm-package-archive-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_npm_package_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                    archive_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_npm_package_drift_inspect_result(self) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "npm-package-archive-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_npm_package_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                    archive_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_maven_repository_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="maven-repository-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_maven_repository_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_maven_repository_drift_inspect_result(self) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "maven-repository-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_maven_repository_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_oci_image_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="oci-image-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_oci_image_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_oci_image_drift_inspect_result(self) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "oci-image-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_oci_image_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _materialize_cached_oci_image_platform_drift_family(
        self,
        sandbox_dir: Path,
    ) -> tuple[VerificationFixture, CachedCommandResult]:
        return self._materialize_cached_verification_family(
            sandbox_dir,
            cache_name="oci-image-platform-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_oci_image_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility_platform=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _cached_oci_image_platform_drift_inspect_result(self) -> CachedCommandResult:
        return self._cached_inspect_repro_result(
            "oci-image-platform-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_oci_image_fixture(
                    family_dir,
                    include_reproducibility=True,
                    drift_reproducibility_platform=True,
                ),
                verify_command=lambda fixture: self._verify_rc_command(
                    fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
        )

    def _prepare_verification_fixture(
        self,
        sandbox_dir: Path,
        *,
        include_rc_tag: bool = True,
        mismatched_source_commit_sha: bool = False,
        drift_source_artifact: bool = False,
        missing_source_artifact: bool = False,
        missing_source_checksum_sidecar: bool = False,
        missing_source_signature: bool = False,
        zero_length_source_artifact: bool = False,
        secondary_kind: str | None = None,
        mismatched_secondary_digest: bool = False,
        missing_secondary_artifact: bool = False,
        missing_secondary_checksum_sidecar: bool = False,
        missing_secondary_signature: bool = False,
        zero_length_secondary_artifact: bool = False,
        malformed_secondary_missing_artifact_id: bool = False,
        malformed_secondary_missing_kind: bool = False,
        include_maven_repository: bool = False,
        drift_maven_repository: bool = False,
        missing_maven_inventory: bool = False,
        zero_length_maven_repository_file: bool = False,
        include_maven_repository_reproducibility: bool = False,
        drift_maven_repository_reproducibility: bool = False,
        include_unrelated_local_maven_repository_files: bool = False,
        omit_maven_repository_sidecar_path_rules: bool = False,
        include_python_distribution: bool = False,
        missing_python_checksum_sidecar: bool = False,
        zero_length_python_distribution: bool = False,
        missing_python_index_entry: bool = False,
        include_python_distribution_reproducibility: bool = False,
        drift_python_distribution_reproducibility: bool = False,
        archive_python_distribution_reproducibility: bool = False,
        include_npm_package: bool = False,
        drift_npm_registry_integrity: bool = False,
        drift_npm_tarball: bool = False,
        missing_npm_tarball: bool = False,
        missing_npm_checksum_sidecar: bool = False,
        zero_length_npm_tarball: bool = False,
        include_npm_package_reproducibility: bool = False,
        drift_npm_package_reproducibility: bool = False,
        archive_npm_package_reproducibility: bool = False,
        include_oci_image: bool = False,
        drift_oci_image: bool = False,
        include_oci_image_reproducibility: bool = False,
        drift_oci_image_reproducibility: bool = False,
        drift_oci_image_reproducibility_platform: bool = False,
        include_generic_file_reproducibility: bool = False,
        drift_generic_file_reproducibility: bool = False,
        archive_generic_file_reproducibility: bool = False,
        include_second_generic_file_shared_profile: bool = False,
        extra_verify_rc_profile_lines: tuple[str, ...] = (),
    ) -> VerificationFixture:
        reproducibility = VerificationReproducibilityOptions(
            include_generic_file=include_generic_file_reproducibility,
            drift_generic_file=drift_generic_file_reproducibility,
            archive_generic_file=archive_generic_file_reproducibility,
            include_python_distribution=include_python_distribution_reproducibility,
            drift_python_distribution=drift_python_distribution_reproducibility,
            archive_python_distribution=archive_python_distribution_reproducibility,
            include_npm_package=include_npm_package_reproducibility,
            drift_npm_package=drift_npm_package_reproducibility,
            archive_npm_package=archive_npm_package_reproducibility,
            include_maven_repository=include_maven_repository_reproducibility,
            drift_maven_repository=drift_maven_repository_reproducibility,
            include_unrelated_local_maven_repository_files=(
                include_unrelated_local_maven_repository_files
            ),
            include_oci_image=include_oci_image_reproducibility,
            drift_oci_image=drift_oci_image_reproducibility,
            drift_oci_image_platform=drift_oci_image_reproducibility_platform,
        )
        origin_dir = copy_test_tree(
            self._origin_template_for(reproducibility.origin_template_key()),
            sandbox_dir / "origin",
        )
        component_id = "buildish-example"
        version = "1.2.3"
        rc_tag = "v1.2.3-rc0"
        stage_dir = (
            sandbox_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / f"{version}-rc0"
        )
        release_dir = sandbox_dir / "dist" / "release" / "incubator" / "buildish"
        release_dir.mkdir(parents=True, exist_ok=True)
        keys_path = release_dir / "KEYS"
        config_path = sandbox_dir / "component.yaml"
        work_dir = sandbox_dir / "verify-work"
        log_path = sandbox_dir / "verify.log"
        report_json_path = sandbox_dir / "verify-report.json"
        report_md_path = sandbox_dir / "verify-report.md"
        inspection_bundle_path = sandbox_dir / "verify-inspection-bundle"
        manifest_output_path = sandbox_dir / "verify-rc-command.json"
        gpg_home = sandbox_dir / "gpg-home"
        extra_env: dict[str, str] = {}
        prepend_dirs: tuple[Path, ...] = ()
        copy_test_tree(self._gpg_home_template, gpg_home)
        gpg_home.chmod(0o700)
        effective_gpg_home = _effective_home(gpg_home)
        verify_rc_line_list = reproducibility.profile_lines(
            generic_file_kind=secondary_kind,
            include_maven_sidecar_path_rules=not omit_maven_repository_sidecar_path_rules,
            extra_lines=extra_verify_rc_profile_lines,
        )
        verify_rc_lines = (
            ("verify_rc:", "  profiles:", *verify_rc_line_list)
            if verify_rc_line_list
            else ()
        )

        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=(stage_dir.parent).as_uri(),
            release_base_url=(release_dir / component_id).as_uri(),
            verify_rc_lines=verify_rc_lines,
        )

        source_commit_sha = git_rev_parse(origin_dir, "HEAD")
        git_create_annotated_tag(origin_dir, rc_tag)
        if mismatched_source_commit_sha:
            (origin_dir / "README.txt").write_text("root\nsecond\n", encoding="utf-8")
            run_quiet(["git", "-C", str(origin_dir), "add", "README.txt"], check=True)
            run_quiet(
                ["git", "-C", str(origin_dir), "commit", "-m", "second commit"],
                check=True,
            )
            source_commit_sha = git_rev_parse(origin_dir, "HEAD")
        source_date_epoch = int(
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "show",
                    "-s",
                    "--format=%ct",
                    source_commit_sha,
                ],
                check=True,
            ).stdout.strip()
        )

        keys_path.write_text(self._public_key, encoding="utf-8")

        stage_dir.mkdir(parents=True, exist_ok=True)
        source_artifact_name = f"apache-{component_id}-{version}-incubating-src.tar.gz"
        source_artifact_path = stage_dir / source_artifact_name
        create_from_git(
            origin_dir,
            source_commit_sha,
            f"apache-{component_id}-{version}-incubating-src/",
            source_artifact_path,
        )
        source_artifact_sha512 = hashlib.sha512(
            source_artifact_path.read_bytes()
        ).hexdigest()
        source_artifact_sha512_path = stage_dir / f"{source_artifact_name}.sha512"
        source_artifact_sha512_path.write_text(
            f"{source_artifact_sha512}  {source_artifact_name}\n",
            encoding="utf-8",
        )
        source_artifact_signature_path = stage_dir / f"{source_artifact_name}.asc"
        self._detached_sign(
            effective_gpg_home, source_artifact_path, source_artifact_signature_path
        )
        if zero_length_source_artifact:
            source_artifact_path.write_bytes(b"")
            source_artifact_sha512 = hashlib.sha512(b"").hexdigest()
            source_artifact_sha512_path.write_text(
                f"{source_artifact_sha512}  {source_artifact_name}\n",
                encoding="utf-8",
            )
            self._detached_sign(
                effective_gpg_home, source_artifact_path, source_artifact_signature_path
            )
        if drift_source_artifact:
            source_artifact_path.write_bytes(
                source_artifact_path.read_bytes() + b"drift\n"
            )
        if missing_source_artifact:
            source_artifact_path.unlink()
        if missing_source_checksum_sidecar:
            source_artifact_sha512_path.unlink()
        if missing_source_signature:
            source_artifact_signature_path.unlink()
        secondary_artifacts: list[dict[str, object]] = []
        if secondary_kind is not None:
            secondary_name = "buildish-example-bootstrap.zip"
            secondary_path = stage_dir / secondary_name
            if archive_generic_file_reproducibility:
                write_zip_archive(
                    secondary_path,
                    members=[
                        (
                            "bootstrap.txt",
                            b"bootstrap zip bytes\n",
                            (2026, 4, 30, 12, 0, 1),
                            0o100644,
                        )
                    ],
                )
            else:
                secondary_path.write_bytes(
                    b"" if zero_length_secondary_artifact else b"bootstrap zip bytes\n"
                )
            secondary_sha512 = hashlib.sha512(secondary_path.read_bytes()).hexdigest()
            secondary_sha512_path = stage_dir / f"{secondary_name}.sha512"
            secondary_sha512_path.write_text(
                f"{secondary_sha512}  {secondary_name}\n",
                encoding="utf-8",
            )
            secondary_signature_path = stage_dir / f"{secondary_name}.asc"
            self._detached_sign(
                effective_gpg_home, secondary_path, secondary_signature_path
            )
            manifest_secondary_sha512 = secondary_sha512
            if mismatched_secondary_digest:
                manifest_secondary_sha512 = ("0" * 127) + "1"
            secondary_artifact: dict[str, object] = {
                "artifact_id": "bootstrap-zip",
                "kind": secondary_kind,
                "filename": secondary_name,
                "uri": secondary_path.as_uri(),
                "checksums": {
                    "sha512": {
                        "value": manifest_secondary_sha512,
                        "uri": secondary_sha512_path.as_uri(),
                    }
                },
                "signatures": [
                    {
                        "type": "openpgp-detached-ascii-armored",
                        "uri": secondary_signature_path.as_uri(),
                    }
                ],
            }
            if include_generic_file_reproducibility:
                secondary_artifact["reproducibility"] = {
                    "profile_id": "bootstrap-zip",
                }
            if malformed_secondary_missing_artifact_id:
                secondary_artifact.pop("artifact_id")
            if malformed_secondary_missing_kind:
                secondary_artifact.pop("kind")
            secondary_artifacts.append(secondary_artifact)
            if include_second_generic_file_shared_profile:
                second_secondary_name = "buildish-example-bootstrap-alt.zip"
                second_secondary_path = stage_dir / second_secondary_name
                second_secondary_path.write_bytes(b"bootstrap zip bytes\n")
                second_secondary_sha512 = hashlib.sha512(
                    second_secondary_path.read_bytes()
                ).hexdigest()
                second_secondary_sha512_path = (
                    stage_dir / f"{second_secondary_name}.sha512"
                )
                second_secondary_sha512_path.write_text(
                    f"{second_secondary_sha512}  {second_secondary_name}\n",
                    encoding="utf-8",
                )
                second_secondary_signature_path = (
                    stage_dir / f"{second_secondary_name}.asc"
                )
                self._detached_sign(
                    effective_gpg_home,
                    second_secondary_path,
                    second_secondary_signature_path,
                )
                secondary_artifacts.append(
                    {
                        "artifact_id": "bootstrap-zip-alt",
                        "kind": secondary_kind,
                        "filename": second_secondary_name,
                        "uri": second_secondary_path.as_uri(),
                        "checksums": {
                            "sha512": {
                                "value": second_secondary_sha512,
                                "uri": second_secondary_sha512_path.as_uri(),
                            }
                        },
                        "signatures": [
                            {
                                "type": "openpgp-detached-ascii-armored",
                                "uri": second_secondary_signature_path.as_uri(),
                            }
                        ],
                        "reproducibility": {
                            "profile_id": "bootstrap-zip",
                        },
                    }
                )
            if missing_secondary_artifact:
                secondary_path.unlink()
            if missing_secondary_checksum_sidecar:
                secondary_sha512_path.unlink()
            if missing_secondary_signature:
                secondary_signature_path.unlink()
        if include_maven_repository:
            staging_repository_id = "orgapacheexample-1234"
            repository_root = sandbox_dir / staging_repository_id
            repository_root.mkdir(parents=True, exist_ok=True)
            artifact_relative_path = Path("org/example/app/1.0.0/app-1.0.0.jar")
            artifact_path = repository_root / artifact_relative_path
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            if include_maven_repository_reproducibility:
                if zero_length_maven_repository_file:
                    artifact_path.write_bytes(b"")
                else:
                    write_zip_archive(
                        artifact_path,
                        members=[
                            (
                                "app.txt",
                                b"jar payload\n",
                                (2026, 4, 30, 12, 0, 1),
                                0o100644,
                            )
                        ],
                    )
                pom_path = artifact_path.with_name("app-1.0.0.pom")
                pom_path.write_text("<project>stable</project>\n", encoding="utf-8")
                metadata_path = repository_root / "org/example/app/maven-metadata.xml"
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_text("<metadata/>\n", encoding="utf-8")
            else:
                artifact_path.write_bytes(
                    b"" if zero_length_maven_repository_file else b"jar-bytes\n"
                )
            artifact_sha512 = hashlib.sha512(artifact_path.read_bytes()).hexdigest()
            artifact_sha512_path = artifact_path.with_name(
                f"{artifact_path.name}.sha512"
            )
            artifact_sha512_path.write_text(
                f"{artifact_sha512}  {artifact_path.name}\n",
                encoding="utf-8",
            )
            artifact_signature_path = artifact_path.with_name(
                f"{artifact_path.name}.asc"
            )
            self._detached_sign(
                effective_gpg_home, artifact_path, artifact_signature_path
            )
            repository_bundle_dir = sandbox_dir / "maven-bundle"
            repository_bundle_dir.mkdir(parents=True, exist_ok=True)
            registration = build_maven_repository_registration(
                Namespace(
                    artifact_id="maven-staging-main",
                    staging_repository_id=staging_repository_id,
                    base_url=f"{repository_root.as_uri()}/",
                    inventory_workers=None,
                    progress="off",
                    role=None,
                    git_commit_sha=None,
                    artifact_origin=None,
                ),
                repository_bundle_dir,
            )
            maven_artifact = registration.secondary_artifact.model_dump(
                mode="json", exclude_none=True
            )
            inventory = dict(maven_artifact["inventory"])
            inventory_filename = inventory["filename"]
            inventory["uri"] = (repository_bundle_dir / inventory_filename).as_uri()
            maven_artifact["inventory"] = inventory
            if include_maven_repository_reproducibility:
                maven_artifact["reproducibility"] = {
                    "profile_id": "maven-staging",
                }
            secondary_artifacts.append(maven_artifact)
            if missing_maven_inventory:
                (repository_bundle_dir / inventory_filename).unlink()
            if drift_maven_repository:
                artifact_path.write_bytes(b"jar-drift\n")
        if include_python_distribution:
            distribution_dir = sandbox_dir / "pypi-files"
            distribution_dir.mkdir(parents=True, exist_ok=True)
            distribution_path = distribution_dir / "example-1.2.3-py3-none-any.whl"
            if archive_python_distribution_reproducibility:
                write_zip_archive(
                    distribution_path,
                    members=[
                        (
                            "example/__init__.py",
                            b"wheel payload\n",
                            (2026, 4, 30, 12, 0, 1),
                            0o100644,
                        )
                    ],
                )
            else:
                distribution_path.write_bytes(
                    b"" if zero_length_python_distribution else b"wheel payload\n"
                )
            distribution_bundle_dir = sandbox_dir / "python-bundle"
            distribution_bundle_dir.mkdir(parents=True, exist_ok=True)
            registration = build_python_distribution_registration(
                Namespace(
                    artifact_id="pypi-wheel",
                    file=str(distribution_path),
                    filename=None,
                    uri=distribution_path.as_uri(),
                    index_url=(sandbox_dir / "simple").as_uri() + "/",
                    project_name="example",
                    package_version="1.2.3",
                    sha256=None,
                    sha256_uri=None,
                    attestation_repository=None,
                    role=None,
                    git_commit_sha=None,
                    artifact_origin=None,
                ),
                distribution_bundle_dir,
            )
            python_artifact = registration.secondary_artifact.model_dump(
                mode="json",
                exclude_none=True,
            )
            if missing_python_checksum_sidecar:
                python_sidecar_path = (
                    distribution_dir / f"{distribution_path.name}.sha256"
                )
                python_sidecar_path.write_text(
                    f"{python_artifact['checksums']['sha256']['value']}  {distribution_path.name}\n",
                    encoding="utf-8",
                )
                python_artifact["checksums"]["sha256"]["uri"] = (
                    python_sidecar_path.as_uri()
                )
                python_sidecar_path.unlink()
            simple_project_dir = sandbox_dir / "simple" / "example"
            simple_project_dir.mkdir(parents=True, exist_ok=True)
            simple_index_path = simple_project_dir / "index.json"
            simple_index_payload = {
                "files": []
                if missing_python_index_entry
                else [
                    {
                        "filename": python_artifact["filename"],
                        "url": python_artifact["uri"],
                        "hashes": {
                            "sha256": python_artifact["checksums"]["sha256"]["value"],
                        },
                    }
                ]
            }
            simple_index_path.write_text(
                json.dumps(simple_index_payload, indent=2) + "\n",
                encoding="utf-8",
            )
            if include_python_distribution_reproducibility:
                python_artifact["reproducibility"] = {
                    "profile_id": "pypi-wheel",
                }
            secondary_artifacts.append(python_artifact)
        if include_npm_package:
            artifact_file_path = sandbox_dir / "npm-dist" / "buildish-example-1.2.3.tgz"
            artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
            if archive_npm_package_reproducibility:
                write_tgz_archive(
                    artifact_file_path,
                    members=[
                        (
                            "package/package.json",
                            b"npm package payload\n",
                            1714435201,
                            0o644,
                        )
                    ],
                )
            else:
                artifact_file_path.write_bytes(
                    b"" if zero_length_npm_tarball else b"npm package payload\n"
                )
            artifact_bytes = artifact_file_path.read_bytes()
            expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
            expected_integrity = "sha512-" + base64.b64encode(
                hashlib.sha512(artifact_bytes).digest()
            ).decode("ascii")
            live_integrity = (
                "sha512-" + base64.b64encode(bytes(64)).decode("ascii")
                if drift_npm_registry_integrity
                else expected_integrity
            )
            registry_root = sandbox_dir / "npm-registry"
            metadata_dir = registry_root / "@buildish-tooling" / "buildish-example"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            (metadata_dir / "index.json").write_text(
                json.dumps(
                    {
                        "name": "@buildish-tooling/buildish-example",
                        "versions": {
                            "1.2.3": {
                                "name": "@buildish-tooling/buildish-example",
                                "version": "1.2.3",
                                "dist": {
                                    "tarball": artifact_file_path.as_uri(),
                                    "integrity": live_integrity,
                                    "signatures": [],
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            npm_artifact: dict[str, object] = {
                "artifact_id": "npm-package-main",
                "kind": "npm-package",
                "filename": artifact_file_path.name,
                "uri": artifact_file_path.as_uri(),
                "registry_url": registry_root.as_uri() + "/",
                "package_name": "@buildish-tooling/buildish-example",
                "version": "1.2.3",
                "integrity": expected_integrity,
                "checksums": {
                    "sha512": {
                        "value": expected_sha512,
                    }
                },
            }
            if missing_npm_checksum_sidecar:
                npm_sidecar_path = (
                    artifact_file_path.parent / f"{artifact_file_path.name}.sha512"
                )
                npm_sidecar_path.write_text(
                    f"{expected_sha512}  {artifact_file_path.name}\n",
                    encoding="utf-8",
                )
                npm_checksums = cast(dict[str, object], npm_artifact["checksums"])
                npm_sha512_payload = cast(dict[str, str], npm_checksums["sha512"])
                npm_sha512_payload["uri"] = npm_sidecar_path.as_uri()
                npm_sidecar_path.unlink()
            if include_npm_package_reproducibility:
                npm_artifact["reproducibility"] = {
                    "profile_id": "npm-package-main",
                }
            secondary_artifacts.append(npm_artifact)
            if drift_npm_tarball:
                artifact_file_path.write_bytes(artifact_bytes + b"registry drift\n")
            if missing_npm_tarball:
                artifact_file_path.unlink()
        if include_oci_image:
            docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
            extra_env["FAKE_DOCKER_STATE_DIR"] = str(docker_state_dir)
            prepend_dirs = (docker_path.parent,)
            top_level_digest = "sha256:" + ("d4" * 32)
            amd64_digest = "sha256:" + ("a1" * 32)
            arm64_digest = "sha256:" + ("b2" * 32)
            live_arm64_digest = (
                "sha256:" + ("c3" * 32) if drift_oci_image else arm64_digest
            )
            (docker_state_dir / "imagetools-inspect-response.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "mediaType": "application/vnd.oci.image.index.v1+json",
                        "digest": top_level_digest,
                        "manifests": [
                            {
                                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                "digest": amd64_digest,
                                "platform": {"architecture": "amd64", "os": "linux"},
                            },
                            {
                                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                "digest": live_arm64_digest,
                                "platform": {"architecture": "arm64", "os": "linux"},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            oci_bundle_dir = sandbox_dir / "oci-bundle"
            oci_bundle_dir.mkdir(parents=True, exist_ok=True)
            registration = build_oci_image_registration(
                Namespace(
                    artifact_id="ghcr-main-image",
                    image_ref=None,
                    registry="ghcr.io",
                    repository="buildish-tooling/buildish-example",
                    digest=top_level_digest,
                    platform_digests=[
                        f"linux/amd64={amd64_digest}",
                        f"linux/arm64={arm64_digest}",
                    ],
                    uri=None,
                    role=None,
                    git_commit_sha=None,
                    artifact_origin=None,
                ),
                oci_bundle_dir,
            )
            oci_artifact = registration.secondary_artifact.model_dump(
                mode="json", exclude_none=True
            )
            if include_oci_image_reproducibility:
                oci_artifact["reproducibility"] = {
                    "profile_id": "oci-main-image",
                }
            secondary_artifacts.append(oci_artifact)

        manifest_payload: dict[str, object] = {
            "schema_version": "1",
            "manifest_type": "rc-vote",
            "component_id": component_id,
            "version": version,
            "release_line": "1.2.x",
            "release_branch": "release/1.2.x",
            "source_repository_url": origin_dir.as_uri(),
            "source_commit_sha": source_commit_sha,
            "source_date_epoch": source_date_epoch,
            "final_tag": f"v{version}",
            "final_tag_mode": "rc-source-commit",
            "provenance": {"created_at": "2026-04-29T12:00:00Z", "tooling": {}},
            "trust_roots": {
                "asf_keys": {
                    "uri": keys_path.as_uri(),
                    "known_length_bytes": keys_path.stat().st_size,
                    "known_prefix_sha512": hashlib.sha512(
                        keys_path.read_bytes()
                    ).hexdigest(),
                }
            },
            "draft_github_release": {
                "repository": "buildish-tooling/buildish-example",
                "tag": rc_tag,
                "url": f"https://github.com/buildish-tooling/buildish-example/releases/tag/{rc_tag}",
            },
            "vote_materials": {
                "source_artifacts": [
                    {
                        "role": "asf-source-release",
                        "filename": source_artifact_name,
                        "uri": source_artifact_path.as_uri(),
                        "artifact_origin": "source-commit",
                        "git_commit_sha": source_commit_sha,
                        "checksums": {
                            "sha512": {
                                "value": source_artifact_sha512,
                                "uri": source_artifact_sha512_path.as_uri(),
                            }
                        },
                        "signatures": [
                            {
                                "type": "openpgp-detached-ascii-armored",
                                "uri": source_artifact_signature_path.as_uri(),
                            }
                        ],
                    }
                ],
                "secondary_artifacts": secondary_artifacts,
            },
            "verification": {
                "staging_svn_url": f"{stage_dir.as_uri()}/",
            },
        }
        if include_rc_tag:
            manifest_payload["rc_tag"] = rc_tag

        manifest_path = stage_dir / "rc-vote-manifest.json"
        manifest_text = json.dumps(manifest_payload, indent=2) + "\n"
        manifest_path.write_text(manifest_text, encoding="utf-8")
        manifest_sha512 = hashlib.sha512(manifest_text.encode("utf-8")).hexdigest()
        manifest_sha512_path = stage_dir / "rc-vote-manifest.json.sha512"
        manifest_sha512_path.write_text(
            f"{manifest_sha512}  rc-vote-manifest.json\n",
            encoding="utf-8",
        )
        manifest_signature_path = stage_dir / "rc-vote-manifest.json.asc"
        self._detached_sign(effective_gpg_home, manifest_path, manifest_signature_path)

        return VerificationFixture(
            config_path=config_path,
            keys_url=keys_path.as_uri(),
            manifest_url=manifest_path.as_uri(),
            manifest_output_path=manifest_output_path,
            inspection_bundle_path=inspection_bundle_path,
            origin_dir=origin_dir,
            log_path=log_path,
            report_json_path=report_json_path,
            report_md_path=report_md_path,
            source_commit_sha=source_commit_sha,
            source_date_epoch=source_date_epoch,
            work_dir=work_dir,
            extra_env=extra_env,
            prepend_dirs=prepend_dirs,
        )

    @staticmethod
    def _detached_sign(gpg_home: Path, input_path: Path, output_path: Path) -> None:
        fingerprint = secret_key_fingerprint(gpg_home)
        run_quiet(
            [
                "gpg",
                "--batch",
                "--yes",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--local-user",
                fingerprint,
                "--armor",
                "--detach-sign",
                "--output",
                str(output_path),
                str(input_path),
            ],
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        )

    @staticmethod
    def _fixture_cli_env(
        fixture: VerificationFixture,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        merged_env = dict(fixture.extra_env)
        if extra_env is not None:
            merged_env.update(extra_env)
        return cli_env(
            fixture.manifest_output_path,
            extra_env=merged_env,
            prepend_dirs=fixture.prepend_dirs,
        )
