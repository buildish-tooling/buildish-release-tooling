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

"""Pooled, bounded URI downloader helpers."""

from __future__ import annotations

import contextlib
import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Self, cast
from urllib.error import HTTPError
from urllib.parse import unquote, urlparse

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


@dataclass(frozen=True)
class DownloadedResource:
    """Metadata for one downloaded URI."""

    uri: str
    path: Path
    size_bytes: int
    hashes: dict[str, str]


@dataclass
class ResourceDownloader:
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
    ) -> DownloadedResource:
        """Download one URI to disk while enforcing a byte limit and hashing."""

        stream: BinaryReadable
        with self._open_uri(uri) as stream:
            copied = copy_stream_to_path(
                stream,
                destination,
                max_bytes=max_bytes,
                algorithms=algorithms,
            )
        return _downloaded_resource(uri, copied)

    def hash_uri(
        self,
        uri: str,
        *,
        algorithm: str = "sha512",
    ) -> str:
        """Hash one supported URI without buffering it all in memory."""

        stream: BinaryReadable
        with self._open_uri(uri) as stream:
            return hash_stream(stream, algorithm=algorithm)

    def read_bytes(
        self,
        uri: str,
        *,
        max_bytes: int,
    ) -> bytes:
        """Read one URI into memory with an explicit maximum size."""

        stream: BinaryReadable
        with self._open_uri(uri) as stream:
            return read_bytes_bounded(stream, max_bytes=max_bytes)

    def read_text(
        self,
        uri: str,
        *,
        max_bytes: int,
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> str:
        """Read one URI as bounded text."""

        stream: BinaryReadable
        with self._open_uri(uri) as stream:
            return read_text_bounded(
                stream,
                max_bytes=max_bytes,
                encoding=encoding,
                errors=errors,
            )

    @contextlib.contextmanager
    def _open_uri(self, uri: str) -> Iterator[BinaryReadable]:
        parsed = urlparse(uri)
        if parsed.scheme == "file":
            with Path(unquote(parsed.path)).open("rb") as handle:
                yield handle
            return
        if parsed.scheme in {"http", "https"}:
            response = self.pool_manager.request(
                "GET",
                uri,
                preload_content=False,
                timeout=self.timeout,
            )
            try:
                if response.status < 200 or response.status >= 300:
                    payload = response.read(MAX_HTTP_ERROR_BODY_BYTES)
                    raise HTTPError(
                        uri,
                        response.status,
                        "unexpected HTTP response",
                        _http_error_headers(response.headers),
                        io.BytesIO(payload),
                    )
                yield cast(BinaryReadable, response)
            finally:
                response.release_conn()
            return
        raise ValueError(f"unsupported URI scheme: {uri}")


def _downloaded_resource(uri: str, copied: CopiedResource) -> DownloadedResource:
    return DownloadedResource(
        uri=uri,
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
