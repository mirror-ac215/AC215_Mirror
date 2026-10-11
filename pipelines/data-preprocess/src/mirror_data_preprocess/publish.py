from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


class Blob(Protocol):
    def upload_from_filename(self, filename: str) -> None: ...


class Bucket(Protocol):
    def blob(self, name: str) -> Blob: ...


class StorageClient(Protocol):
    def bucket(self, name: str) -> Bucket: ...


def _parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    parsed = urlparse(gcs_uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError("gcs_uri must be a gs://bucket/prefix URI")
    return parsed.netloc, parsed.path.lstrip("/").rstrip("/")


def publish_directory(
    output_dir: Path, gcs_uri: str, client: StorageClient, max_workers: int = 32
) -> int:
    """Upload files with bounded in-flight work and preserved relative paths.

    A failure stops scheduling new uploads. Objects already uploaded remain at the
    target prefix, so callers must publish only validated, versioned output paths.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise FileNotFoundError(output_dir)
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")
    bucket_name, prefix = _parse_gcs_uri(gcs_uri)
    bucket = client.bucket(bucket_name)
    files = iter(sorted(path for path in output_dir.rglob("*") if path.is_file()))

    def upload(file_path: Path) -> None:
        relative_path = file_path.relative_to(output_dir).as_posix()
        object_name = "/".join(part for part in (prefix, relative_path) if part)
        bucket.blob(object_name).upload_from_filename(str(file_path))

    submitted = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending: set[Future[None]] = set()
        for _ in range(max_workers):
            try:
                pending.add(executor.submit(upload, next(files)))
                submitted += 1
            except StopIteration:
                break

        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                future.result()
                try:
                    pending.add(executor.submit(upload, next(files)))
                    submitted += 1
                except StopIteration:
                    pass
    return submitted
