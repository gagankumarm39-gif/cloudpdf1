# Cloud-Based PDF Generation System

A cloud-native web application designed to allow users to input document information, compile publication-quality PDFs via ReportLab, archive them in AWS cloud storage (Amazon S3), index their metadata (Amazon DynamoDB), and securely access and download them from anywhere.

---

## Project Objectives
- **Centralized Document Studio**: Eliminates desktop dependencies by generating documents directly in the cloud.
- **High-Durability Cloud Storage**: Leverages AWS S3 for binary PDF objects with standard 99.999999999% durability.
- **Fast NoSQL Metadata Indexing**: Indexes document titles, author details, generation timestamps, and S3 object keys using Amazon DynamoDB.
- **Scalable Deployment**: Architected for Amazon EC2 hosting with IAM role-based least-privilege security.

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Frontend** | HTML5, CSS3 (Modern Blue/White responsive theme), Vanilla JavaScript |
| **Backend** | Python 3.12+, Flask 3.0 |
| **WSGI Server** | Gunicorn 22.0 |
| **PDF Generation Engine** | ReportLab 4.2 |
| **Cloud Storage** | Supabase Storage (Free Tier) with Local Disk Fallback & S3 Compatibility |
| **Database** | Supabase PostgreSQL (SQLAlchemy) with DynamoDB & Local JSON Fallback |
| **Cloud Hosting** | Render Free Web Service (or Amazon EC2) |
| **Security & Auth** | Flask-Login, bcrypt, Flask-WTF CSRF, HTTPS, Supabase RLS |

---

## Milestone Roadmap

- [x] **Milestone 1 - Project Foundation and UI**
  - Professional project architecture and clean directory structure.
  - Modern, responsive blue-and-white dashboard and studio UI.
  - Interactive document creation form, live character counter, and preset templates.
  - Placeholder metrics (Total Documents, Cloud Storage Status, Storage Consumed).
  - PDF history table with dynamic client-side update capabilities.
  - Flask application with `/` homepage and `/api/health` monitoring endpoint.
  - Zero cloud credentials required for local execution.
- [x] **Milestone 2 - Actual PDF Generation Engine (ReportLab)**
  - Modular `PDFGeneratorService` utilizing ReportLab Flowables.
  - Running headers, rules, and dynamic two-pass `NumberedCanvas` ("Page X of Y").
  - Multi-page document flows, table metadata card, and justified paragraphs.
  - Storage abstraction `StorageService` for safe filename sanitization and S3 decoupling.
  - `POST /api/generate-pdf` with instant binary browser download and JSON mode.
  - `GET /api/download-pdf/<filename>` for catalog download.
  - Automated test suite with 7 pytest test cases.
- [x] **Milestone 3 – PDF Preview and Document Management**
  - Inline browser PDF preview modal via `GET /api/documents/<id>/preview` (non-forcing download).
  - Search filter with live debounce (by title, author, or Doc ID).
  - Dynamic client-side and server-side sorting (newest, oldest, title A-Z, size).
  - Safe document deletion with confirmation dialog (`DELETE /api/documents/<id>`).
  - `DocumentRepository` repository pattern with local JSON persistence, pre-architected for DynamoDB.
  - Real-time dashboard statistics (total generated, storage consumed).
  - Comprehensive automated test suite expanded to 14 passing tests.
- [x] **Milestone 4 – Amazon S3 Cloud Storage Integration**
  - Python Boto3 integration with standard AWS credential provider chain (IAM roles, profiles, env vars).
  - Dedicated `S3Service` with upload, download stream, preview/download presigned URLs, and head/delete operations.
  - Hybrid `StorageService` saving local backups and uploading to private Amazon S3 with safe keys.
  - Secure short-lived presigned URLs for inline browser viewing and attachment downloads.
  - Safe local fallback when S3 is unconfigured (zero AWS credential barrier for development).
  - Fully mocked automated test suite using Moto (20 passing tests).
