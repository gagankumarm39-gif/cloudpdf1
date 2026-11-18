"""
Comprehensive Automated Test Suite for Milestone 3:
PDF Preview, Document Management, Search, Sorting, Deletion, and Dashboard Statistics.
"""
import io
import pytest
from app import app
from services.document_repository import DocumentRepository
from services.storage_service import StorageService


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_list_documents(client):
    """Test GET /api/documents returns documents and statistics."""
    res = client.get("/api/documents")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert isinstance(data["documents"], list)
    assert len(data["documents"]) >= 3
    assert "statistics" in data
    assert data["statistics"]["total_generated"] >= 3


def test_search_documents(client):
    """Test searching by title and author."""
    # Search for "Architecture"
    res = client.get("/api/documents?search=Architecture")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert len(data["documents"]) >= 1
    assert any("Architecture" in d["title"] for d in data["documents"])

    # Search non-existent
    res_none = client.get("/api/documents?search=NonExistentKeywordXYZ123")
    assert res_none.status_code == 200
    assert len(res_none.get_json()["documents"]) == 0


def test_sort_documents(client):
    """Test sorting by title asc/desc."""
    res_asc = client.get("/api/documents?sort=title&order=asc")
    assert res_asc.status_code == 200
    titles_asc = [d["title"].lower() for d in res_asc.get_json()["documents"]]
    assert titles_asc == sorted(titles_asc)

    res_desc = client.get("/api/documents?sort=title&order=desc")
    assert res_desc.status_code == 200
    titles_desc = [d["title"].lower() for d in res_desc.get_json()["documents"]]
    assert titles_desc == sorted(titles_desc, reverse=True)


def test_preview_document(client):
    """Test GET /api/documents/<id>/preview returns inline PDF (as_attachment=False)."""
    # Fetch existing document ID
    res = client.get("/api/documents")
    docs = res.get_json()["documents"]
    assert len(docs) > 0
    target_id = docs[0]["id"]

    res_preview = client.get(f"/api/documents/{target_id}/preview")
    assert res_preview.status_code == 200
    assert res_preview.mimetype == "application/pdf"
    assert res_preview.data.startswith(b"%PDF-")
    # Verify Content-Disposition is inline (not attachment)
    disposition = res_preview.headers.get("Content-Disposition", "")
    assert "inline" in disposition or "attachment" not in disposition


def test_download_document_by_id(client):
    """Test GET /api/documents/<id>/download returns attachment."""
    res = client.get("/api/documents")
    docs = res.get_json()["documents"]
    target_id = docs[0]["id"]

    res_download = client.get(f"/api/documents/{target_id}/download")
    assert res_download.status_code == 200
    assert res_download.mimetype == "application/pdf"
    assert res_download.data.startswith(b"%PDF-")
    assert "attachment" in res_download.headers.get("Content-Disposition", "")


def test_preview_and_download_nonexistent_doc(client):
    """Test 404 behavior for invalid doc IDs."""
    res_prev = client.get("/api/documents/INVALID-ID-9999/preview")
    assert res_prev.status_code == 404

    res_down = client.get("/api/documents/INVALID-ID-9999/download")
    assert res_down.status_code == 404


def test_create_and_delete_document_workflow(client):
    """
    Test full lifecycle:
    1. Generate PDF via POST /api/generate-pdf?download=false
    2. Verify it appears in GET /api/documents
    3. Preview document
    4. Download document
    5. Delete document via DELETE /api/documents/<id>
    6. Verify it is removed from list
    """
    payload = {
        "title": "Temporary Lifecycle Test Document",
        "author": "QA Automation",
        "description": "Will be created and subsequently deleted",
        "content": "Lifecycle testing paragraph verifying full Milestone 3 capabilities."
    }

    # 1. Create
    res_create = client.post("/api/generate-pdf?download=false", json=payload)
    assert res_create.status_code == 201
    created_doc = res_create.get_json()["document"]
    doc_id = created_doc["id"]
    assert doc_id.startswith("DOC-")

    # 2. Verify in list
    res_list = client.get(f"/api/documents?search={doc_id}")
    assert res_list.status_code == 200
    assert any(d["id"] == doc_id for d in res_list.get_json()["documents"])

    # 3. Preview
    res_prev = client.get(f"/api/documents/{doc_id}/preview")
    assert res_prev.status_code == 200
    assert res_prev.data.startswith(b"%PDF-")

    # 4. Download
    res_down = client.get(f"/api/documents/{doc_id}/download")
    assert res_down.status_code == 200
    assert res_down.data.startswith(b"%PDF-")

    # 5. Delete
    res_del = client.delete(f"/api/documents/{doc_id}")
    assert res_del.status_code == 200
    del_data = res_del.get_json()
    assert del_data["success"] is True
    assert del_data["deleted_id"] == doc_id

    # 6. Verify removed
    res_after = client.get(f"/api/documents?search={doc_id}")
    assert len(res_after.get_json()["documents"]) == 0

    # 7. Delete again should return 404
    res_del_again = client.delete(f"/api/documents/{doc_id}")
    assert res_del_again.status_code == 404
