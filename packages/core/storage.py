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
        public_endpoint_url: str | None = None,
    ) -> None:
        self.bucket = bucket
        client_options = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region_name,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            **client_options,
        )
        self._presign_client = (
            self._client
            if public_endpoint_url is None or public_endpoint_url == endpoint_url
            else boto3.client("s3", endpoint_url=public_endpoint_url, **client_options)
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

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except (BotoCoreError, ClientError, KeyError) as error:
            raise StorageUnavailable("The stored document is unavailable") from error

    def generate_presigned_url(self, key: str, *, expires_in: int = 600) -> str:
        try:
            return self._presign_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError) as error:
            raise StorageUnavailable("A document URL could not be generated") from error

    def close(self) -> None:
        self._client.close()
        if self._presign_client is not self._client:
            self._presign_client.close()