- [x] **Milestone 5 – Amazon DynamoDB Integration**
  - Dedicated `DynamoDBService` for document metadata indexation (Table: `CloudPDFDocuments`, Partition Key: `doc_id`).
  - 4-step generation workflow: ReportLab compilation → S3 upload → DynamoDB insertion → Client delivery.
  - Fault tolerance & partial failure rollback (cleans up uploaded S3 objects if DynamoDB fails).
  - Search, sort, retrieve, and delete coordinated across DynamoDB and S3.
  - Local development fallback without credentials preserved.
  - Comprehensive Moto-mocked test suite (24 passing tests).
- [x] **Milestone 6 – User Authentication and Security**
  - Dedicated `AuthService` with secure bcrypt salted password hashing (work factor 12).
  - User registration with RFC email validation, password strength verification, and duplicate check.
  - User login & session management via `Flask-Login` with HTTP-only, SameSite cookies.
  - CSRF token protection via `Flask-WTF` (`CSRFProtect`).
  - Amazon DynamoDB `CloudPDFUsers` table with Partition Key `user_id` and Global Secondary Index `EmailIndex`.
  - Multi-user document isolation: documents indexed by `user_id` (`UserDocIndex` GSI); cross-user viewing, previewing, downloading, or deletion is strictly blocked (HTTP 403 Forbidden).
  - Responsive authentication pages (`/login` and `/register`) adhering to the clean blue-and-white theme.
  - Local JSON storage fallback for users (`storage/users_metadata.json`) with pre-seeded demo account.
  - 30 passing automated tests covering unit, integration, and security layers.
