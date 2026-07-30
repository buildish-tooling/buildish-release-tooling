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

"""Policy-aware download sessions for bounded URI reads and downloads."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self
from urllib.parse import urlparse

from urllib3 import Timeout

from buildish_release_tooling.shared._downloader import (
    DEFAULT_DOWNLOADER_TIMEOUT,
    DownloadedResource,
    RedirectValidator,
    _ResourceDownloader,
)


class DownloadTransport(Protocol):
    """Transport interface owned by one download session."""

    def close(self) -> None:
        """Release transport resources."""

    def download_to_path(
        self,
        uri: str,
        destination: Path,
        *,
        max_bytes: int,
        algorithms: Iterable[str] = ("sha512",),
        max_redirects: int = 0,
        redirect_validator: RedirectValidator | None = None,
    ) -> DownloadedResource:
        """Download one resource to disk."""

    def hash_uri(
        self,
        uri: str,
        *,
        algorithm: str = "sha512",
        max_redirects: int = 0,
        redirect_validator: RedirectValidator | None = None,
    ) -> str:
        """Hash one resource."""

    def read_bytes(
        self,
        uri: str,
        *,
        max_bytes: int,
        max_redirects: int = 0,
        redirect_validator: RedirectValidator | None = None,
    ) -> bytes:
        """Read one resource as bounded bytes."""

    def read_text(
        self,
        uri: str,
        *,
        max_bytes: int,
        encoding: str = "utf-8",
        errors: str = "strict",
        max_redirects: int = 0,
        redirect_validator: RedirectValidator | None = None,
    ) -> str:
        """Read one resource as bounded text."""


@dataclass(frozen=True, slots=True)
class DownloadPolicy:
    """Immutable URI policy for one download session."""

    allowed_schemes: frozenset[str]
    max_redirects: int = 5
    allow_https_to_http_redirect: bool = False


@dataclass
class DownloadSession:
    """Policy-aware resource download session with explicit lifecycle ownership."""

    policy: DownloadPolicy
    transport: DownloadTransport
    _owns_transport: bool = True

    @classmethod
    def production(
        cls,
        *,
        max_connections: int = 16,
        timeout: Timeout | float = DEFAULT_DOWNLOADER_TIMEOUT,
    ) -> Self:
        """Create a session for production release downloads."""

        return cls(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https"})),
            transport=_ResourceDownloader.create(max_connections=max_connections, timeout=timeout),
        )

    @classmethod
    def non_production(
        cls,
        *,
        max_connections: int = 16,
        timeout: Timeout | float = DEFAULT_DOWNLOADER_TIMEOUT,
    ) -> Self:
        """Create a session for local/test release targets."""

        return cls(
            policy=DownloadPolicy(allowed_schemes=frozenset({"https", "http", "file"})),
            transport=_ResourceDownloader.create(max_connections=max_connections, timeout=timeout),
        )

    @classmethod
    def harness(
        cls,
        *,
        max_connections: int = 16,
        timeout: Timeout | float = DEFAULT_DOWNLOADER_TIMEOUT,
    ) -> Self:
        """Create a session for harness-owned test infrastructure."""

        return cls.non_production(max_connections=max_connections, timeout=timeout)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()

    def close(self) -> None:
        """Release resources owned by this session."""

        if self._owns_transport:
            self.transport.close()

    def download_to_path(
        self,
        uri: str,
        destination: Path,
        *,
        max_bytes: int,
        algorithms: Iterable[str] = ("sha512",),
    ) -> DownloadedResource:
        """Download one URI to disk after applying this session's policy."""

        self._validate_uri(uri)
        return self.transport.download_to_path(
            uri,
            destination,
            max_bytes=max_bytes,
            algorithms=algorithms,
            max_redirects=self.policy.max_redirects,
            redirect_validator=self._validate_redirect,
        )

    def hash_uri(self, uri: str, *, algorithm: str = "sha512") -> str:
        """Hash one URI after applying this session's policy."""

        self._validate_uri(uri)
        return self.transport.hash_uri(
            uri,
            algorithm=algorithm,
            max_redirects=self.policy.max_redirects,
            redirect_validator=self._validate_redirect,
        )

    def read_bytes(self, uri: str, *, max_bytes: int) -> bytes:
        """Read one URI as bounded bytes after applying this session's policy."""

        self._validate_uri(uri)
        return self.transport.read_bytes(
            uri,
            max_bytes=max_bytes,
            max_redirects=self.policy.max_redirects,
            redirect_validator=self._validate_redirect,
        )

    def read_text(
        self,
        uri: str,
        *,
        max_bytes: int,
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> str:
        """Read one URI as bounded text after applying this session's policy."""

        self._validate_uri(uri)
        return self.transport.read_text(
            uri,
            max_bytes=max_bytes,
            encoding=encoding,
            errors=errors,
            max_redirects=self.policy.max_redirects,
            redirect_validator=self._validate_redirect,
        )

    def _validate_redirect(self, source_uri: str, target_uri: str) -> None:
        self._validate_uri(target_uri)
        source = urlparse(source_uri)
        target = urlparse(target_uri)
        if (
            source.scheme == "https"
            and target.scheme == "http"
            and not self.policy.allow_https_to_http_redirect
        ):
            raise ValueError(f"HTTPS download must not redirect to HTTP: {source_uri} -> {target_uri}")

    def _validate_uri(self, uri: str) -> None:
        parsed = urlparse(uri)
        if parsed.scheme not in self.policy.allowed_schemes:
            allowed = ", ".join(sorted(self.policy.allowed_schemes))
            raise ValueError(f"URI scheme must be one of {allowed}: {uri}")
        if parsed.scheme == "file" and parsed.netloc not in {"", "localhost"}:
            raise ValueError(f"file URI must not include a non-local authority: {uri}")
