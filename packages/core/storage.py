"""S3-compatible storage for immutable source documents."""

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageUnavailable(RuntimeError):
    """Raised when object storage cannot complete an operation."""


class S3Storage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region_name: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region_name,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "")
            status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if error_code not in {"404", "NoSuchBucket", "NotFound"} and status_code != 404:
                raise StorageUnavailable("Object storage is unavailable") from error
        except BotoCoreError as error:
            raise StorageUnavailable("Object storage is unavailable") from error

        try:
            self._client.create_bucket(Bucket=self.bucket)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "")
            if error_code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise StorageUnavailable("Object storage is unavailable") from error
        except BotoCoreError as error:
            raise StorageUnavailable("Object storage is unavailable") from error

    def check_ready(self) -> None:
        self.ensure_bucket()

    def put(self, *, key: str, content: bytes, content_type: str, sha256: str) -> None:
        self.ensure_bucket()
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentLength=len(content),
                ContentType=content_type,
                Metadata={"sha256": sha256},
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageUnavailable("Object storage is unavailable") from error

    def close(self) -> None:
        self._client.close()
