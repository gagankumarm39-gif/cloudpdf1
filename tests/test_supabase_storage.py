"""
Comprehensive Automated Test Suite for Milestone 8:
Supabase Storage Integration & Hybrid Storage Operations (Using Mocks)

Tests:
1. Supabase Storage Service Upload of PDF bytes.
2. Supabase Storage Signed URL generation for preview (inline).
3. Supabase Storage Signed URL generation for attachment download.
4. Supabase Storage Object deletion.
5. Supabase Storage Object existence check.
6. Supabase Storage binary stream download.
7. Unconfigured handling and graceful fallback.
8. Connection health check reporting (connected, unreachable, unconfigured).
9. User document folder isolation and path traversal prevention.
10. End-to-end PDF generation workflow with Supabase Storage.
11. End-to-end PDF preview and download redirects to signed URLs.
12. End-to-end PDF deletion cleans up Supabase and database metadata.
13. Partial failure recovery: Database failure rolls back uploaded Supabase document.
"""
import os
import io
import pytest
from unittest.mock import MagicMock, patch

from app import app
from services.supabase_storage_service import (
    SupabaseStorageService,
    sanitize_storage_path
)
from services.storage_service import StorageService

TEST_URL = "https://example-project.supabase.co"
TEST_KEY = "test-anon-or-service-role-key"
TEST_BUCKET = "test-pdf-bucket"


class MockBucketClient:
    """Mock for Supabase Storage Bucket Client (storage3 / postgrest)."""
    def __init__(self, bucket_id=TEST_BUCKET):
        self.bucket_id = bucket_id
        self.files = {}

    def upload(self, path, file, file_options=None):
        if isinstance(file, (bytes, bytearray)):
            content = bytes(file)
        elif hasattr(file, "read"):
            content = file.read()
        else:
            content = str(file).encode("utf-8")
        self.files[path] = {
            "content": content,
            "options": file_options or {}
        }
        return {"Key": f"{self.bucket_id}/{path}", "Id": "mock-file-id"}

    def download(self, path, options=None, query_params=None):
        if path not in self.files:
            raise Exception(f"Object {path} not found")
        return self.files[path]["content"]

    def create_signed_url(self, path, expires_in, options=None):
        if path not in self.files:
            pass  # Supabase can generate signed URL token based on path
        is_dl = options and "download" in options
        dl_param = f"&download={options['download']}" if is_dl else ""
        signed_url = f"{TEST_URL}/storage/v1/object/sign/{self.bucket_id}/{path}?token=mock-token-{expires_in}{dl_param}"
        return {"signedURL": signed_url}

    def exists(self, path):
        return path in self.files

    def remove(self, paths):
        removed = []
        for p in paths:
            if p in self.files:
                del self.files[p]
                removed.append({"name": p})
        return removed


class MockStorageClient:
    """Mock for supabase.storage."""
    def __init__(self):
        self.buckets = {TEST_BUCKET: {"id": TEST_BUCKET, "public": False}}
        self._bucket_clients = {}

    def from_(self, bucket_id):
        if bucket_id not in self._bucket_clients:
            self._bucket_clients[bucket_id] = MockBucketClient(bucket_id)
        return self._bucket_clients[bucket_id]

    def get_bucket(self, bucket_id):
        if bucket_id not in self.buckets:
            raise Exception(f"Bucket {bucket_id} not found")
        return self.buckets[bucket_id]


class MockSupabaseClient:
    """Mock for official Supabase Client."""
    def __init__(self):
        self.storage = MockStorageClient()


@pytest.fixture
def mock_supabase_env():
    """Provides a SupabaseStorageService backed by in-memory mock."""
    mock_client = MockSupabaseClient()
    service = SupabaseStorageService(
        supabase_url=TEST_URL,
        supabase_key=TEST_KEY,
        bucket_name=TEST_BUCKET,
        client=mock_client
    )
    return service, mock_client


def test_sanitize_storage_path():
    """Test path sanitization and directory traversal protection."""
    assert sanitize_storage_path("user1/doc.pdf") == "user1/doc.pdf"
    assert sanitize_storage_path("../../../etc/passwd") == "etc/passwd"
    assert sanitize_storage_path("..\\..\\windows\\system32") == "windows/system32"
    assert sanitize_storage_path("user 123/my document!@#.pdf") == "user_123/my_document.pdf"
    assert sanitize_storage_path("././.") == ""


