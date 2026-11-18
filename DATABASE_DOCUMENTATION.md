# Database Documentation: Supabase PostgreSQL Schema & Operations

## Cloud-Based PDF Generation System — Milestone 12

This document provides complete technical specifications for the relational database model powering the **Cloud-Based PDF Generation System**, implemented in Supabase PostgreSQL via SQLAlchemy ORM.

---

## 1. Database Architecture & Technologies

- **Database Engine**: PostgreSQL 15+ (Hosted on Supabase).
- **ORM & Data Layer**: SQLAlchemy 2.0 with Declarative Models.
- **Connection Driver**: `psycopg2-binary`.
- **Connection Pooling**: PgBouncer / Supavisor connection pooler (`pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`, `pool_recycle=300`).
- **Connection URL Format**:
  - Direct connection (Port 5432): `postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres`
  - Transaction Pooler (Port 6543): `postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-1-[REGION].pooler.supabase.com:6543/postgres`
  - Session Pooler (Port 5432): `postgresql://postgres.[PROJECT-REF]:[PASSWORD]@aws-1-[REGION].pooler.supabase.com:5432/postgres`

---

## 2. Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    USERS ||--o{ DOCUMENTS : "owns and creates"
    USERS {
        VARCHAR_64 user_id PK "Unique User Identifier"
        VARCHAR_128 name "User Full Name"
        VARCHAR_255 email UK "Indexed unique email address"
        VARCHAR_255 password_hash "Bcrypt salted hash (cost 12)"
        TIMESTAMP created_at "Account creation timestamp"
        BOOLEAN is_active "Account status flag"
    }
    DOCUMENTS {
        VARCHAR_64 doc_id PK "Unique Document Identifier"
        VARCHAR_64 user_id FK "References USERS(user_id) ON DELETE CASCADE"
        VARCHAR_255 title "Document Title"
        VARCHAR_128 author "Author Name"
        TEXT description "Document Abstract / Description"
        VARCHAR_255 filename "Sanitized PDF Filename"
        VARCHAR_500 storage_path "Supabase Storage Object Path"
        VARCHAR_128 storage_bucket "Storage Bucket (pdf-documents)"
        VARCHAR_64 storage_type "Storage Tier (supabase_and_local)"
        VARCHAR_32 file_size "Formatted size string"
        BIGINT size_bytes "Binary file size in bytes"
        VARCHAR_64 content_type "MIME Type (application/pdf)"
        VARCHAR_32 status "Status (Ready)"
        TIMESTAMP created_at "Creation timestamp"
        VARCHAR_500 s3_key "Legacy S3 compatibility key"
    }
