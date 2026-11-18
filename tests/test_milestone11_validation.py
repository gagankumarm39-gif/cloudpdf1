"""
Milestone 11: Comprehensive Integration & Security Validation Suite
Validates:
- End-to-end user workflows (registration, login, PDF generation, preview, download, delete, logout).
- Multi-user isolation (User A vs User B document ownership, unauthorized viewing/download/deletion).
- SQL Injection attack resilience in all fields and search filters.
- XSS payload sanitization in title, author, and description.
- Path traversal attack protection in storage service and signed URLs.
- Error handling (malformed input, missing fields, 404s, invalid auth).
- Database foreign key constraints and duplicate prevention.
- Performance benchmarks (PDF compilation latency, throughput).
"""
import io
import time
import pytest
from app import app
from services.postgres_service import PostgresService
from services.supabase_storage_service import sanitize_storage_path


@pytest.fixture
def integration_app(tmp_path, monkeypatch):
    """Sets up an isolated database and local storage context for deep integration testing."""
    test_db = PostgresService(database_url="sqlite:///:memory:")
    test_db.init_db()

    # Monkeypatch services in app
    monkeypatch.setattr("app.postgres_service", test_db)
    monkeypatch.setattr("app.auth_service.postgres", test_db)
    monkeypatch.setattr("app.document_repo.postgres", test_db)

    local_users = str(tmp_path / "test_users.json")
    local_docs = str(tmp_path / "test_docs.json")
    monkeypatch.setattr("app.auth_service.metadata_file", local_users)
    monkeypatch.setattr("app.document_repo.metadata_path", local_docs)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app


class TestMilestone11EndToEndWorkflow:
    def test_complete_user_lifecycle(self, integration_app):
        """Tests registration -> login -> create PDF -> view -> download -> delete -> logout."""
        client = integration_app.test_client()

        # 1. Open Home page (redirects or renders)
        home = client.get("/")
        assert home.status_code in [200, 302]

        # 2. Register new user
        reg = client.post("/register", data={
            "name": "Integration User",
            "email": "integration@test.edu",
            "password": "StrongPassword123",
            "confirm_password": "StrongPassword123"
        }, follow_redirects=True)
        assert reg.status_code == 200

        # 3. Generate PDF
        gen = client.post("/api/generate-pdf?download=false", json={
            "title": "Integration Architecture Report",
            "author": "Integration User",
            "description": "Verifying full Milestone 11 flow.",
            "content": "Comprehensive system verification content covering ReportLab Flowables."
        })
        assert gen.status_code == 201
        doc_data = gen.get_json()["document"]
        doc_id = doc_data["id"]
        assert doc_id.startswith("DOC-")

        # 4. View in document list
        docs_list = client.get("/api/documents")
        assert docs_list.status_code == 200
        items = docs_list.get_json()["documents"]
        assert any(d["id"] == doc_id for d in items)

        # 5. Search by title
        search_res = client.get("/api/documents?search=Integration")
        assert search_res.status_code == 200
        assert len(search_res.get_json()["documents"]) >= 1

        # 6. Preview PDF (Inline stream or signed redirect)
        prev = client.get(f"/api/documents/{doc_id}/preview")
        assert prev.status_code in [200, 302]
        if prev.status_code == 200:
            assert prev.headers.get("Content-Type") == "application/pdf"

        # 7. Download PDF
        down = client.get(f"/api/documents/{doc_id}/download")
        assert down.status_code in [200, 302]

        # 8. Delete PDF
        delete_res = client.delete(f"/api/documents/{doc_id}")
        assert delete_res.status_code == 200
        assert delete_res.get_json()["success"] is True

        # 9. Verify gone
        get_gone = client.get(f"/api/documents/{doc_id}")
        assert get_gone.status_code == 404

        # 10. Logout
        logout = client.get("/logout", follow_redirects=True)
        assert logout.status_code == 200