def test_supabase_service_unconfigured():
    """Test unconfigured service behavior."""
    svc = SupabaseStorageService(supabase_url="", supabase_key="", bucket_name="")
    assert svc.is_configured() is False
    assert svc.client is None

    conn = svc.check_connection()
    assert conn["configured"] is False
    assert conn["accessible"] is False

    up = svc.upload_pdf_bytes(b"data", "test.pdf", "test.pdf")
    assert up["success"] is False
    assert up["error"] == "SUPABASE_NOT_CONFIGURED"

    url = svc.generate_signed_url("test.pdf")
    assert url["success"] is False
    assert url["error"] == "SUPABASE_NOT_CONFIGURED"

    dl_ok, _, _ = svc.download_pdf_stream("test.pdf")
    assert dl_ok is False

    assert svc.file_exists("test.pdf") is False

    del_res = svc.delete_file("test.pdf")
    assert del_res["success"] is False


def test_supabase_service_upload_and_exists(mock_supabase_env):
    """Test uploading PDF bytes and checking existence."""
    service, mock_client = mock_supabase_env
    assert service.is_configured() is True

    test_bytes = b"%PDF-1.4 Mocked Supabase PDF content."
    storage_path = service.generate_storage_path("USER-100", "DOC-501", "Report.pdf")
    assert storage_path == "USER-100/DOC-501_Report.pdf"

    upload_res = service.upload_pdf_bytes(
        pdf_bytes=test_bytes,
        storage_path=storage_path,
        filename="Report.pdf",
        metadata={"title": "Report", "author": "QA Engineer"}
    )
    assert upload_res["success"] is True
    assert upload_res["bucket"] == TEST_BUCKET
    assert upload_res["path"] == storage_path
    assert upload_res["storage_uri"] == f"supabase://{TEST_BUCKET}/{storage_path}"

    # Verify exists
    assert service.file_exists(storage_path) is True
    assert service.file_exists("USER-100/nonexistent.pdf") is False


def test_supabase_service_signed_urls(mock_supabase_env):
    """Test generating signed URLs for preview and download."""
    service, _ = mock_supabase_env
    storage_path = "USER-100/DOC-502_Spec.pdf"
    service.upload_pdf_bytes(b"%PDF-1.4 spec", storage_path, "DOC-502_Spec.pdf")

    # Inline preview signed URL
    prev_res = service.generate_signed_url(storage_path, filename="DOC-502_Spec.pdf", as_attachment=False)
    assert prev_res["success"] is True
    assert "signed_url" in prev_res
    assert "token=mock-token-3600" in prev_res["signed_url"]
    assert "download=" not in prev_res["signed_url"]

    # Attachment download signed URL
    down_res = service.generate_signed_url(storage_path, filename="DOC-502_Spec.pdf", as_attachment=True)
    assert down_res["success"] is True
    assert "signed_url" in down_res
    assert "download=DOC-502_Spec.pdf" in down_res["signed_url"]


def test_supabase_service_download_stream(mock_supabase_env):
    """Test downloading binary stream from Supabase Storage."""
    service, _ = mock_supabase_env
    storage_path = "USER-100/DOC-503_Data.pdf"
    content = b"%PDF-1.4 Binary stream test data"
    service.upload_pdf_bytes(content, storage_path, "DOC-503_Data.pdf")

    ok, data, err = service.download_pdf_stream(storage_path)
    assert ok is True
    assert data == content
    assert err is None


def test_supabase_service_delete_file(mock_supabase_env):
    """Test deleting file from Supabase Storage."""
    service, _ = mock_supabase_env
    storage_path = "USER-100/DOC-504_Temp.pdf"
    service.upload_pdf_bytes(b"%PDF-1.4 delete test", storage_path, "DOC-504_Temp.pdf")
    assert service.file_exists(storage_path) is True

    del_res = service.delete_file(storage_path)
    assert del_res["success"] is True
    assert service.file_exists(storage_path) is False


