"""
Amazon S3 Cloud Storage Service
Cloud-Based PDF Generation System - Milestone 4

Features:
- Connects using Boto3 default credential provider chain (Supports IAM Roles, AWS CLI profiles, and environment variables).
- Configurable via AWS_REGION and S3_BUCKET_NAME.
- Never requires hardcoded credentials.
- Gracefully handles non-configured states for seamless local development.
- Implements secure presigned URLs (short-lived) for private S3 PDF preview and download.
- Full error handling for NoSuchBucket, NoSuchKey, ClientError, and NoCredentialsError.
"""
import os
import io
import logging
from typing import Optional, Dict, Any, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
from botocore.config import Config

logger = logging.getLogger(__name__)

class S3Service:
    """
    Dedicated Service for managing PDF objects in Amazon S3.
    """
    def __init__(self, bucket_name: Optional[str] = None, region_name: Optional[str] = None):
        # Read from environment variables if bucket_name is None
        if bucket_name is not None:
            self.bucket_name = bucket_name.strip()
        else:
            self.bucket_name = os.getenv("S3_BUCKET_NAME", "").strip()

        if region_name is not None:
            self.region_name = region_name.strip()
        else:
            self.region_name = os.getenv("AWS_REGION", "us-east-1").strip()

        
        # Boto3 client with standard retry configuration
        self._s3_client = None
        self._config = Config(
            region_name=self.region_name,
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"}
        )

    def is_configured(self) -> bool:
        """Checks whether an S3 bucket name is specified."""
        return bool(self.bucket_name)

    def check_connection(self) -> Dict[str, Any]:
        """
        Actively checks connection to configured Amazon S3 bucket using head_bucket.
        Returns detailed status for health checks.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "accessible": False,
                "status": "unconfigured",
                "bucket": None
            }
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            return {
                "configured": True,
                "accessible": True,
                "status": "connected",
                "bucket": self.bucket_name,
                "region": self.region_name
            }
        except Exception as e:
            logger.warning(f"S3 health check probe failed for bucket '{self.bucket_name}': {e}")
            return {
                "configured": True,
                "accessible": False,
                "status": "unreachable",
                "bucket": self.bucket_name,
                "error": str(e)
            }

    @property
    def client(self):
        """Lazy-loaded boto3 client using default AWS credential provider chain."""
        if self._s3_client is None:
            # Let boto3 resolve credentials via env vars, ~/.aws/credentials, or EC2/ECS IAM instance profile
            self._s3_client = boto3.client("s3", config=self._config)
        return self._s3_client

    def upload_pdf_bytes(
        self,
        pdf_bytes: bytes,
        object_key: str,
        filename: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Uploads PDF bytes to private Amazon S3 bucket.
        Stores filename and custom tags in object metadata.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "S3_NOT_CONFIGURED",
                "message": "S3_BUCKET_NAME environment variable is not configured."
            }

        extra_args = {
            "ContentType": "application/pdf",
            "ContentDisposition": f'attachment; filename="{filename}"'
        }

        s3_metadata = {"filename": filename}
        if metadata:
            s3_metadata.update(metadata)
        extra_args["Metadata"] = s3_metadata

        try:
            buffer = io.BytesIO(pdf_bytes)
            self.client.upload_fileobj(
                Fileobj=buffer,
                Bucket=self.bucket_name,
                Key=object_key,
                ExtraArgs=extra_args
            )

            s3_uri = f"s3://{self.bucket_name}/{object_key}"
            return {
                "success": True,
                "bucket": self.bucket_name,
                "key": object_key,
                "s3_uri": s3_uri,
                "size_bytes": len(pdf_bytes)
            }
        except NoCredentialsError:
            logger.error("AWS credentials not found in credential chain.")
            return {
                "success": False,
                "error": "NO_CREDENTIALS",
                "message": "AWS credentials were not found in credential chain (IAM role/env)."
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"S3 ClientError during upload: {error_code} - {error_msg}")
            return {
                "success": False,
                "error": error_code,
                "message": error_msg
            }
        except Exception as e:
            logger.error(f"Unexpected error uploading to S3: {str(e)}")
            return {
                "success": False,
                "error": "UPLOAD_FAILED",
                "message": str(e)
            }

    def generate_presigned_url(
        self,
        object_key: str,
        filename: Optional[str] = None,
        as_attachment: bool = False,
        expiration: int = 3600
    ) -> Dict[str, Any]:
        """
        Generates a secure, short-lived presigned URL for private S3 object access.
        - as_attachment=False: Sets Content-Disposition to inline for browser preview.
        - as_attachment=True: Sets Content-Disposition to attachment for direct download.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "S3_NOT_CONFIGURED",
                "message": "S3_BUCKET_NAME is not configured."
            }

        params = {
            "Bucket": self.bucket_name,
            "Key": object_key
        }

        # Override response headers for secure inline preview vs attachment download
        if as_attachment:
            safe_name = filename or os.path.basename(object_key)
            params["ResponseContentDisposition"] = f'attachment; filename="{safe_name}"'
        else:
            params["ResponseContentDisposition"] = "inline"
        params["ResponseContentType"] = "application/pdf"

        try:
            url = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=expiration
            )
            return {
                "success": True,
                "presigned_url": url,
                "expires_in": expiration
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            return {
                "success": False,
                "error": error_code,
                "message": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "error": "PRESIGNED_URL_FAILED",
                "message": str(e)
            }

    def download_pdf_stream(self, object_key: str) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Downloads the PDF bytes directly from S3 (e.g. for proxy streaming or testing).
        Returns (success, bytes, error_message).
        """
        if not self.is_configured():
            return False, None, "S3_BUCKET_NAME is not configured."

        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=object_key)
            pdf_bytes = response["Body"].read()
            return True, pdf_bytes, None
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            return False, None, f"S3 Error: {error_code}"
        except Exception as e:
            return False, None, str(e)

    def delete_object(self, object_key: str) -> Dict[str, Any]:
        """
        Deletes a PDF document object from Amazon S3.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "S3_NOT_CONFIGURED",
                "message": "S3_BUCKET_NAME is not configured."
            }

        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=object_key)
            return {
                "success": True,
                "message": f"Object '{object_key}' deleted from bucket '{self.bucket_name}'."
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            return {
                "success": False,
                "error": error_code,
                "message": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "error": "DELETE_FAILED",
                "message": str(e)
            }

    def object_exists(self, object_key: str) -> bool:
        """
        Checks whether an object exists in the S3 bucket using head_object.
        """
        if not self.is_configured():
            return False

        try:
            self.client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ["404", "NoSuchKey", "NotFound"]:
                return False
            logger.warning(f"Error checking object_exists for {object_key}: {e}")
            return False
        except Exception:
            return False
