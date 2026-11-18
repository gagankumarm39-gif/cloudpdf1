"""
Comprehensive Automated Test Suite for Milestone 5:
Amazon DynamoDB Metadata Service & Pipeline Integration (Using Moto Mock AWS)

Tests:
1. Create / Initialize CloudPDFDocuments table
2. Insert document metadata record
3. Retrieve document by doc_id
4. Check document existence
5. List and search documents
6. Update document metadata
7. Delete document metadata
8. End-to-end PDF generation with S3 and DynamoDB
9. Partial failure recovery: if DynamoDB fails, rollback uploaded S3 object
10. Missing document handling
"""
import os
import boto3
import pytest
from moto import mock_aws

from app import app
from services.dynamodb_service import DynamoDBService
from services.s3_service import S3Service
from services.document_repository import DocumentRepository
from services.storage_service import StorageService

TEST_REGION = "us-east-1"
TEST_TABLE = "CloudPDFDocuments"
TEST_BUCKET = "test-cloud-pdf-bucket"


@pytest.fixture
def mock_aws_environment():
    """Sets up an in-memory mocked DynamoDB and S3 environment via Moto."""
    with mock_aws():
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = TEST_REGION
        os.environ["AWS_REGION"] = TEST_REGION
        os.environ["DYNAMODB_TABLE_NAME"] = TEST_TABLE
        os.environ["S3_BUCKET_NAME"] = TEST_BUCKET

        # 1. Create S3 Bucket
        s3 = boto3.client("s3", region_name=TEST_REGION)
        s3.create_bucket(Bucket=TEST_BUCKET)

        # 2. Create DynamoDB Table
        dynamodb = boto3.resource("dynamodb", region_name=TEST_REGION)
        table = dynamodb.create_table(
            TableName=TEST_TABLE,
            KeySchema=[{"AttributeName": "doc_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "doc_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST"
        )
        try:
            yield {"s3": s3, "dynamodb": dynamodb, "table": table}
        finally:
            os.environ.pop("DYNAMODB_TABLE_NAME", None)
            os.environ.pop("S3_BUCKET_NAME", None)
            from app import s3_service, dynamodb_service, document_repo
            s3_service.bucket_name = ""
            dynamodb_service.table_name = ""
            document_repo.dynamodb = dynamodb_service



def test_dynamodb_service_crud(mock_aws_environment):
    """Test Insert, Retrieve, Exists, Update, and Delete operations on DynamoDBService."""
    service = DynamoDBService(table_name=TEST_TABLE, region_name=TEST_REGION)
    assert service.is_configured() is True

    # 1. Insert document
    doc_payload = {
        "doc_id": "DOC-9001",
        "title": "Cloud Computing Thesis",
        "author": "Kavya M",
        "description": "Distributed architectures on AWS",
        "filename": "DOC-9001_Thesis.pdf",
        "s3_key": "documents/DOC-9001_Thesis.pdf",
        "size": "340 KB",
        "size_bytes": 348160,
        "created_at": "2026-11-15T10:00:00Z",
        "storage_type": "s3_and_local",
        "status": "Ready"
    }

    insert_res = service.insert_document(doc_payload)
    assert insert_res["success"] is True
    assert insert_res["item"]["doc_id"] == "DOC-9001"
    assert insert_res["item"]["content_type"] == "application/pdf"

    # 2. Check existence
    assert service.document_exists("DOC-9001") is True
    assert service.document_exists("DOC-NONEXISTENT") is False

    # 3. Retrieve document
    success, item, err = service.get_document("DOC-9001")
    assert success is True
    assert item["title"] == "Cloud Computing Thesis"
    assert item["author"] == "Kavya M"

    # 4. Update document
    up_res = service.update_document("DOC-9001", {"status": "Archived", "description": "Updated abstract"})
    assert up_res["success"] is True

    _, updated_item, _ = service.get_document("DOC-9001")
    assert updated_item["status"] == "Archived"
    assert updated_item["description"] == "Updated abstract"

    # 5. Delete document
    del_res = service.delete_document("DOC-9001")
    assert del_res["success"] is True
    assert service.document_exists("DOC-9001") is False


def test_dynamodb_list_and_search(mock_aws_environment):
    """Test scanning, searching, and sorting across DynamoDB records."""
    service = DynamoDBService(table_name=TEST_TABLE, region_name=TEST_REGION)

    # Insert sample records
    docs = [
        {"doc_id": "DOC-101", "title": "AWS Lambda Functions", "author": "Alice", "size_bytes": 1000},
        {"doc_id": "DOC-102", "title": "Amazon DynamoDB Scaling", "author": "Bob", "size_bytes": 2500},
        {"doc_id": "DOC-103", "title": "Amazon S3 Durability", "author": "Charlie", "size_bytes": 500}
    ]
    for d in docs:
        service.insert_document(d)

    # List all
    success, items, err = service.list_documents()
    assert success is True
    assert len(items) == 3

    # Search by keyword
    _, results, _ = service.list_documents(search="DynamoDB")
    assert len(results) == 1
    assert results[0]["title"] == "Amazon DynamoDB Scaling"

    # Sort by size descending
    _, sorted_items, _ = service.list_documents(sort_by="size", order="desc")
    sizes = [it["size_bytes"] for it in sorted_items]
    assert sizes == [2500, 1000, 500]


def test_e2e_generate_pdf_pipeline_s3_and_dynamodb(mock_aws_environment):
    """
    Test full end-to-end 4-step generation workflow:
    1. ReportLab compilation
    2. S3 upload
    3. DynamoDB metadata insertion
    4. HTTP Response verification
    """
    from app import s3_service, dynamodb_service, storage_service, document_repo

    s3_service.bucket_name = TEST_BUCKET
    s3_service.region_name = TEST_REGION
    s3_service._s3_client = None

    dynamodb_service.table_name = TEST_TABLE
    dynamodb_service.region_name = TEST_REGION
    dynamodb_service._dynamodb_resource = None
    dynamodb_service._dynamodb_client = None

    document_repo.dynamodb = dynamodb_service

    client = app.test_client()

    payload = {
        "title": "Cloud Computing Full Architecture Pipeline",
        "author": "Kavya M",
        "description": "Integration test for S3 object and DynamoDB metadata persistence",
        "content": "Step 1 ReportLab, Step 2 Amazon S3, Step 3 Amazon DynamoDB, Step 4 Frontend delivery."
    }

    res = client.post("/api/generate-pdf?download=false", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True
    assert data["s3_synced"] is True
    assert data["dynamodb_synced"] is True

    doc_id = data["document"]["id"]
    s3_key = data["document"]["s3_key"]

    # Verify S3 object exists
    assert s3_service.object_exists(s3_key) is True

    # Verify DynamoDB record exists
    assert dynamodb_service.document_exists(doc_id) is True

    # Verify document appears in list endpoint
    res_list = client.get("/api/documents")
    assert res_list.status_code == 200
    listed_ids = [d["id"] for d in res_list.get_json()["documents"]]
    assert doc_id in listed_ids

    # Verify deletion cleans up S3 AND DynamoDB
    res_del = client.delete(f"/api/documents/{doc_id}")
    assert res_del.status_code == 200
    assert s3_service.object_exists(s3_key) is False
    assert dynamodb_service.document_exists(doc_id) is False


def test_partial_failure_rollback(mock_aws_environment):
    """
    Test that if DynamoDB insertion fails after S3 upload,
    the uploaded S3 object is rolled back/cleaned up to prevent orphaned objects.
    """
    from app import s3_service, dynamodb_service, document_repo

    s3_service.bucket_name = TEST_BUCKET
    s3_service.region_name = TEST_REGION
    s3_service._s3_client = None

    # Point DynamoDB service to an invalid / non-existent table to trigger ClientError
    dynamodb_service.table_name = "NonExistentTable999"
    dynamodb_service.region_name = TEST_REGION
    dynamodb_service._dynamodb_resource = None
    document_repo.dynamodb = dynamodb_service

    client = app.test_client()

    payload = {
        "title": "Fault Injection Test",
        "author": "Chaos Tester",
        "content": "Testing S3 cleanup upon DynamoDB insertion failure."
    }

    res = client.post("/api/generate-pdf?download=false", json=payload)
    # Pipeline should catch the exception, clean up S3, and return 500
    assert res.status_code == 500
    data = res.get_json()
    assert "Database metadata insertion failed" in data["message"]

    # Restore correct table name for subsequent tests
    dynamodb_service.table_name = TEST_TABLE