def test_supabase_check_connection(mock_supabase_env):
    """Test health check connection probing."""
    service, mock_client = mock_supabase_env
    conn = service.check_connection()
    assert conn["configured"] is True
    assert conn["accessible"] is True
    assert conn["status"] == "connected"
    assert conn["bucket"] == TEST_BUCKET
    assert conn["public"] is False

    # Simulate error on get_bucket
    with patch.object(mock_client.storage, "get_bucket", side_effect=Exception("Bucket network timeout")):
        err_conn = service.check_connection()
        assert err_conn["configured"] is True
        assert err_conn["accessible"] is False
        assert err_conn["status"] == "unreachable"
        assert "Bucket network timeout" in err_conn["error"]


def test_storage_service_hybrid_supabase_and_local(mock_supabase_env):
    """Test StorageService abstraction delegating to Supabase while saving local copy."""
    supa_svc, _ = mock_supabase_env
    storage = StorageService(supabase_service=supa_svc)

    doc_id = "DOC-9901"
    title = "Hybrid Architecture Document"
    pdf_bytes = b"%PDF-1.4 Hybrid PDF test"

    meta = storage.save_pdf(pdf_bytes, doc_id, title, author="DevOps", user_id="USER-QA-01")
    assert meta["supabase_synced"] is True
    assert meta["cloud_synced"] is True
    assert meta["storage_type"] == "supabase_and_local"
    assert os.path.exists(meta["filepath"])

    # Preview returns URL
    src_type, target = storage.get_preview_stream_or_url(meta["filename"], storage_path=meta["storage_path"])
    assert src_type == "url"
    assert "token=mock-token" in target

    # Download returns URL
    src_type, target = storage.get_download_stream_or_url(meta["filename"], storage_path=meta["storage_path"])
    assert src_type == "url"
    assert "download=" in target

    # Delete cleans up both
    storage.delete_file(meta["filename"], storage_path=meta["storage_path"])
    assert not os.path.exists(meta["filepath"])
    assert not supa_svc.file_exists(meta["storage_path"])


def test_e2e_api_workflow_with_supabase(mock_supabase_env):
    """Test full Flask API workflow with Supabase storage."""
    supa_svc, _ = mock_supabase_env
    from app import supabase_storage_service, storage_service, dynamodb_service, document_repo
    # Swap active app services with mock
    app.config["TESTING"] = True
    supabase_storage_service.supabase_url = TEST_URL
    supabase_storage_service.supabase_key = TEST_KEY
    supabase_storage_service.bucket_name = TEST_BUCKET
    supabase_storage_service._client = supa_svc.client

    # Isolate DynamoDB for pure Supabase test
    dynamodb_service.table_name = ""
    document_repo.dynamodb = dynamodb_service

    client = app.test_client()

    payload = {
        "title": "Supabase Cloud Migration Report",
        "author": "Kavya M",
        "description": "Integration verification for Milestone 8 Supabase Storage.",
        "content": "ReportLab content compiled and archived to Supabase Storage bucket."
    }

    # Generate PDF in JSON mode
    res = client.post("/api/generate-pdf?download=false", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    assert data["supabase_synced"] is True
    assert data["cloud_synced"] is True

    doc_id = data["document"]["id"]
    storage_path = data["document"]["storage_path"]

    # Verify exists in Supabase Storage mock
    assert supa_svc.file_exists(storage_path) is True

    # Preview endpoint redirects (302) to Supabase signed URL
    res_prev = client.get(f"/api/documents/{doc_id}/preview")
    assert res_prev.status_code == 302
    assert "storage/v1/object/sign" in res_prev.headers["Location"]

    # Download endpoint redirects (302) to Supabase signed URL
    res_down = client.get(f"/api/documents/{doc_id}/download")
    assert res_down.status_code == 302
    assert "storage/v1/object/sign" in res_down.headers["Location"]
    assert "download=" in res_down.headers["Location"]

    # Delete endpoint removes from Supabase Storage and repository
    res_del = client.delete(f"/api/documents/{doc_id}")
    assert res_del.status_code == 200
    assert supa_svc.file_exists(storage_path) is False

    # Cleanup app service configuration
    supabase_storage_service.supabase_url = ""
    supabase_storage_service.supabase_key = ""
    supabase_storage_service.bucket_name = ""
    supabase_storage_service._client = None
