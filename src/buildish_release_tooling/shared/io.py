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

"""Shared bounded stream and local-file I/O helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

DEFAULT_STREAM_CHUNK_BYTES = 1024 * 1024


class BinaryReadable(Protocol):
    """Minimal binary stream interface consumed by shared I/O helpers."""

    def read(self, size: int = -1) -> bytes:
        """Read bytes from one stream."""


class ByteLimitExceededError(ValueError):
    """Raised when a bounded read or copy exceeds the configured byte limit."""


@dataclass(frozen=True)
class CopiedResource:
    """Metadata produced while copying one stream to disk."""

    path: Path
    size_bytes: int
    hashes: Mapping[str, str]


def normalized_hash_algorithm(algorithm: str) -> str:
    """Return one lowercase hashlib algorithm name after validating support."""

    normalized = algorithm.lower()
    if normalized not in hashlib.algorithms_available:
        raise ValueError(f"unsupported hash algorithm: {algorithm}")
    return normalized


def hash_stream(
    stream: BinaryReadable,
    *,
    algorithm: str = "sha512",
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> str:
    """Compute one digest while reading a binary stream in chunks."""

    digest = hashlib.new(normalized_hash_algorithm(algorithm))
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


def hash_stream_bounded(
    stream: BinaryReadable,
    *,
    max_bytes: int,
    algorithm: str = "sha512",
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> str:
    """Compute one digest while failing if the stream exceeds the byte limit."""

    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    digest = hashlib.new(normalized_hash_algorithm(algorithm))
    bytes_read = 0
    while chunk := stream.read(min(chunk_size, max_bytes + 1 - bytes_read)):
        bytes_read += len(chunk)
        if bytes_read > max_bytes:
            raise ByteLimitExceededError(f"hash input exceeded {max_bytes} bytes")
        digest.update(chunk)
    return digest.hexdigest()


def hash_file(
    path: Path,
    *,
    algorithm: str = "sha512",
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> str:
    """Compute one digest for a local file without loading it all."""

    with path.open("rb") as handle:
        return hash_stream(handle, algorithm=algorithm, chunk_size=chunk_size)


def copy_stream_to_path(
    source: BinaryReadable,
    destination: Path,
    *,
    algorithms: Iterable[str] = ("sha512",),
    max_bytes: int | None = None,
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> CopiedResource:
    """Copy a binary stream to a path while enforcing limits and hashing."""

    normalized_algorithms = tuple(dict.fromkeys(normalized_hash_algorithm(algorithm) for algorithm in algorithms))
    digests = {algorithm: hashlib.new(algorithm) for algorithm in normalized_algorithms}
    destination.parent.mkdir(parents=True, exist_ok=True)
    bytes_copied = 0
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            while chunk := source.read(chunk_size):
                bytes_copied += len(chunk)
                if max_bytes is not None and bytes_copied > max_bytes:
                    raise ByteLimitExceededError(
                        f"copy exceeded {max_bytes} bytes while writing {destination.as_posix()}"
                    )
                temporary_file.write(chunk)
                for digest in digests.values():
                    digest.update(chunk)
        temporary_path.replace(destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return CopiedResource(
        path=destination,
        size_bytes=bytes_copied,
        hashes={algorithm: digest.hexdigest() for algorithm, digest in digests.items()},
    )


def read_bytes_bounded(
    stream: BinaryReadable,
    *,
    max_bytes: int,
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> bytes:
    """Read one binary stream into memory, failing if the limit is exceeded."""

    chunks: list[bytes] = []
    bytes_read = 0
    while chunk := stream.read(min(chunk_size, max_bytes + 1 - bytes_read)):
        bytes_read += len(chunk)
        if bytes_read > max_bytes:
            raise ByteLimitExceededError(f"read exceeded {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def read_text_bounded(
    stream: BinaryReadable,
    *,
    max_bytes: int,
    encoding: str = "utf-8",
    errors: str = "strict",
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> str:
    """Read bounded bytes and decode them as text."""

    return read_bytes_bounded(stream, max_bytes=max_bytes, chunk_size=chunk_size).decode(
        encoding,
        errors=errors,
    )


def read_bytes_file_bounded(path: Path, *, max_bytes: int) -> bytes:
    """Read one local file into memory, failing if the limit is exceeded."""

    with path.open("rb") as handle:
        return read_bytes_bounded(handle, max_bytes=max_bytes)


def read_text_file_bounded(
    path: Path,
    *,
    max_bytes: int,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> str:
    """Read one local file as text, failing if the byte limit is exceeded."""

    with path.open("rb") as handle:
        return read_text_bounded(
            handle,
            max_bytes=max_bytes,
            encoding=encoding,
            errors=errors,
        )


def files_equal(
    left: Path,
    right: Path,
    *,
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> bool:
    """Return whether two local files have identical bytes."""

    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            left_chunk = left_file.read(chunk_size)
            right_chunk = right_file.read(chunk_size)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def first_differing_byte(
    left: Path,
    right: Path,
    *,
    chunk_size: int = DEFAULT_STREAM_CHUNK_BYTES,
) -> int | None:
    """Return the first differing byte offset for two files, or None if equal."""

    offset = 0
    with left.open("rb") as left_file, right.open("rb") as right_file:
        while True:
            left_chunk = left_file.read(chunk_size)
            right_chunk = right_file.read(chunk_size)
            if left_chunk != right_chunk:
                return offset + _first_chunk_difference(left_chunk, right_chunk)
            if not left_chunk:
                return None
            offset += len(left_chunk)


def _first_chunk_difference(left: bytes, right: bytes) -> int:
    for index, (left_byte, right_byte) in enumerate(zip(left, right, strict=False)):
        if left_byte != right_byte:
            return index
    return min(len(left), len(right))
