"""
Tests for Supabase PostgreSQL Database Integration (Milestone 9).
Uses in-memory SQLite (via SQLAlchemy) to test the database service, models,
foreign key relationships, parameterized query safety, user auth, and document repository
without requiring external network connections or paid cloud resources.
"""
import pytest
from datetime import datetime
from services.postgres_service import PostgresService, Base
from services.auth_service import AuthService
from services.document_repository import DocumentRepository


@pytest.fixture
def memory_pg_service():
    """Initializes an in-memory SQLite database using PostgresService abstraction."""
    service = PostgresService(database_url="sqlite:///:memory:")
    service.init_db()
    return service


@pytest.fixture
def memory_auth_service(memory_pg_service, tmp_path):
    """AuthService wired to in-memory database and temporary local JSON file."""
    local_meta = str(tmp_path / "users_test.json")
    auth = AuthService(postgres_service=memory_pg_service)
    auth.metadata_file = local_meta
    auth._ensure_local_store()
    return auth


@pytest.fixture
def memory_doc_repo(memory_pg_service, tmp_path):
    """DocumentRepository wired to in-memory database and temporary local JSON file."""
    local_meta = str(tmp_path / "docs_test.json")
    repo = DocumentRepository(metadata_path=local_meta, postgres_service=memory_pg_service)
    return repo


class TestPostgresService:
    def test_init_db_and_connection(self, memory_pg_service):
        assert memory_pg_service.is_configured() is True
        conn = memory_pg_service.check_connection()
        assert conn["accessible"] is True
        assert conn["configured"] is True
        assert conn["dialect"] == "sqlite"

    def test_create_and_get_user(self, memory_pg_service):
        user, err = memory_pg_service.create_user(
            user_id="U-101",
            name="Alice Smith",
            email="alice@example.com",
            password_hash="hashed_pw_123"
        )
        assert err is None
        assert user["user_id"] == "U-101"
        assert user["email"] == "alice@example.com"

        # Lookup by ID
        fetched_id = memory_pg_service.get_user_by_id("U-101")
        assert fetched_id is not None
        assert fetched_id["name"] == "Alice Smith"

        # Lookup by Email (case insensitive)
        fetched_email = memory_pg_service.get_user_by_email("ALICE@example.com")
        assert fetched_email is not None
        assert fetched_email["user_id"] == "U-101"

    def test_duplicate_user_email_rejection(self, memory_pg_service):
        memory_pg_service.create_user(
            user_id="U-101",
            name="Alice Smith",
            email="alice@example.com",
            password_hash="pw1"
        )
        # Attempt to insert same email with different user_id
        _, err = memory_pg_service.create_user(
            user_id="U-102",
            name="Alice Duplicate",
            email="alice@example.com",
            password_hash="pw2"
        )
        assert err is not None
        assert "already exists" in err

    def test_insert_and_get_document(self, memory_pg_service):
        # Create user first
        memory_pg_service.create_user(
            user_id="U-101",
            name="Alice",
            email="alice@example.com",
            password_hash="pw"
        )

        doc_data = {
            "doc_id": "DOC-9001",
            "user_id": "U-101",
            "title": "Cloud Computing Thesis",
            "author": "Alice",
            "description": "Supabase PostgreSQL architecture analysis.",
            "filename": "DOC-9001_Cloud_Computing_Thesis.pdf",
            "storage_path": "documents/DOC-9001.pdf",
            "storage_bucket": "pdf-documents",
            "storage_type": "supabase_and_local",
            "file_size": "150 KB",
            "size_bytes": 153600,
            "created_at": "2026-11-17T12:00:00Z"
        }

        res = memory_pg_service.insert_document(doc_data)
        assert res["success"] is True

        # Fetch document
        doc = memory_pg_service.get_document_by_id("DOC-9001")
        assert doc is not None
        assert doc["title"] == "Cloud Computing Thesis"
        assert doc["storage_type"] == "supabase_and_local"
        assert doc["file_size"] == "150 KB"

    def test_list_documents_filtering_and_sorting(self, memory_pg_service):
        # Create users
        memory_pg_service.create_user("U-101", "Alice", "alice@example.com", "pw")
        memory_pg_service.create_user("U-102", "Bob", "bob@example.com", "pw")

        # Insert docs
        memory_pg_service.insert_document({
            "doc_id": "DOC-A",
            "user_id": "U-101",
            "title": "Alpha Document",
            "author": "Alice",
            "size_bytes": 1000,
            "file_size": "1 KB",
            "created_at": "2026-11-15T10:00:00Z"
        })
        memory_pg_service.insert_document({
            "doc_id": "DOC-B",
            "user_id": "U-101",
            "title": "Beta Document",
            "author": "Alice",
            "size_bytes": 5000,
            "file_size": "5 KB",
            "created_at": "2026-11-16T10:00:00Z"
        })
        memory_pg_service.insert_document({
            "doc_id": "DOC-C",
            "user_id": "U-102",
            "title": "Gamma Document",
            "author": "Bob",
            "size_bytes": 2000,
            "file_size": "2 KB",
            "created_at": "2026-11-17T10:00:00Z"
        })

        # Filter by user U-101
        items = memory_pg_service.list_documents(user_id="U-101")
        assert len(items) == 2
        assert {item["doc_id"] for item in items} == {"DOC-A", "DOC-B"}

        # Search query
        items = memory_pg_service.list_documents(user_id="U-101", search="Alpha")
        assert len(items) == 1
        assert items[0]["doc_id"] == "DOC-A"

        # Sort by size descending
        items = memory_pg_service.list_documents(user_id="U-101", sort_by="size", order="desc")
        assert items[0]["doc_id"] == "DOC-B"
        assert items[1]["doc_id"] == "DOC-A"

    def test_delete_document(self, memory_pg_service):
        memory_pg_service.create_user("U-101", "Alice", "alice@example.com", "pw")
        memory_pg_service.insert_document({
            "doc_id": "DOC-DEL",
            "user_id": "U-101",
            "title": "To Delete",
            "author": "Alice",
            "size_bytes": 100
        })

        res = memory_pg_service.delete_document("DOC-DEL")
        assert res is True

        doc = memory_pg_service.get_document_by_id("DOC-DEL")
        assert doc is None

    def test_sql_injection_safety(self, memory_pg_service):
        """Verify parameterized queries handle SQL injection strings safely."""
        memory_pg_service.create_user("U-101", "Alice", "alice@example.com", "pw")
        evil_title = "Report'; DROP TABLE documents; --"
        memory_pg_service.insert_document({
            "doc_id": "DOC-SAFE",
            "user_id": "U-101",
            "title": evil_title,
            "author": "Alice",
            "size_bytes": 100
        })

        # The table should still exist and document should be stored with literal SQL injection string
        doc = memory_pg_service.get_document_by_id("DOC-SAFE")
        assert doc is not None
        assert doc["title"] == evil_title

        # Search with SQL injection payload
        items = memory_pg_service.list_documents(search="' OR '1'='1")
        assert isinstance(items, list)


