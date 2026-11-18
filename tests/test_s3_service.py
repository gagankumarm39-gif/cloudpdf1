"""
Comprehensive Automated Test Suite for Milestone 4:
Amazon S3 Cloud Storage Integration (Using Moto Mock S3)

Tests:
1. S3 Upload of generated PDF bytes
2. S3 Presigned URL generation for inline preview
3. S3 Presigned URL generation for attachment download
4. S3 Object deletion
5. S3 Object existence checking (head_object)
6. Error handling when S3 is unconfigured or credentials missing
7. End-to-end PDF generation workflow with active S3 bucket
8. Deletion workflow removing objects from both S3 and repository
"""
import os
import boto3
import pytest
from moto import mock_aws

from app import app
from services.s3_service import S3Service
from services.storage_service import StorageService
from services.pdf_service import PDFGeneratorService
from services.document_repository import DocumentRepository


TEST_BUCKET = "test-cloud-pdf-bucket"
TEST_REGION = "us-east-1"


@pytest.fixture
def mock_s3_environment():
    """Sets up an in-memory mocked S3 bucket via Moto."""
    with mock_aws():
        # Set dummy credentials so boto3 will never fail looking for credentials
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = TEST_REGION
        os.environ["S3_BUCKET_NAME"] = TEST_BUCKET
        os.environ["AWS_REGION"] = TEST_REGION

        # Create mock bucket
        s3 = boto3.client("s3", region_name=TEST_REGION)
        s3.create_bucket(Bucket=TEST_BUCKET)
        try:
            yield s3
        finally:
            os.environ.pop("S3_BUCKET_NAME", None)
            from app import s3_service
            s3_service.bucket_name = ""



def test_s3_service_upload_and_exists(mock_s3_environment):
    """Test uploading PDF bytes to S3 and verifying object exists."""
    s3_svc = S3Service(bucket_name=TEST_BUCKET, region_name=TEST_REGION)
    assert s3_svc.is_configured() is True

    test_bytes = b"%PDF-1.4 Mocked PDF content for S3 test."
    key = "documents/DOC-TEST-1001_Test_Doc.pdf"

    upload_res = s3_svc.upload_pdf_bytes(
        pdf_bytes=test_bytes,
        object_key=key,
        filename="DOC-TEST-1001_Test_Doc.pdf",
        metadata={"title": "Test Doc", "author": "QA Engineer"}
    )

    assert upload_res["success"] is True
    assert upload_res["key"] == key
    assert upload_res["s3_uri"] == f"s3://{TEST_BUCKET}/{key}"

    # Verify exists
    assert s3_svc.object_exists(key) is True
    # Verify non-existent key returns False
    assert s3_svc.object_exists("documents/does_not_exist.pdf") is False


def test_s3_presigned_urls(mock_s3_environment):
    """Test generating presigned URLs for preview and download."""
    s3_svc = S3Service(bucket_name=TEST_BUCKET, region_name=TEST_REGION)
    key = "documents/DOC-TEST-URL.pdf"
    s3_svc.upload_pdf_bytes(b"%PDF-1.4 test", key, "DOC-TEST-URL.pdf")

    # Preview URL (inline)
    prev_res = s3_svc.generate_presigned_url(key, filename="DOC-TEST-URL.pdf", as_attachment=False)
    assert prev_res["success"] is True
    assert "presigned_url" in prev_res
    assert TEST_BUCKET in prev_res["presigned_url"]

    # Download URL (attachment)
    down_res = s3_svc.generate_presigned_url(key, filename="DOC-TEST-URL.pdf", as_attachment=True)
    assert down_res["success"] is True
    assert "presigned_url" in down_res
    assert "response-content-disposition" in down_res["presigned_url"].lower()


def test_s3_delete_object(mock_s3_environment):
    """Test deleting an object from S3."""
    s3_svc = S3Service(bucket_name=TEST_BUCKET, region_name=TEST_REGION)
    key = "documents/DOC-TO-DELETE.pdf"
    s3_svc.upload_pdf_bytes(b"%PDF-1.4 delete test", key, "DOC-TO-DELETE.pdf")
    assert s3_svc.object_exists(key) is True

    del_res = s3_svc.delete_object(key)
    assert del_res["success"] is True
    assert s3_svc.object_exists(key) is False


def test_s3_download_stream(mock_s3_environment):
    """Test downloading binary stream directly from S3."""
    s3_svc = S3Service(bucket_name=TEST_BUCKET, region_name=TEST_REGION)
    key = "documents/DOC-STREAM.pdf"
    content = b"%PDF-1.4 streamable byte content"
    s3_svc.upload_pdf_bytes(content, key, "DOC-STREAM.pdf")

    success, data, err = s3_svc.download_pdf_stream(key)
    assert success is True
    assert data == content
    assert err is None


def test_s3_unconfigured_error_handling():
    """Test that S3Service handles unconfigured bucket name gracefully without crashing."""
    s3_svc = S3Service(bucket_name="", region_name=TEST_REGION)
    assert s3_svc.is_configured() is False

    res_upload = s3_svc.upload_pdf_bytes(b"data", "key.pdf", "key.pdf")
    assert res_upload["success"] is False
    assert res_upload["error"] == "S3_NOT_CONFIGURED"

    res_url = s3_svc.generate_presigned_url("key.pdf")
    assert res_url["success"] is False
    assert res_url["error"] == "S3_NOT_CONFIGURED"

    assert s3_svc.object_exists("key.pdf") is False


def test_e2e_api_generate_pdf_with_s3(mock_s3_environment):
    """Test full Flask API workflow with S3 upload and presigned redirect preview."""
    # Ensure app uses mock s3 service and isolate from dynamodb for this pure S3 test
    from app import s3_service, dynamodb_service, storage_service, document_repo
    s3_service.bucket_name = TEST_BUCKET
    s3_service.region_name = TEST_REGION
    s3_service._s3_client = None  # Reset client to use mock

    # Ensure DynamoDB is disabled for this test to isolate S3 behavior
    dynamodb_service.table_name = ""
    document_repo.dynamodb = dynamodb_service

    client = app.test_client()

    payload = {
        "title": "Cloud Architecture S3 Report",
        "author": "Kavya M",
        "description": "Integration test for S3 PutObject and Presigned URL generation",
        "content": "Testing seamless Amazon S3 storage integration with local disk backup."
    }

    # Generate document in JSON mode
    res = client.post("/api/generate-pdf?download=false", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    assert data["s3_synced"] is True

    doc_id = data["document"]["id"]
    s3_key = data["document"]["s3_key"]

    # Verify object actually exists in mocked S3 bucket
    assert s3_service.object_exists(s3_key) is True

    # Test Preview endpoint redirects to S3 presigned URL (HTTP 302)
    res_prev = client.get(f"/api/documents/{doc_id}/preview")
    assert res_prev.status_code == 302
    assert TEST_BUCKET in res_prev.headers["Location"]

    # Test Download endpoint redirects to S3 presigned URL (HTTP 302)
    res_down = client.get(f"/api/documents/{doc_id}/download")
    assert res_down.status_code == 302
    assert TEST_BUCKET in res_down.headers["Location"]

    # Test Delete removes from S3 and repo
    res_del = client.delete(f"/api/documents/{doc_id}")
    assert res_del.status_code == 200
    assert s3_service.object_exists(s3_key) is False
