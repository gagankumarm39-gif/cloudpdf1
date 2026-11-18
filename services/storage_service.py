"""
Storage Service Abstraction for Cloud-Based PDF Generation System.
Orchestrates hybrid storage: saves locally for instant local availability and
syncs with Supabase Storage (or legacy S3 if configured).
Milestone 8: Primary cloud storage is Supabase Storage.
"""
import os
import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from services.supabase_storage_service import SupabaseStorageService, sanitize_storage_path
from services.s3_service import S3Service

# Local storage path for generated PDFs
STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "generated_pdfs")
os.makedirs(STORAGE_DIR, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """
    Sanitize document title or filename to prevent directory traversal
    and remove unsafe characters.
    """
    name = str(name).strip()
    clean = re.sub(r"[^\w\s-]", "", name)
    clean = re.sub(r"[-\s]+", "_", clean).strip("-_")
    if not clean:
        clean = "document"
    return clean[:50]


class StorageService:
    """
    Hybrid Storage Manager: Local Disk + Cloud Storage (Supabase Storage with S3 fallback/compatibility).
    """
    def __init__(
        self,
        base_dir: str = STORAGE_DIR,
        supabase_service: Optional[SupabaseStorageService] = None,
        s3_service: Optional[S3Service] = None
    ):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.supabase = supabase_service or SupabaseStorageService()
        self.s3 = s3_service or S3Service()

    def generate_storage_path(self, doc_id: str, title: str) -> str:
        """Construct a safe unique filename and local absolute filepath."""
        safe_title = sanitize_filename(title)
        filename = f"{doc_id}_{safe_title}.pdf"
        filepath = os.path.join(self.base_dir, filename)
        return filepath

    def generate_cloud_key(self, doc_id: str, title: str, user_id: Optional[str] = None) -> str:
        """
        Construct a unique and safe object path for cloud storage.
        If user_id is provided, enforces user folder isolation: {user_id}/{doc_id}_{safe_title}.pdf.
        """
        safe_title = sanitize_filename(title)
        safe_filename = f"{doc_id}_{safe_title}.pdf"
        if user_id:
            safe_user = sanitize_storage_path(user_id)
            return f"{safe_user}/{safe_filename}"
        return f"documents/{safe_filename}"

    # Alias for backwards compatibility
    def generate_s3_key(self, doc_id: str, title: str) -> str:
        return self.generate_cloud_key(doc_id, title)

    def save_pdf(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        title: str,
        author: str = "",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Saves PDF locally and automatically uploads to Supabase Storage (or S3 if active).
        """
        filepath = self.generate_storage_path(doc_id, title)
        filename = os.path.basename(filepath)

        # 1. Save locally
        with open(filepath, "wb") as f:
            f.write(pdf_bytes)

        file_size_bytes = len(pdf_bytes)
        file_size_kb = round(file_size_bytes / 1024, 1)

        cloud_key = self.generate_cloud_key(doc_id, title, user_id=user_id)

        result = {
            "doc_id": doc_id,
            "filename": filename,
            "filepath": filepath,
            "size_bytes": file_size_bytes,
            "size_formatted": f"{file_size_kb} KB",
            "storage_type": "local",
            "cloud_synced": False,
            "supabase_synced": False,
            "s3_synced": False,
            "storage_path": cloud_key,
            "s3_key": cloud_key,
            "supabase_bucket": self.supabase.bucket_name if self.supabase.is_configured() else None,
            "s3_bucket": self.s3.bucket_name if self.s3.is_configured() else None,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        # 2. Upload to Supabase Storage if configured (Milestone 8 priority)
        if self.supabase.is_configured():
            supa_res = self.supabase.upload_pdf_bytes(
                pdf_bytes=pdf_bytes,
                storage_path=cloud_key,
                filename=filename,
                metadata={"doc_id": doc_id, "title": title, "author": author, "user_id": user_id or ""}
            )
            if supa_res.get("success"):
                result["supabase_synced"] = True
                result["cloud_synced"] = True
                result["storage_type"] = "supabase_and_local"
                result["supabase_uri"] = supa_res.get("storage_uri")
                result["cloud_bucket"] = self.supabase.bucket_name
            else:
                result["supabase_error"] = supa_res.get("message")

        # 3. Coexistence with S3 if S3 configured (e.g. S3 test suites or hybrid transition)
        if self.s3.is_configured() and not result.get("supabase_synced"):
            s3_res = self.s3.upload_pdf_bytes(
                pdf_bytes=pdf_bytes,
                object_key=cloud_key,
                filename=filename,
                metadata={"doc_id": doc_id, "title": title, "author": author}
            )
            if s3_res.get("success"):
                result["s3_synced"] = True
                result["cloud_synced"] = True
                result["storage_type"] = "s3_and_local" if not result.get("supabase_synced") else "multi_cloud_and_local"
                result["s3_uri"] = s3_res.get("s3_uri")
                result["cloud_bucket"] = self.s3.bucket_name
            else:
                result["s3_error"] = s3_res.get("message")

        return result

    def save_pdf_bytes(self, pdf_bytes: bytes, doc_id: str, title: str) -> Dict[str, Any]:
        """Backward compatibility alias for M2/M3 calls."""
        return self.save_pdf(pdf_bytes, doc_id, title)

    def get_file_path(self, filename: str) -> str:
        """Return safe local filepath if it exists, otherwise raise FileNotFoundError."""
        safe_name = os.path.basename(filename)
        filepath = os.path.join(self.base_dir, safe_name)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File {safe_name} not found in local storage.")
        return filepath

    def file_exists(self, filename: str) -> bool:
        """Checks if a file exists locally."""
        safe_name = os.path.basename(filename)
        filepath = os.path.join(self.base_dir, safe_name)
        return os.path.exists(filepath)

    def delete_file(
        self,
        filename: str,
        storage_path: Optional[str] = None,
        s3_key: Optional[str] = None
    ) -> bool:
        """
        Deletes the file from local storage, Supabase Storage, and Amazon S3.
        """
        # 1. Delete local copy
        try:
            safe_name = os.path.basename(filename)
            filepath = os.path.join(self.base_dir, safe_name)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        target_cloud_path = storage_path or s3_key

        # 2. Delete Supabase Storage file if configured
        if target_cloud_path and self.supabase.is_configured():
            self.supabase.delete_file(target_cloud_path)

        # 3. Delete S3 object if configured
        if target_cloud_path and self.s3.is_configured():
            self.s3.delete_object(target_cloud_path)

        return True

    def get_preview_stream_or_url(
        self,
        filename: str,
        storage_path: Optional[str] = None,
        s3_key: Optional[str] = None
    ) -> Tuple[str, Any]:
        """
        Retrieves preview source.
        Returns ("url", signed_url) if Supabase or S3 is active, or ("local_path", filepath).
        """
        target_path = storage_path or s3_key

        # 1. Supabase Storage Signed URL (Milestone 8 priority)
        if self.supabase.is_configured() and target_path:
            res = self.supabase.generate_signed_url(target_path, filename=filename, as_attachment=False)
            if res.get("success"):
                return "url", res["signed_url"]

        # 2. S3 Presigned URL fallback
        if self.s3.is_configured() and target_path and self.s3.object_exists(target_path):
            res = self.s3.generate_presigned_url(target_path, filename=filename, as_attachment=False)
            if res.get("success"):
                return "url", res["presigned_url"]

        # 3. Fallback to local file
        filepath = self.get_file_path(filename)
        return "local_path", filepath

    def get_download_stream_or_url(
        self,
        filename: str,
        storage_path: Optional[str] = None,
        s3_key: Optional[str] = None
    ) -> Tuple[str, Any]:
        """
        Retrieves download source.
        Returns ("url", signed_url) if Supabase or S3 is active, or ("local_path", filepath).
        """
        target_path = storage_path or s3_key

        # 1. Supabase Storage Signed URL (Milestone 8 priority)
        if self.supabase.is_configured() and target_path:
            res = self.supabase.generate_signed_url(target_path, filename=filename, as_attachment=True)
            if res.get("success"):
                return "url", res["signed_url"]

        # 2. S3 Presigned URL fallback
        if self.s3.is_configured() and target_path and self.s3.object_exists(target_path):
            res = self.s3.generate_presigned_url(target_path, filename=filename, as_attachment=True)
            if res.get("success"):
                return "url", res["presigned_url"]

        # 3. Fallback to local file
        filepath = self.get_file_path(filename)
        return "local_path", filepath
