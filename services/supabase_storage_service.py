"""
Supabase Storage Service
Cloud-Based PDF Generation System - Milestone 8

Features:
- Official Supabase Python SDK client integration.
- Configurable via SUPABASE_URL, SUPABASE_KEY, and SUPABASE_BUCKET environment variables.
- Strictly protects credentials: never exposes private keys to frontend JavaScript.
- Enforces user-isolated storage paths ({user_id}/{doc_id}_{filename}.pdf) and path traversal validation.
- Generates secure short-lived presigned/signed URLs for private PDF viewing (inline) and downloading (attachment).
- Supports direct binary stream download, upload with Content-Type header, existence checking, and file deletion.
- Gracefully handles unconfigured states to allow seamless local development fallback.
- Free tier compliant (zero paid add-ons required).
"""
import os
import io
import re
import logging
from typing import Optional, Dict, Any, Tuple
from supabase import create_client, Client

logger = logging.getLogger(__name__)


def sanitize_storage_path(path: str) -> str:
    """
    Sanitize object path components to prevent path traversal vulnerabilities (e.g. '../').
    Allows alphanumeric characters, underscores, hyphens, dots, and forward slashes.
    """
    normalized = path.replace("\\", "/").strip()
    parts = [p for p in normalized.split("/") if p and p != "." and p != ".."]
    cleaned_parts = []
    for part in parts:
        clean = re.sub(r"[^\w\s\.-]", "", part)
        clean = re.sub(r"\s+", "_", clean).strip("-_")
        if not clean:
            clean = "document"
        cleaned_parts.append(clean)
    return "/".join(cleaned_parts)