```

---

## 3. Schema DDL Definitions

### 3.1 `users` Table
Stores authenticated user credentials and profile metadata.

```sql
CREATE TABLE users (
    user_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes
CREATE INDEX ix_users_email ON users(email);
```

| Column | Type | Constraints | Description |
|---|---|---|---|
| `user_id` | `VARCHAR(64)` | PRIMARY KEY | Generated prefix ID (`USER-XXXXXXXX`) |
| `name` | `VARCHAR(128)` | NOT NULL | User's full name |
| `email` | `VARCHAR(255)` | UNIQUE, NOT NULL, INDEXED | Normalized lowercase email address |
| `password_hash` | `VARCHAR(255)` | NOT NULL | Salted bcrypt hash string (never plaintext) |
| `created_at` | `TIMESTAMP` | DEFAULT CURRENT_TIMESTAMP | Registration UTC timestamp |
| `is_active` | `BOOLEAN` | DEFAULT TRUE | Account activity status |

### 3.2 `documents` Table
Stores document metadata, cloud storage coordinates, and user ownership linkage.

```sql
CREATE TABLE documents (
    doc_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(128) NOT NULL,
    description TEXT,
    filename VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    storage_bucket VARCHAR(128) DEFAULT 'pdf-documents',
    storage_type VARCHAR(64) DEFAULT 'supabase_and_local',
    file_size VARCHAR(32) NOT NULL,
    size_bytes BIGINT DEFAULT 0,
    content_type VARCHAR(64) DEFAULT 'application/pdf',
    status VARCHAR(32) DEFAULT 'Ready',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    s3_key VARCHAR(500)
);

-- Indexes
CREATE INDEX ix_documents_user_id ON documents(user_id);
CREATE INDEX ix_documents_created_at ON documents(created_at);
CREATE INDEX idx_docs_user_created ON documents(user_id, created_at);
```

| Column | Type | Constraints | Description |
|---|---|---|---|
| `doc_id` | `VARCHAR(64)` | PRIMARY KEY | Generated document ID (`DOC-XXXX`) |
| `user_id` | `VARCHAR(64)` | FOREIGN KEY (`users.user_id`) | Document owner identifier |
| `title` | `VARCHAR(255)` | NOT NULL | Human-readable document title |
| `author` | `VARCHAR(128)` | NOT NULL | Stated author |
| `description` | `TEXT` | NULLABLE | Document summary/abstract |
| `filename` | `VARCHAR(255)` | NOT NULL | Sanitized `.pdf` filename |
| `storage_path` | `VARCHAR(500)` | NOT NULL | Supabase Storage path (`{user_id}/{doc_id}_{filename}`) |
| `storage_bucket`| `VARCHAR(128)` | DEFAULT `'pdf-documents'` | Target bucket |
| `storage_type` | `VARCHAR(64)` | DEFAULT `'supabase_and_local'` | Storage tier tag |
| `file_size` | `VARCHAR(32)` | NOT NULL | Human formatted size (e.g., `245 KB`) |
| `size_bytes` | `BIGINT` | DEFAULT `0` | Exact integer byte count for storage analytics |
| `content_type` | `VARCHAR(64)` | DEFAULT `'application/pdf'` | MIME type |
| `status` | `VARCHAR(32)` | DEFAULT `'Ready'` | Document status flag |
| `created_at` | `TIMESTAMP` | DEFAULT CURRENT_TIMESTAMP | Compilation UTC timestamp |
| `s3_key` | `VARCHAR(500)` | NULLABLE | Compatibility key for AWS S3 coexistence |

---

## 4. Key Relationships & Integrity Constraints

1. **Foreign Key Integrity (`ON DELETE CASCADE`)**:
   - Every document is strictly bound to a valid user account.
   - If an account is deleted, all owned document records are automatically purged via PostgreSQL cascading delete, preventing orphaned metadata.
2. **Composite Query Index (`idx_docs_user_created`)**:
   - Accelerates dashboard history queries (`WHERE user_id = :uid ORDER BY created_at DESC`).
3. **Unique Email Index (`ix_users_email`)**:
   - Enforces unique email registration at the database engine level, rejecting race-condition duplicate account registrations.

---

## 5. Operations & Query Patterns

All queries are executed through SQLAlchemy ORM with automatic parameter binding:

### 5.1 User Registration
```python
# Inserts new user record idempotently
user = UserRecord(user_id=uid, name=name, email=email, password_hash=pw_hash)
session.add(user)
session.commit()
```

### 5.2 Scoped Document Listing & Search
```python
# Parameterized query filtering by user_id and partial search
query = session.query(DocumentRecord).filter(DocumentRecord.user_id == user_id)
if search:
    term = f"%{search.strip()}%"
    query = query.filter(
        or_(
            DocumentRecord.title.ilike(term),
            DocumentRecord.author.ilike(term),
            DocumentRecord.doc_id.ilike(term)
        )
    )
query = query.order_by(desc(DocumentRecord.created_at))
```

### 5.3 Dashboard Analytics
```python
# Aggregate queries scoped to user
records = session.query(DocumentRecord).filter_by(user_id=user_id).all()
total_count = len(records)
total_bytes = sum(doc.size_bytes for doc in records)
```

---

## 6. Migration Utility

The repository includes a non-destructive migration script:
```bash
python scripts/migrate_dynamo_to_postgres.py
```
This script connects to existing DynamoDB tables (`CloudPDFUsers`, `CloudPDFDocuments`) and local JSON backups (`storage/*.json`), transferring all accounts and documents into Supabase PostgreSQL using `session.merge()` (upsert).
