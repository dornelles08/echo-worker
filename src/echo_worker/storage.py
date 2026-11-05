from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

import boto3
import httpx
from botocore.config import Config

from echo_worker.logging import get_logger
from echo_worker.models import MediaRecord

logger = get_logger(__name__)


class StorageError(RuntimeError):
    """The media file could not be retrieved."""


def _suffix(filename: str) -> str:
    suffix = Path(filename).suffix

    return suffix if suffix else ".bin"


class Storage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
        use_ssl: bool,
        timeout_seconds: float = 300,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            use_ssl=use_ssl,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )
        self._timeout = timeout_seconds

    def download(self, media: MediaRecord, destination: Path) -> Path:
        """Downloads the media file to ``destination`` and returns its path.

        Prefers the stable ``storage_key`` over the presigned URL, which may
        have expired by the time the job runs.
        """
        if media.storage_key:
            return self._download_from_bucket(media.storage_key, destination)

        if media.url.startswith("http://") or media.url.startswith("https://"):
            return self._download_from_url(media.url, destination)

        local_path = Path(media.url)

        if local_path.exists():
            shutil.copyfile(local_path, destination)
            return destination

        raise StorageError(f"No storage key and no reachable URL for media {media.id}")

    def _download_from_bucket(self, key: str, destination: Path) -> Path:
        logger.info("Downloading s3://%s/%s", self._bucket, key)

        try:
            self._client.download_file(self._bucket, key, str(destination))
        except Exception as error:
            raise StorageError(f"Failed to download {key} from bucket") from error

        return destination

    def _download_from_url(self, url: str, destination: Path) -> Path:
        logger.info("Downloading %s", urlparse(url).hostname)

        try:
            with httpx.stream("GET", url, timeout=self._timeout, follow_redirects=True) as response:
                response.raise_for_status()

                with destination.open("wb") as file:
                    for chunk in response.iter_bytes():
                        file.write(chunk)
        except httpx.HTTPError as error:
            raise StorageError("Failed to download media from URL") from error

        return destination


def build_destination(directory: Path, media: MediaRecord) -> Path:
    return directory / f"media-{media.id}{_suffix(media.filename)}"