class SupabaseStorageService:
    """
    Dedicated Service for managing PDF documents in Supabase Storage.
    """
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        client: Optional[Client] = None
    ):
        self.supabase_url = (supabase_url if supabase_url is not None else os.getenv("SUPABASE_URL", "")).strip()
        self.supabase_key = (supabase_key if supabase_key is not None else os.getenv("SUPABASE_KEY", "")).strip()
        self.bucket_name = (bucket_name if bucket_name is not None else os.getenv("SUPABASE_BUCKET", "")).strip()
        self._client = client

    def is_configured(self) -> bool:
        """Returns True if Supabase URL, key, and bucket name are non-empty."""
        return bool(self.supabase_url and self.supabase_key and self.bucket_name)

    @property
    def client(self) -> Optional[Client]:
        """Lazy-loaded official Supabase Client."""
        if self._client is None and self.supabase_url and self.supabase_key:
            try:
                self._client = create_client(self.supabase_url, self.supabase_key)
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                self._client = None
        return self._client

    def check_connection(self) -> Dict[str, Any]:
        """
        Actively checks connection to configured Supabase Storage bucket.
        Returns detailed status dictionary for health checks.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "accessible": False,
                "status": "unconfigured",
                "bucket": None
            }

        try:
            cl = self.client
            if not cl:
                return {
                    "configured": True,
                    "accessible": False,
                    "status": "client_init_failed",
                    "bucket": self.bucket_name,
                    "error": "Failed to create Supabase client."
                }

            # Probe bucket existence via storage.get_bucket
            bucket_info = cl.storage.get_bucket(self.bucket_name)
            is_public = getattr(bucket_info, "public", False)
            if isinstance(bucket_info, dict):
                is_public = bucket_info.get("public", False)

            return {
                "configured": True,
                "accessible": True,
                "status": "connected",
                "bucket": self.bucket_name,
                "public": is_public
            }
        except Exception as e:
            logger.warning(f"Supabase Storage connection probe failed for bucket '{self.bucket_name}': {e}")
            return {
                "configured": True,
                "accessible": False,
                "status": "unreachable",
                "bucket": self.bucket_name,
                "error": str(e)
            }

    def generate_storage_path(self, user_id: str, doc_id: str, filename_or_title: str) -> str:
        """
        Constructs a unique, secure user-isolated storage path in the bucket.
        Format: {safe_user_id}/{doc_id}_{safe_title}.pdf
        """
        safe_user = sanitize_storage_path(user_id or "USER-DEMO-001")
        base_name = os.path.basename(filename_or_title)
        if not base_name.lower().endswith(".pdf"):
            base_name = f"{base_name}.pdf"
        safe_file = sanitize_storage_path(base_name)
        if not safe_file.startswith(doc_id):
            safe_file = f"{doc_id}_{safe_file}"
        raw_path = f"{safe_user}/{safe_file}"
        return sanitize_storage_path(raw_path)

    def upload_pdf_bytes(
        self,
        pdf_bytes: bytes,
        storage_path: str,
        filename: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Uploads PDF bytes to private Supabase Storage bucket.
        Sets Content-Type: application/pdf and upsert=True.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "SUPABASE_NOT_CONFIGURED",
                "message": "Supabase environment variables (URL/KEY/BUCKET) are not configured."
            }

        safe_path = sanitize_storage_path(storage_path)

        try:
            cl = self.client
            if not cl:
                raise RuntimeError("Supabase client not initialized.")

            file_options = {
                "content-type": "application/pdf",
                "upsert": "true"
            }
            if metadata:
                file_options["metadata"] = metadata

            response = cl.storage.from_(self.bucket_name).upload(
                path=safe_path,
                file=pdf_bytes,
                file_options=file_options
            )

            storage_uri = f"supabase://{self.bucket_name}/{safe_path}"
            return {
                "success": True,
                "bucket": self.bucket_name,
                "path": safe_path,
                "storage_uri": storage_uri,
                "size_bytes": len(pdf_bytes),
                "response": response
            }
        except Exception as e:
            logger.error(f"Error uploading to Supabase Storage: {str(e)}")
            return {
                "success": False,
                "error": "UPLOAD_FAILED",
                "message": str(e)
            }

    def generate_signed_url(
        self,
        storage_path: str,
        filename: Optional[str] = None,
        as_attachment: bool = False,
        expiration: int = 3600
    ) -> Dict[str, Any]:
        """
        Generates a secure, short-lived signed URL for private bucket access.
        - as_attachment=False: Sets inline preview.
        - as_attachment=True: Passes download option to download file directly.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "SUPABASE_NOT_CONFIGURED",
                "message": "Supabase credentials are not configured."
            }

        safe_path = sanitize_storage_path(storage_path)
        safe_name = filename or os.path.basename(storage_path)

        try:
            cl = self.client
            if not cl:
                raise RuntimeError("Supabase client not initialized.")

            options: Dict[str, Any] = {}
            if as_attachment:
                options["download"] = safe_name

            res = cl.storage.from_(self.bucket_name).create_signed_url(
                path=safe_path,
                expires_in=expiration,
                options=options if options else None
            )

            url = None
            if isinstance(res, dict):
                url = res.get("signedURL") or res.get("signedUrl")
            elif hasattr(res, "signed_url"):
                url = res.signed_url
            elif hasattr(res, "signedURL"):
                url = res.signedURL
            elif hasattr(res, "signedUrl"):
                url = res.signedUrl

            if not url:
                return {
                    "success": False,
                    "error": "NO_SIGNED_URL_RETURNED",
                    "message": f"Unexpected response from Supabase Storage: {res}"
                }

            return {
                "success": True,
                "signed_url": url,
                "expires_in": expiration
            }
        except Exception as e:
            logger.error(f"Error generating signed URL in Supabase Storage: {str(e)}")
            return {
                "success": False,
                "error": "SIGNED_URL_FAILED",
                "message": str(e)
            }

    def download_pdf_stream(self, storage_path: str) -> Tuple[bool, Optional[bytes], Optional[str]]:
        """
        Downloads the PDF bytes directly from Supabase Storage.
        Returns (success, bytes, error_message).
        """
        if not self.is_configured():
            return False, None, "Supabase Storage is not configured."

        safe_path = sanitize_storage_path(storage_path)

        try:
            cl = self.client
            if not cl:
                return False, None, "Supabase client not initialized."

            pdf_bytes = cl.storage.from_(self.bucket_name).download(safe_path)
            return True, pdf_bytes, None
        except Exception as e:
            logger.error(f"Error downloading from Supabase Storage: {str(e)}")
            return False, None, str(e)

    def delete_file(self, storage_path: str) -> Dict[str, Any]:
        """
        Deletes a PDF document object from Supabase Storage.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "SUPABASE_NOT_CONFIGURED",
                "message": "Supabase Storage is not configured."
            }

        safe_path = sanitize_storage_path(storage_path)

        try:
            cl = self.client
            if not cl:
                raise RuntimeError("Supabase client not initialized.")

            res = cl.storage.from_(self.bucket_name).remove([safe_path])
            return {
                "success": True,
                "message": f"Object '{safe_path}' deleted from Supabase bucket '{self.bucket_name}'.",
                "response": res
            }
        except Exception as e:
            logger.error(f"Error deleting object from Supabase Storage: {str(e)}")
            return {
                "success": False,
                "error": "DELETE_FAILED",
                "message": str(e)
            }

    def file_exists(self, storage_path: str) -> bool:
        """
        Checks whether an object exists in the Supabase Storage bucket.
        """
        if not self.is_configured():
            return False

        safe_path = sanitize_storage_path(storage_path)

        try:
            cl = self.client
            if not cl:
                return False

            return bool(cl.storage.from_(self.bucket_name).exists(safe_path))
        except Exception as e:
            logger.warning(f"Error checking file_exists in Supabase: {e}")
            return False
