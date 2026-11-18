"""
Document Repository Abstraction for Cloud-Based PDF Generation System.
Orchestrates hybrid document persistence:
- When Supabase PostgreSQL is configured and accessible, uses PostgreSQL as primary source of truth (Milestone 9).
- When Amazon DynamoDB is configured and accessible, uses DynamoDB (Milestone 5-7 compatibility).
- Synchronizes with local storage/documents_metadata.json for local development fallback and cache.
- Exposes consistent API interface: list_all, get_by_id, add, delete, get_statistics.
"""
import os
import json
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
from services.dynamodb_service import DynamoDBService
from services.postgres_service import PostgresService

METADATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
METADATA_FILE = os.path.join(METADATA_DIR, "documents_metadata.json")


class DocumentRepository:
    """
    Hybrid Repository for Document Metadata.
    Coordinates Supabase PostgreSQL, Amazon DynamoDB and local JSON persistence.
    """
    def __init__(
        self,
        metadata_path: str = METADATA_FILE,
        dynamodb_service: Optional[DynamoDBService] = None,
        postgres_service: Optional[PostgresService] = None
    ):
        self.metadata_path = metadata_path
        self._lock = threading.Lock()
        self.dynamodb = dynamodb_service or DynamoDBService()
        self.postgres = postgres_service or PostgresService()
        self._ensure_storage()

    def is_postgres_configured(self) -> bool:
        """True if PostgreSQL DATABASE_URL is set."""
        return self.postgres.is_configured()

    def _ensure_storage(self):
        """Ensures storage directory and initial metadata JSON exist."""
        os.makedirs(os.path.dirname(self.metadata_path), exist_ok=True)
        if not os.path.exists(self.metadata_path):
            initial_seed = [
                {
                    "id": "DOC-8921",
                    "doc_id": "DOC-8921",
                    "title": "Cloud Computing Project Proposal",
                    "author": "Kavya M",
                    "description": "Semester project documentation covering AWS cloud architecture.",
                    "created_at": "2026-11-14T14:32:00Z",
                    "size": "245 KB",
                    "file_size": "245 KB",
                    "size_bytes": 250880,
                    "status": "Ready",
                    "filename": "DOC-8921_Cloud_Computing_Project_Proposal.pdf",
                    "s3_key": "documents/DOC-8921_Cloud_Computing_Project_Proposal.pdf",
                    "storage_type": "s3_and_local"
                },
                {
                    "id": "DOC-8920",
                    "doc_id": "DOC-8920",
                    "title": "AWS Architecture Blueprint",
                    "author": "Cloud Arch Team",
                    "description": "Technical specification for AWS cloud resources, VPC, and IAM.",
                    "created_at": "2026-11-13T18:10:00Z",
                    "size": "512 KB",
                    "file_size": "512 KB",
                    "size_bytes": 524288,
                    "status": "Ready",
                    "filename": "DOC-8920_AWS_Architecture_Blueprint.pdf",
                    "s3_key": "documents/DOC-8920_AWS_Architecture_Blueprint.pdf",
                    "storage_type": "s3_and_local"
                },
                {
                    "id": "DOC-8919",
                    "doc_id": "DOC-8919",
                    "title": "Quarterly Research Abstract",
                    "author": "Academic Dept",
                    "description": "Executive summary brief highlighting cloud business benefits.",
                    "created_at": "2026-11-12T09:45:00Z",
                    "size": "180 KB",
                    "file_size": "180 KB",
                    "size_bytes": 184320,
                    "status": "Ready",
                    "filename": "DOC-8919_Quarterly_Research_Abstract.pdf",
                    "s3_key": "documents/DOC-8919_Quarterly_Research_Abstract.pdf",
                    "storage_type": "s3_and_local"
                }
            ]
            self._write_records(initial_seed)

    def _read_records(self) -> List[Dict[str, Any]]:
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_records(self, records: List[Dict[str, Any]]):
        temp_file = self.metadata_path + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        os.replace(temp_file, self.metadata_path)

    def list_all(
        self,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "date",
        order: str = "desc"
    ) -> List[Dict[str, Any]]:
        """
        Retrieves documents for the specified user (or all if user_id is None).
        Prioritizes PostgreSQL (M9), then DynamoDB (M5-M7), then local JSON cache.
        """
        # 1. PostgreSQL (Milestone 9 priority)
        if self.is_postgres_configured():
            docs = self.postgres.list_documents(
                user_id=user_id,
                search=search,
                sort_by=sort_by,
                order=order
            )
            return docs

        # 2. DynamoDB (Milestone 5-M7 priority)
        if self.dynamodb.is_configured():
            success, items, _ = self.dynamodb.list_documents(user_id=user_id, search=search, sort_by=sort_by, order=order)
            if success:
                return items

        # Fallback to local JSON records
        with self._lock:
            records = self._read_records()

        # Migrate older records without user_id
        for r in records:
            if "user_id" not in r:
                r["user_id"] = "USER-DEMO-001"

        # User filter
        if user_id:
            records = [r for r in records if r.get("user_id") == user_id]

        # Search filter
        if search and search.strip():
            query = search.strip().lower()
            records = [
                r for r in records
                if query in r.get("title", "").lower()
                or query in r.get("author", "").lower()
                or query in r.get("id", "").lower()
                or query in r.get("doc_id", "").lower()
            ]

        # Sorting
        reverse = (order.lower() == "desc")
        if sort_by == "date":
            records.sort(key=lambda r: r.get("created_at", ""), reverse=reverse)
        elif sort_by == "title":
            records.sort(key=lambda r: r.get("title", "").lower(), reverse=reverse)
        elif sort_by == "size":
            records.sort(key=lambda r: int(r.get("size_bytes", 0)), reverse=reverse)

        return records

    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Find a single document by its ID (from Postgres, DynamoDB, or local storage)."""
        # 1. PostgreSQL (Milestone 9 priority)
        if self.is_postgres_configured():
            item = self.postgres.get_document_by_id(doc_id)
            if item:
                return item

        # 2. DynamoDB
        if self.dynamodb.is_configured():
            success, item, _ = self.dynamodb.get_document(doc_id)
            if success and item:
                return item

        # Fallback to local JSON
        with self._lock:
            records = self._read_records()
            for r in records:
                if r.get("id") == doc_id or r.get("doc_id") == doc_id:
                    return r
            return None

    def add(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves document metadata to PostgreSQL (if configured), DynamoDB (if configured)
        and synchronizes with local JSON store.
        """
        doc_id = document.get("doc_id") or document.get("id")
        document["doc_id"] = doc_id
        document["id"] = doc_id

        # 1. Save to PostgreSQL if configured (Milestone 9 priority)
        if self.is_postgres_configured():
            res = self.postgres.insert_document(document)
            if not res.get("success"):
                raise RuntimeError(f"PostgreSQL insertion failed: {res.get('message', res.get('error'))}")

        # 2. Save to DynamoDB if configured
        if self.dynamodb.is_configured():
            res = self.dynamodb.insert_document(document)
            if not res.get("success"):
                # Raise error so caller can safely handle partial failure
                raise RuntimeError(f"DynamoDB insertion failed: {res.get('message', res.get('error'))}")

        # 3. Sync to local JSON store
        with self._lock:
            records = self._read_records()
            records = [r for r in records if r.get("id") != doc_id]
            records.insert(0, document)
            self._write_records(records)

        return document

    def delete(self, doc_id: str) -> bool:
        """
        Deletes document metadata from PostgreSQL, DynamoDB, and local storage.
        """
        deleted_pg = False
        if self.is_postgres_configured():
            deleted_pg = self.postgres.delete_document(doc_id)

        # Delete from DynamoDB
        if self.dynamodb.is_configured():
            self.dynamodb.delete_document(doc_id)

        # Delete from local JSON
        with self._lock:
            records = self._read_records()
            initial_count = len(records)
            records = [r for r in records if r.get("id") != doc_id and r.get("doc_id") != doc_id]
            if len(records) < initial_count or deleted_pg:
                self._write_records(records)
                return True
            return False

    def get_statistics(
        self,
        user_id: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        s3_configured: bool = False,
        dynamodb_table: Optional[str] = None,
        dynamodb_configured: bool = False,
        region: str = "us-east-1",
        supabase_bucket: Optional[str] = None,
        supabase_configured: bool = False,
        postgres_configured: bool = False
    ) -> Dict[str, Any]:
        """Calculates dashboard statistics across managed documents (user-scoped if user_id given)."""
        records = self.list_all(user_id=user_id)

        total_count = len(records)
        total_bytes = sum(int(r.get("size_bytes", 0)) for r in records)

        if total_bytes < 1024:
            storage_str = f"{total_bytes} B"
        elif total_bytes < 1024 * 1024:
            storage_str = f"{round(total_bytes / 1024, 1)} KB"
        else:
            storage_str = f"{round(total_bytes / (1024 * 1024), 2)} MB"

        if supabase_configured and supabase_bucket:
            cloud_status = f"Supabase Storage ({supabase_bucket})"
        elif s3_configured and s3_bucket:
            cloud_status = f"Amazon S3 ({s3_bucket})"
        else:
            cloud_status = "Local Disk (Cloud Ready)"

        if postgres_configured or self.is_postgres_configured():
            db_status = "Supabase PostgreSQL"
        elif dynamodb_configured and dynamodb_table:
            db_status = f"DynamoDB ({dynamodb_table})"
        else:
            db_status = "Local JSON (Cloud DB Ready)"

        return {
            "total_generated": total_count,
            "total_bytes": total_bytes,
            "storage_used": storage_str,
            "cloud_storage_status": cloud_status,
            "database_status": db_status,
            "supabase_bucket": supabase_bucket or "Not Configured",
            "supabase_configured": supabase_configured,
            "postgres_configured": postgres_configured or self.is_postgres_configured(),
            "s3_bucket": s3_bucket or "Not Configured",
            "s3_configured": s3_configured,
            "dynamodb_table": dynamodb_table or "CloudPDFDocuments",
            "dynamodb_configured": dynamodb_configured,
            "active_region": region,
            "recent_count": min(total_count, 5)
        }