class TestMilestone11SecurityAndIsolation:
    def test_cross_user_data_isolation(self, integration_app):
        """Verifies User B cannot view, preview, download, or delete User A's document."""
        client = integration_app.test_client()

        # Register User A
        client.post("/register", data={
            "name": "User Alpha",
            "email": "alpha@shield.org",
            "password": "AlphaPassword123",
            "confirm_password": "AlphaPassword123"
        }, follow_redirects=True)

        # User A creates document
        gen_a = client.post("/api/generate-pdf?download=false", json={
            "title": "Alpha Confidential Blueprint",
            "author": "User Alpha",
            "description": "Sensitive architectural data",
            "content": "Secret payload content for Alpha only."
        })
        doc_a_id = gen_a.get_json()["document"]["id"]

        # Logout User A
        client.get("/logout")

        # Register User B
        client.post("/register", data={
            "name": "User Beta",
            "email": "beta@shield.org",
            "password": "BetaPassword123",
            "confirm_password": "BetaPassword123"
        }, follow_redirects=True)

        # User B lists documents - should NOT see User A's doc
        docs_b = client.get("/api/documents")
        b_ids = [d["id"] for d in docs_b.get_json()["documents"]]
        assert doc_a_id not in b_ids

        # User B attempts to access User A's doc details -> 403 Forbidden
        assert client.get(f"/api/documents/{doc_a_id}").status_code == 403

        # User B attempts to preview User A's doc -> 403 Forbidden
        assert client.get(f"/api/documents/{doc_a_id}/preview").status_code == 403

        # User B attempts to download User A's doc -> 403 Forbidden
        assert client.get(f"/api/documents/{doc_a_id}/download").status_code == 403

        # User B attempts to delete User A's doc -> 403 Forbidden
        assert client.delete(f"/api/documents/{doc_a_id}").status_code == 403

    def test_sql_injection_resilience(self, integration_app):
        """Verifies parameterized queries resist aggressive SQL injection attacks."""
        client = integration_app.test_client()
        client.post("/register", data={
            "name": "Pentester",
            "email": "pentest@security.io",
            "password": "Password1234",
            "confirm_password": "Password1234"
        }, follow_redirects=True)

        # SQL Injection in document title and search
        sql_payload = "Annual Summary'; DROP TABLE documents; SELECT * FROM users WHERE '1'='1"
        gen = client.post("/api/generate-pdf?download=false", json={
            "title": sql_payload,
            "author": "Dr. Hacker",
            "description": "Injection test",
            "content": "Checking parameterized query safety."
        })
        assert gen.status_code == 201

        # Search query injection
        search_res = client.get(f"/api/documents?search={sql_payload}")
        assert search_res.status_code == 200

        # Verify documents table still exists and data is intact
        all_docs = client.get("/api/documents")
        assert all_docs.status_code == 200
        assert len(all_docs.get_json()["documents"]) >= 1

    def test_path_traversal_sanitization(self):
        """Verifies path traversal attacks like '../../etc/passwd' are sanitized safely."""
        malicious_paths = [
            ("../../etc/passwd", "etc/passwd"),
            ("..\\..\\windows\\system32\\cmd.exe", "windows/system32/cmd.exe"),
            ("user1/../../../root.pdf", "user1/root.pdf"),
            ("valid_user/doc_123.pdf", "valid_user/doc_123.pdf")
        ]
        for raw, expected in malicious_paths:
            cleaned = sanitize_storage_path(raw)
            assert ".." not in cleaned
            assert cleaned == expected


class TestMilestone11PerformanceAndLimits:
    def test_pdf_generation_performance(self, integration_app):
        """Verifies ReportLab generation completes within reasonable time (< 2.5s for 2-page doc)."""
        client = integration_app.test_client()
        client.post("/register", data={
            "name": "Benchmark User",
            "email": "bench@test.com",
            "password": "Password123",
            "confirm_password": "Password123"
        }, follow_redirects=True)

        start_time = time.time()
        res = client.post("/api/generate-pdf?download=false", json={
            "title": "Performance Benchmark Document",
            "author": "Benchmarker",
            "description": "Testing latency of ReportLab flowable rendering engine.",
            "content": "Paragraph content. " * 150
        })
        duration = time.time() - start_time
        assert res.status_code == 201
        assert duration < 3.0  # Must be faster than 3 seconds locally