class TestAuthServiceWithPostgres:
    def test_register_and_authenticate(self, memory_auth_service):
        user, err = memory_auth_service.register_user(
            name="Kavya",
            email="kavya@test.edu",
            password="SecurePassword123"
        )
        assert err is None
        assert user is not None
        assert user.email == "kavya@test.edu"

        # Duplicate register should fail
        _, dup_err = memory_auth_service.register_user(
            name="Kavya Dup",
            email="kavya@test.edu",
            password="SecurePassword123"
        )
        assert dup_err is not None
        assert "already exists" in dup_err

        # Successful authenticate
        auth_user, auth_err = memory_auth_service.authenticate_user("kavya@test.edu", "SecurePassword123")
        assert auth_err is None
        assert auth_user is not None
        assert auth_user.user_id == user.user_id

        # Bad password
        bad_user, bad_err = memory_auth_service.authenticate_user("kavya@test.edu", "WrongPassword999")
        assert bad_user is None
        assert "Invalid" in bad_err


class TestDocumentRepositoryWithPostgres:
    def test_repository_orchestration_postgres_priority(self, memory_doc_repo, memory_pg_service):
        memory_pg_service.create_user("U-999", "Tester", "tester@test.com", "pw")

        doc = {
            "doc_id": "DOC-REPO-1",
            "user_id": "U-999",
            "title": "Postgres Priority Test",
            "author": "Tester",
            "size_bytes": 2048,
            "file_size": "2 KB",
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        saved = memory_doc_repo.add(doc)
        assert saved["doc_id"] == "DOC-REPO-1"

        # List all
        items = memory_doc_repo.list_all(user_id="U-999")
        assert len(items) == 1
        assert items[0]["title"] == "Postgres Priority Test"

        # Get by ID
        fetched = memory_doc_repo.get_by_id("DOC-REPO-1")
        assert fetched is not None
        assert fetched["doc_id"] == "DOC-REPO-1"

        # Statistics
        stats = memory_doc_repo.get_statistics(user_id="U-999")
        assert stats["total_generated"] == 1
        assert stats["total_bytes"] == 2048
        assert "PostgreSQL" in stats["database_status"]

        # Delete
        deleted = memory_doc_repo.delete("DOC-REPO-1")
        assert deleted is True
        assert memory_doc_repo.get_by_id("DOC-REPO-1") is None
