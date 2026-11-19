"""
Supabase PostgreSQL Database Service
Cloud-Based PDF Generation System - Milestone 9

Provides:
- PostgreSQL connection and pool management via SQLAlchemy
- Declarative models: UserRecord and DocumentRecord
- Full CRUD for users (registration, lookup by ID/email, authentication helper)
- Full CRUD for document metadata (insert, list_by_user, search, sort, delete, stats)
- Safe parameterized queries / ORM protection against SQL injection
- Foreign key constraints (documents.user_id -> users.user_id ON DELETE CASCADE)
- Database connection health checking
- Fallback indicator when DATABASE_URL is not configured
"""
import os
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    text,
    desc,
    asc,
    or_
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session, relationship
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

logger = logging.getLogger(__name__)

Base = declarative_base()


class UserRecord(Base):
    """
    SQLAlchemy model for application users.
    Maps to 'users' table in PostgreSQL.
    """
    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationship to user documents
    documents = relationship("DocumentRecord", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "is_active": self.is_active
        }


class DocumentRecord(Base):
    """
    SQLAlchemy model for PDF document metadata.
    Maps to 'documents' table in PostgreSQL.
    """
    __tablename__ = "documents"

    doc_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    author = Column(String(128), nullable=False)
    description = Column(String(1000), default="", nullable=True)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=False)  # Supabase Storage path ({user_id}/{filename})
    storage_bucket = Column(String(128), default="pdf-documents", nullable=False)
    storage_type = Column(String(64), default="supabase_and_local", nullable=False)
    file_size = Column(String(32), default="0 KB", nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
    content_type = Column(String(64), default="application/pdf", nullable=False)
    status = Column(String(32), default="Ready", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Optional legacy S3 compatibility key
    s3_key = Column(String(500), nullable=True)

    # Relationship to User
    user = relationship("UserRecord", back_populates="documents")

    # Composite index for user document queries ordered by creation date
    __table_args__ = (
        Index("idx_docs_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.doc_id,
            "doc_id": self.doc_id,
            "user_id": self.user_id,
            "title": self.title,
            "author": self.author,
            "description": self.description or "",
            "filename": self.filename,
            "storage_path": self.storage_path,
            "s3_key": self.s3_key or self.storage_path,
            "storage_bucket": self.storage_bucket,
            "supabase_bucket": self.storage_bucket,
            "storage_type": self.storage_type,
            "size": self.file_size,
            "file_size": self.file_size,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "status": self.status,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "cloud_synced": True if "supabase" in self.storage_type or "s3" in self.storage_type else False,
            "supabase_synced": True if "supabase" in self.storage_type else False,
            "s3_synced": True if "s3" in self.storage_type else False
        }


def normalize_database_url(url: str) -> str:
    """
    Ensure SQLAlchemy uses the psycopg2 driver for postgresql URLs.
    Supabase connection strings often begin with 'postgres://' which
    SQLAlchemy 1.4+ requires to be 'postgresql://' or 'postgresql+psycopg2://'.
    Explicitly use 'postgresql+psycopg2://' so that the installed psycopg2 driver
    is consistently selected without requiring psycopg (v3).
    """
    if not url:
        return ""
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


class PostgresService:
    """
    Service managing PostgreSQL database connections, ORM models,
    and queries for Supabase PostgreSQL.
    """
    def __init__(self, database_url: Optional[str] = None):
        raw_url = database_url if database_url is not None else os.getenv("DATABASE_URL", "")
        self.database_url = normalize_database_url(raw_url)
        self._engine = None
        self._session_factory = None
        self._session = None

        if self.database_url:
            self._init_engine()

    def is_configured(self) -> bool:
        """Returns True if DATABASE_URL is configured."""
        return bool(self.database_url)

    def _init_engine(self):
        """Initializes SQLAlchemy Engine and scoped session factory."""
        try:
            # Configure engine with connection pooling and pre-ping to handle drops gracefully
            engine_kwargs = {"pool_pre_ping": True}
            # pool_size and max_overflow are only valid for QueuePool (Postgres/MySQL), not SQLite SingletonThreadPool
            if "sqlite" not in self.database_url:
                engine_kwargs.update({
                    "pool_size": 5,
                    "max_overflow": 10,
                    "pool_recycle": 300,
                    "connect_args": {"connect_timeout": 5}
                })
            self._engine = create_engine(self.database_url, **engine_kwargs)
            self._session_factory = sessionmaker(bind=self._engine)
            self._session = scoped_session(self._session_factory)
        except Exception as e:
            logger.error(f"Error initializing Postgres engine: {e}")
            self._engine = None
            self._session = None

    def get_session(self):
        """Returns an active SQLAlchemy session."""
        if self._session is None and self.is_configured():
            self._init_engine()
        if self._session:
            return self._session()
        raise RuntimeError("Postgres database is not configured. DATABASE_URL is required.")

    def init_db(self) -> Dict[str, Any]:
        """
        Creates tables in PostgreSQL schema if they do not already exist.
        Safe and idempotent.
        """
        if not self.is_configured() or not self._engine:
            return {"success": False, "error": "POSTGRES_NOT_CONFIGURED", "message": "DATABASE_URL is not set"}
        try:
            Base.metadata.create_all(self._engine)
            return {"success": True, "message": "PostgreSQL tables created or verified successfully."}
        except Exception as e:
            logger.error(f"Failed to create PostgreSQL tables: {e}")
            return {"success": False, "error": str(e)}

    def check_connection(self) -> Dict[str, Any]:
        """
        Actively checks connection to Supabase PostgreSQL using a lightweight SELECT 1.
        Returns detailed status for health check probes.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "accessible": False,
                "status": "unconfigured",
                "database": "Supabase PostgreSQL"
            }
        try:
            if self._engine is None:
                self._init_engine()
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            dialect_name = self._engine.dialect.name if self._engine else "unknown"
            return {
                "configured": True,
                "accessible": True,
                "status": "connected",
                "database": "Supabase PostgreSQL",
                "dialect": dialect_name
            }
        except Exception as e:
            logger.warning(f"PostgreSQL health check probe failed: {e}")
            return {
                "configured": True,
                "accessible": False,
                "status": "unreachable",
                "database": "Supabase PostgreSQL",
                "error": str(e)
            }

    # =========================================================================
    # User Operations
    # =========================================================================

    def create_user(
        self,
        user_id: str,
        name: str,
        email: str,
        password_hash: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Creates a new user record in PostgreSQL.
        Enforces email uniqueness constraint.
        """
        if not self.is_configured():
            return None, "DATABASE_NOT_CONFIGURED"

        session = self.get_session()
        try:
            user = UserRecord(
                user_id=user_id,
                name=name.strip(),
                email=email.strip().lower(),
                password_hash=password_hash,
                created_at=datetime.utcnow(),
                is_active=True
            )
            session.add(user)
            session.commit()
            return user.to_dict(), None
        except IntegrityError:
            session.rollback()
            return None, "An account with this email address already exists."
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating user in PostgreSQL: {e}")
            return None, str(e)
        finally:
            session.close()

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user record by user_id."""
        if not self.is_configured():
            return None
        session = self.get_session()
        try:
            user = session.query(UserRecord).filter_by(user_id=user_id).first()
            if user:
                data = user.to_dict()
                data["password_hash"] = user.password_hash
                return data
            return None
        finally:
            session.close()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Retrieve user record by email."""
        if not self.is_configured():
            return None
        session = self.get_session()
        try:
            email_clean = email.strip().lower()
            user = session.query(UserRecord).filter_by(email=email_clean).first()
            if user:
                data = user.to_dict()
                data["password_hash"] = user.password_hash
                return data
            return None
        finally:
            session.close()

    # =========================================================================
    # Document Operations
    # =========================================================================

    def insert_document(self, doc_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert document metadata record into PostgreSQL.
        """
        if not self.is_configured():
            return {"success": False, "error": "DATABASE_NOT_CONFIGURED"}

        session = self.get_session()
        try:
            doc_id = doc_data.get("doc_id") or doc_data.get("id")
            user_id = doc_data.get("user_id") or "USER-DEMO-001"

            # Parse created_at
            created_at_raw = doc_data.get("created_at")
            if isinstance(created_at_raw, str):
                try:
                    created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                except Exception:
                    created_at = datetime.utcnow()
            elif isinstance(created_at_raw, datetime):
                created_at = created_at_raw
            else:
                created_at = datetime.utcnow()

            # Ensure user exists for foreign key constraint
            user = session.query(UserRecord).filter_by(user_id=user_id).first()
            if not user:
                # Create a placeholder user record so FK holds
                author_name = doc_data.get("author") or "Cloud User"
                placeholder_user = UserRecord(
                    user_id=user_id,
                    name=author_name,
                    email=f"{user_id.lower()}@cloudpdf.edu",
                    password_hash="",
                    created_at=datetime.utcnow(),
                    is_active=True
                )
                session.add(placeholder_user)
                session.flush()

            document = DocumentRecord(
                doc_id=doc_id,
                user_id=user_id,
                title=doc_data.get("title", "Untitled Document"),
                author=doc_data.get("author", "Anonymous"),
                description=doc_data.get("description", ""),
                filename=doc_data.get("filename", f"{doc_id}.pdf"),
                storage_path=doc_data.get("storage_path") or doc_data.get("s3_key") or f"{user_id}/{doc_id}.pdf",
                storage_bucket=doc_data.get("storage_bucket") or doc_data.get("supabase_bucket") or "pdf-documents",
                storage_type=doc_data.get("storage_type", "supabase_and_local"),
                file_size=doc_data.get("file_size") or doc_data.get("size", "0 KB"),
                size_bytes=int(doc_data.get("size_bytes", 0)),
                content_type=doc_data.get("content_type", "application/pdf"),
                status=doc_data.get("status", "Ready"),
                created_at=created_at,
                s3_key=doc_data.get("s3_key")
            )
            session.merge(document)
            session.commit()
            return {"success": True, "message": "Document metadata stored in PostgreSQL.", "document": document.to_dict()}
        except Exception as e:
            session.rollback()
            logger.error(f"Error inserting document in PostgreSQL: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve document metadata by doc_id."""
        if not self.is_configured():
            return None
        session = self.get_session()
        try:
            doc = session.query(DocumentRecord).filter_by(doc_id=doc_id).first()
            return doc.to_dict() if doc else None
        finally:
            session.close()

    def list_documents(
        self,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "date",
        order: str = "desc"
    ) -> List[Dict[str, Any]]:
        """
        List documents with search, sorting, and user-scoping.
        Uses parameterized filters to prevent SQL injection.
        """
        if not self.is_configured():
            return []

        session = self.get_session()
        try:
            query = session.query(DocumentRecord)

            # User filter
            if user_id:
                query = query.filter(DocumentRecord.user_id == user_id)

            # Search filter (title, author, or doc_id)
            if search:
                term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        DocumentRecord.title.ilike(term),
                        DocumentRecord.author.ilike(term),
                        DocumentRecord.doc_id.ilike(term)
                    )
                )

            # Sorting
            is_desc = order.lower() == "desc"
            if sort_by == "title":
                order_col = desc(DocumentRecord.title) if is_desc else asc(DocumentRecord.title)
            elif sort_by == "size":
                order_col = desc(DocumentRecord.size_bytes) if is_desc else asc(DocumentRecord.size_bytes)
            else:  # date
                order_col = desc(DocumentRecord.created_at) if is_desc else asc(DocumentRecord.created_at)

            query = query.order_by(order_col)
            results = query.all()
            return [doc.to_dict() for doc in results]
        except Exception as e:
            logger.error(f"Error querying documents from PostgreSQL: {e}")
            return []
        finally:
            session.close()

    def delete_document(self, doc_id: str) -> bool:
        """Delete document record from PostgreSQL."""
        if not self.is_configured():
            return False
        session = self.get_session()
        try:
            doc = session.query(DocumentRecord).filter_by(doc_id=doc_id).first()
            if not doc:
                return False
            session.delete(doc)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting document from PostgreSQL: {e}")
            return False
        finally:
            session.close()

    def get_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Compute total documents and total storage consumption."""
        if not self.is_configured():
            return {"total_documents": 0, "total_size_bytes": 0, "total_size_formatted": "0 KB"}

        session = self.get_session()
        try:
            query = session.query(DocumentRecord)
            if user_id:
                query = query.filter(DocumentRecord.user_id == user_id)
            docs = query.all()

            total_docs = len(docs)
            total_bytes = sum(doc.size_bytes or 0 for doc in docs)

            if total_bytes < 1024 * 1024:
                formatted = f"{round(total_bytes / 1024, 1)} KB"
            else:
                formatted = f"{round(total_bytes / (1024 * 1024), 2)} MB"

            return {
                "total_documents": total_docs,
                "total_size_bytes": total_bytes,
                "total_size_formatted": formatted
            }
        except Exception as e:
            logger.error(f"Error computing statistics from PostgreSQL: {e}")
            return {"total_documents": 0, "total_size_bytes": 0, "total_size_formatted": "0 KB"}
        finally:
            session.close()
