import asyncio
import hashlib
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from urllib.parse import quote

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class StoredObjectInfo:
    size: int
    content_type: str | None


class ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.minio_bucket
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._public_client = Minio(
            settings.minio_public_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    async def ensure_bucket(self) -> None:
        def ensure() -> None:
            if self._client.bucket_exists(self._bucket):
                return
            try:
                self._client.make_bucket(self._bucket)
            except S3Error as error:
                if error.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise

        await asyncio.to_thread(ensure)

    async def presigned_upload(self, object_key: str, expires: timedelta) -> str:
        await self.ensure_bucket()
        return await asyncio.to_thread(
            self._public_client.presigned_put_object,
            self._bucket,
            object_key,
            expires,
        )

    async def presigned_download(
        self,
        object_key: str,
        filename: str,
        expires: timedelta,
    ) -> str:
        return await asyncio.to_thread(
            self._public_client.presigned_get_object,
            self._bucket,
            object_key,
            expires,
            {"response-content-disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )

    async def stat(self, object_key: str) -> StoredObjectInfo:
        result = await asyncio.to_thread(self._client.stat_object, self._bucket, object_key)
        return StoredObjectInfo(size=int(result.size or 0), content_type=result.content_type)

    async def sha256(self, object_key: str) -> str:
        def calculate() -> str:
            response = self._client.get_object(self._bucket, object_key)
            digest = hashlib.sha256()
            try:
                for chunk in response.stream(1024 * 1024):
                    digest.update(chunk)
            finally:
                response.close()
                response.release_conn()
            return digest.hexdigest()

        return await asyncio.to_thread(calculate)

    async def put_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        await self.ensure_bucket()

        def upload() -> None:
            self._client.put_object(
                self._bucket,
                object_key,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(upload)

    async def remove(self, object_key: str) -> None:
        await asyncio.to_thread(self._client.remove_object, self._bucket, object_key)