- [x] **Milestone 7 – Amazon EC2 Cloud Deployment & Production Configuration**
  - Production WSGI serving configured with Gunicorn (`gunicorn_config.py`).
  - Automated systemd service definition (`deploy/cloudpdf.service`) with auto-start on boot and process recovery.
  - Nginx reverse proxy configuration (`deploy/nginx.conf`) with direct static asset handling, request size limits, and security headers.
  - Least-privilege IAM policy definition (`deploy/iam_policy.json`) for EC2 Instance Profiles without hardcoded credentials.
  - EC2 Cloud-Init bootstrap user data script (`deploy/ec2_userdata.sh`).
  - AWS Infrastructure verification script (`deploy/setup_aws_resources.py`) for S3 Block Public Access and DynamoDB GSIs.
  - Production health check probe (`/api/health`) reporting active S3 and DynamoDB connectivity status.
  - Complete operational runbook: [AWS_DEPLOYMENT.md](file:///c:/Users/Kavya%20M/OneDrive/Desktop/cloudpdfgenerator/AWS_DEPLOYMENT.md).
  - 35 automated unit, integration, and production configuration tests passing.
- [x] **Milestone 8 – Supabase Storage Migration**
  - Migrated primary cloud PDF binary storage from Amazon S3 to Supabase Storage using the official Supabase Python SDK.
  - Implemented `SupabaseStorageService` supporting secure uploads, direct binary downloads, signed preview & download URLs, and object deletion.
  - Strictly secured credentials via backend environment variables (`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_BUCKET`). Zero credentials exposed to frontend JavaScript.
  - User-isolated storage paths (`{user_id}/{doc_id}_{filename}.pdf`) and comprehensive path traversal sanitization.
  - Private Supabase Storage bucket policy guidelines and RLS protection.
  - Hybrid storage abstraction (`StorageService`) preserving local disk backup and S3 backward compatibility.
  - Partial failure recovery: rolls back uploaded Supabase document if database metadata insertion fails.
  - Full automated test suite expanded to 44 passing tests using mocked Supabase and Moto cloud resources.
  - Complete deployment and configuration documentation in [DEPLOYMENT.md](DEPLOYMENT.md).
- [x] **Milestone 9 – Supabase PostgreSQL Database Integration**
  - Migrated primary metadata and user authentication database from Amazon DynamoDB to **Supabase PostgreSQL**.
  - Implemented `PostgresService` (`services/postgres_service.py`) using SQLAlchemy with connection pooling (`pool_pre_ping=True`), scoped sessions, and parameterized queries for full SQL injection prevention.
  - Relational database schema with declarative models:
    - `users`: `user_id` (PK), `name`, `email` (Unique, indexed), `password_hash`, `created_at`, `is_active`.
    - `documents`: `doc_id` (PK), `user_id` (FK -> `users.user_id` with `ON DELETE CASCADE`), `title`, `author`, `description`, `filename`, `storage_path`, `storage_bucket`, `storage_type`, `file_size`, `size_bytes`, `content_type`, `status`, `created_at` (indexed), `s3_key`.
    - Composite index `idx_docs_user_created` for optimal user-scoped timeline queries.
  - Seamless fallback architecture: `PostgresService` (Priority) → `DynamoDBService` (M5-M7 compatibility) → Local JSON files (offline development).
  - Production migration utility (`scripts/migrate_dynamo_to_postgres.py`) to copy existing DynamoDB and local JSON data into PostgreSQL without destructive drops.
  - Updated `/api/health` monitoring endpoint reporting live PostgreSQL connectivity (`dialect`, `database`, `accessible`).
  - Automated test suite expanded to **53 passing tests**, including comprehensive offline tests (`tests/test_postgres_service.py`) with in-memory SQLite and mock engines.
- [x] **Milestone 10 – Complete Cloud Deployment Using Render**
  - Render Free Web Service deployment configuration (`Procfile`, `runtime.txt` [Python 3.12.7], `render.yaml`).
  - Automated cryptographic `SECRET_KEY` generation via Python `secrets.token_hex(32)`.
  - Production WSGI configuration via Gunicorn supporting dynamic cloud `$PORT`, worker tuning (2 workers for 512MB RAM cap), and 120s timeout for ReportLab compilation.
  - Production security enhancements: Secure HTTPS cookies (`SESSION_COOKIE_SECURE`), HTTPOnly, SameSite, CSRF protection, and debug mode suppression.
  - Cloud database connection string support for Supabase PgBouncer pooler (`aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres`).
  - Step-by-step deployment guide with zero-cost free-tier restrictions and sleep-cycle documentation.
- [x] **Milestone 11 – Complete Integration Testing and Security Validation**
  - Comprehensive end-to-end integration and security audit suite (`tests/test_milestone11_validation.py`).
  - Multi-user isolation verification: validated that User B receives HTTP 403 Forbidden when attempting to view, download, preview, or delete User A's private documents.
  - Hardened storage path sanitization preventing path traversal (`../`) and unauthorized directory traversal.
  - Parameterized ORM queries verified against SQL injection payloads.
  - Fresh 256-bit cryptographic `SECRET_KEY` generated safely via Python `secrets.token_hex(32)` directly into `.env` without printing secrets in reports or chat.
  - Dedicated security documentation created in [SECURITY.md](SECURITY.md).
  - All **58 automated tests** passing cleanly with 100% offline test coverage.
- [x] **Milestone 12 – Final Documentation & Project Completion** *(Completed)*
  - Academic Project Report completed ([PROJECT_REPORT.md](PROJECT_REPORT.md)) with complete IEEE-style sections.
  - System Architecture document completed ([SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)) with Mermaid diagrams.
  - Relational Database Documentation completed ([DATABASE_DOCUMENTATION.md](DATABASE_DOCUMENTATION.md)) with DDL, ER diagram, and query patterns.
  - REST API Documentation completed ([API_DOCUMENTATION.md](API_DOCUMENTATION.md)) with endpoint schemas, request/response models, and status codes.
  - User Guide completed ([USER_GUIDE.md](USER_GUIDE.md)) with visual workflows and operational guides.
  - Testing & QA Report completed ([TESTING_REPORT.md](TESTING_REPORT.md)) summarizing all 58 automated test cases and performance benchmarks.
  - Production security audit completed; verified zero exposed credentials and safe `.env` exclusion in `.gitignore`.

---

## Directory Structure

```
cloudpdfgenerator/
├── app.py                      # Flask backend, auth routes, and secure API endpoints
├── Procfile                    # Render Web Service process definition
├── runtime.txt                 # Python runtime version pin (Python 3.12.7)
├── render.yaml                 # Infrastructure-as-code Blueprint for Render
├── gunicorn_config.py          # Production Gunicorn WSGI server configuration
├── AWS_DEPLOYMENT.md           # AWS EC2 production deployment runbook
├── DEPLOYMENT.md               # Complete Render + Supabase deployment guide
├── SECURITY.md                 # Security architecture, threat model & authorization policy
├── PROJECT_REPORT.md           # Detailed academic project report
├── SYSTEM_ARCHITECTURE.md      # System architecture & component interaction diagrams
├── DATABASE_DOCUMENTATION.md   # PostgreSQL schema, ER diagram, and query patterns
├── API_DOCUMENTATION.md        # Complete REST API reference and schemas
├── USER_GUIDE.md               # End-user visual manual and operational guide
├── TESTING_REPORT.md           # Comprehensive test execution and QA benchmarks
├── requirements.txt            # Python dependencies (Flask, ReportLab, SQLAlchemy, etc.)
├── .env.example                # Example environment variables for production
├── .gitignore                  # Git exclusion rules (.env, venv, caches, PDFs)
├── README.md                   # Project documentation and architecture details
├── deploy/                     # AWS EC2 systemd & Nginx configs (Milestone 7)
├── services/                   # Modular business logic services
│   ├── auth_service.py         # User registration, bcrypt hashing, accounts
│   ├── pdf_service.py          # ReportLab rendering engine & NumberedCanvas
│   ├── postgres_service.py     # Supabase PostgreSQL relational database service (SQLAlchemy)
│   ├── s3_service.py           # Amazon S3 cloud storage service & presigned URLs
│   ├── supabase_storage_service.py # Supabase Storage service & signed URLs
│   ├── dynamodb_service.py     # Amazon DynamoDB document metadata service
│   ├── document_repository.py  # Repository abstraction coordinating Postgres, DynamoDB & local fallback
│   └── storage_service.py      # Dual-tier storage (Supabase / S3 + local filesystem)
├── scripts/                    # Maintenance & migration scripts
│   └── migrate_dynamo_to_postgres.py # Copies DynamoDB/JSON records to PostgreSQL
├── storage/                    # Local storage fallback
├── templates/                  # Frontend HTML templates (index, login, register)
├── static/                     # CSS stylesheets & client JavaScript
└── tests/                      # 58 automated tests across all milestones
```

---

## Getting Started (Local Setup)

### 1. Prerequisites
- Python 3.10+ installed on your machine.
- Git (optional).

### 2. Install Dependencies
Open your terminal in the project root directory and run:
```bash
pip install -r requirements.txt
```

### 3. Run the Application
Start the Flask development server:
```bash
python app.py
```

### 4. Open in Browser & Demo Account
Navigate to:
- **Dashboard UI**: [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Sign In Page**: [http://127.0.0.1:5000/login](http://127.0.0.1:5000/login)
- **Register Account**: [http://127.0.0.1:5000/register](http://127.0.0.1:5000/register)
- **Health-Check API**: [http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health)

**Pre-seeded Demo Account for Testing**:
- **Email**: `kavya@cloudpdf.edu`
- **Password**: `Password123`

### 5. Running the Automated Test Suite
Run all 58 automated tests across all milestones (100% offline, zero cloud charges):
```bash
python -m pytest tests/ -v
```

### 6. Production EC2 Deployment
For complete step-by-step instructions on deploying the application to an Amazon EC2 Linux instance with Gunicorn, systemd, Nginx, and an IAM Instance Role, please refer to:
👉 **[AWS EC2 Production Deployment Guide (AWS_DEPLOYMENT.md)](AWS_DEPLOYMENT.md)**


