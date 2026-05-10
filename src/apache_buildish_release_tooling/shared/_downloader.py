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

"""Private pooled, bounded URI transport helpers.

Use :mod:`apache_buildish_release_tooling.shared.downloader` from production code.
This module contains transport plumbing behind the policy-enforcing download session.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Self, cast
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlparse

import urllib3
from urllib3 import Timeout

from apache_buildish_release_tooling.shared.io import (
    CopiedResource,
    BinaryReadable,
    copy_stream_to_path,
    hash_stream,
    read_bytes_bounded,
    read_text_bounded,
)

DEFAULT_DOWNLOADER_TIMEOUT = Timeout(connect=10.0, read=60.0)
MAX_HTTP_ERROR_BODY_BYTES = 1024 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

RedirectValidator = Callable[[str, str], None]


@dataclass(frozen=True)
class DownloadedResource:
    """Metadata for one downloaded URI."""

    uri: str
    final_uri: str
    path: Path
    size_bytes: int
    hashes: dict[str, str]


@dataclass
class _ResourceDownloader:
    """Download and read URI resources with pooled HTTP connections and limits."""

    pool_manager: urllib3.PoolManager
    timeout: Timeout | float = DEFAULT_DOWNLOADER_TIMEOUT

    @classmethod
    def create(
        cls,
        *,
        max_connections: int = 16,
        timeout: Timeout | float = DEFAULT_DOWNLOADER_TIMEOUT,
    ) -> Self:
        return cls(
            pool_manager=urllib3.PoolManager(
                maxsize=max_connections,
                block=True,
                timeout=timeout,
            ),
            timeout=timeout,
        )

    def close(self) -> None:
        self.pool_manager.clear()

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
        """Download one URI to disk while enforcing a byte limit and hashing."""

        stream: BinaryReadable
        with self._open_uri(
            uri,
            max_redirects=max_redirects,
            redirect_validator=redirect_validator,
        ) as (stream, final_uri):
            copied = copy_stream_to_path(
                stream,
                destination,
                max_bytes=max_bytes,
                algorithms=algorithms,
            )
        return _downloaded_resource(uri, final_uri, copied)

    def hash_uri(
        self,
        uri: str,
        *,
        algorithm: str = "sha512",
        max_redirects: int = 0,
        redirect_validator: RedirectValidator | None = None,
    ) -> str:
        """Hash one supported URI without buffering it all in memory."""

        stream: BinaryReadable
        with self._open_uri(
            uri,
            max_redirects=max_redirects,
            redirect_validator=redirect_validator,
        ) as (stream, _final_uri):
            return hash_stream(stream, algorithm=algorithm)

    def read_bytes(
        self,
        uri: str,
        *,
        max_bytes: int,
        max_redirects: int = 0,
        redirect_validator: RedirectValidator | None = None,
    ) -> bytes:
        """Read one URI into memory with an explicit maximum size."""

        stream: BinaryReadable
        with self._open_uri(
            uri,
            max_redirects=max_redirects,
            redirect_validator=redirect_validator,
        ) as (stream, _final_uri):
            return read_bytes_bounded(stream, max_bytes=max_bytes)

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
        """Read one URI as bounded text."""

        stream: BinaryReadable
        with self._open_uri(
            uri,
            max_redirects=max_redirects,
            redirect_validator=redirect_validator,
        ) as (stream, _final_uri):
            return read_text_bounded(
                stream,
                max_bytes=max_bytes,
                encoding=encoding,
                errors=errors,
            )

    @contextlib.contextmanager
    def _open_uri(
        self,
        uri: str,
        *,
        max_redirects: int,
        redirect_validator: RedirectValidator | None,
    ) -> Iterator[tuple[BinaryReadable, str]]:
        current_uri = uri
        redirects_followed = 0
        while True:
            parsed = urlparse(current_uri)
            if parsed.scheme == "file":
                if parsed.netloc not in {"", "localhost"}:
                    raise ValueError(f"file URI must not include a non-local authority: {current_uri}")
                with Path(unquote(parsed.path)).open("rb") as handle:
                    yield handle, current_uri
                return
            if parsed.scheme not in {"http", "https"}:
                raise ValueError(f"unsupported URI scheme: {current_uri}")
            response = self.pool_manager.request(
                "GET",
                current_uri,
                preload_content=False,
                timeout=self.timeout,
                redirect=False,
            )
            try:
                if response.status in _REDIRECT_STATUSES:
                    location = response.headers.get("location") if hasattr(response.headers, "get") else None
                    if not location:
                        raise HTTPError(
                            current_uri,
                            response.status,
                            "redirect response missing Location header",
                            _http_error_headers(response.headers),
                            io.BytesIO(b""),
                        )
                    if redirects_followed >= max_redirects:
                        raise HTTPError(
                            current_uri,
                            response.status,
                            "redirect limit exceeded",
                            _http_error_headers(response.headers),
                            io.BytesIO(b""),
                        )
                    next_uri = urljoin(current_uri, str(location))
                    if redirect_validator is not None:
                        redirect_validator(current_uri, next_uri)
                    redirects_followed += 1
                    current_uri = next_uri
                    continue
                if response.status < 200 or response.status >= 300:
                    payload = response.read(MAX_HTTP_ERROR_BODY_BYTES)
                    raise HTTPError(
                        current_uri,
                        response.status,
                        "unexpected HTTP response",
                        _http_error_headers(response.headers),
                        io.BytesIO(payload),
                    )
                yield cast(BinaryReadable, response), current_uri
            finally:
                response.release_conn()
            return


def _downloaded_resource(uri: str, final_uri: str, copied: CopiedResource) -> DownloadedResource:
    return DownloadedResource(
        uri=uri,
        final_uri=final_uri,
        path=copied.path,
        size_bytes=copied.size_bytes,
        hashes=dict(copied.hashes),
    )


def _http_error_headers(headers: object) -> Message[str, str]:
    message: Message[str, str] = Message()
    items = getattr(headers, "items", None)
    if callable(items):
        for name, value in items():
            message[str(name)] = str(value)
    return message
