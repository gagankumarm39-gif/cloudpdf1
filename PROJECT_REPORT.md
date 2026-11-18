# Academic Project Report: Cloud-Based PDF Generation System

## Course Project: Cloud Computing & Web Systems Engineering

---

## Abstract

Desktop-dependent document compilation frequently encounters platform incompatibility, lack of centralized archival, and cumbersome manual distribution. This project implements the **Cloud-Based PDF Generation System** ("CloudPDF Studio"), a cloud-native web platform that enables authenticated users to author, compile, archive, and retrieve publication-quality PDF documents entirely in the cloud. Built using **Python Flask**, **ReportLab**, **Supabase Storage**, and **Supabase PostgreSQL**, the system features a 4-step compilation-and-storage pipeline with compensating rollback transactions, multi-user data isolation, bcrypt credential hashing, and parameterized query execution to prevent SQL injection. The platform is configured for zero-cost deployment on **Render Free Web Service** and **Supabase Free Tier**, delivering enterprise-grade cloud capabilities without financial overhead.

---

## 1. Introduction

With the proliferation of cloud computing, modern software architectures emphasize centralized compute, decoupled storage, and accessible browser interfaces. Document generation remains a crucial business workflow for academic institutions, enterprises, and public services. Traditional systems rely heavily on desktop text processors or local CLI utilities, introducing software dependency issues and fragmented storage. The Cloud-Based PDF Generation System resolves these limitations by centralizing PDF generation on a cloud backend, integrating scalable cloud storage, and providing an interactive web dashboard.

---

## 2. Problem Statement

Existing approaches to document generation face several key challenges:
1. **Desktop Dependencies**: Users must install proprietary software or complex rendering engines locally.
2. **Fragmented Storage**: Generated documents reside on disparate user machines without centralized version control or access logs.
3. **Security Deficits**: Desktop documents lack fine-grained role-based access control, cryptographic password hashing, and user-scoped data boundaries.
4. **Cloud Infrastructure Cost**: Traditional enterprise document pipelines rely on expensive enterprise software licenses or complex paid AWS configurations.

---

## 3. Objectives

The primary objectives of this project are:
- Develop a responsive web studio for authoring structured documents.
- Implement an automated server-side PDF compilation engine using ReportLab Flowables and dynamic page numbering ("Page X of Y").
- Integrate private cloud object storage via Supabase Storage for secure PDF binary archiving.
- Implement a relational database schema using Supabase PostgreSQL to manage user accounts and document metadata.
- Enforce strict multi-user authorization boundaries and cryptographic authentication.
- Establish a zero-cost production deployment on Render Free and Supabase Free tier.

---

## 4. Existing System vs. Proposed System

| Feature | Existing Desktop Systems | Proposed CloudPDF Studio |
|---|---|---|
| **Execution Environment** | Local client machine | Cloud server (Render / Python Flask) |
| **PDF Compilation** | Manual export from desktop office software | Automated programmatic rendering via ReportLab |
| **Document Archival** | Local disk / USB drives | Private cloud storage (Supabase Storage) |
| **Metadata Indexing** | Local file system directories | Relational PostgreSQL with composite indexes |
| **Access Control** | Operating system file permissions | Bcrypt authentication & backend row-level ownership |
| **Document Preview** | External PDF reader software | Inline browser viewer using signed URLs |
| **Cost** | Commercial software licenses | 100% Free Tier compliant ($0/month) |

---

## 5. Technology Review

- **Python Flask**: A lightweight, extensible WSGI web framework providing robust HTTP routing, middleware support, and minimal overhead.
- **ReportLab**: A mature Python library for generating PDF documents programmatically with flowable layouts, custom canvas drawing, and high-precision typography.
- **Supabase Storage**: S3-compatible cloud object storage built on top of AWS infrastructure, offering private buckets, path-based access control, and short-lived signed URLs.
- **Supabase PostgreSQL & SQLAlchemy**: Enterprise-grade relational database coupled with an Object-Relational Mapper that provides connection pooling (PgBouncer) and parameterized queries.
- **Bcrypt**: Adaptive salted cryptographic hashing algorithm resistant to rainbow table and brute-force GPU attacks.
- **Gunicorn**: Production-grade UNIX WSGI HTTP server supporting multi-process concurrency.
- **Render**: Modern cloud application hosting platform offering free-tier web services, automated Git continuous deployment, and free SSL/TLS termination.

---

## 6. Hardware and Software Requirements

### Software Requirements
- **Operating System**: Windows 10/11, macOS, or Linux (Ubuntu 22.04+ / Amazon Linux 2023).
- **Runtime**: Python 3.10+ (pinned to Python 3.12.7 in production).
- **Web Browser**: Any modern browser (Google Chrome, Mozilla Firefox, Microsoft Edge, Safari).
- **Core Libraries**: `Flask==3.0.3`, `reportlab==4.2.0`, `SQLAlchemy==2.0.38`, `psycopg2-binary==2.9.10`, `supabase==2.34.1`, `bcrypt==5.0.0`, `gunicorn==22.0.0`.

### Hardware Requirements (Development & Production)
- **Development**: 4 GB RAM, 2 CPU cores, 500 MB disk space.
- **Production (Render Free Tier)**: 0.1 CPU core, 512 MB RAM, 100 GB monthly bandwidth.

---

## 7. System Architecture & Workflows

The system follows a three-tier decoupled cloud architecture:
1. **Client Tier**: Web browser executing semantic HTML5, CSS3, and JavaScript Fetch API calls.
2. **Application Tier**: Render-hosted Gunicorn WSGI processes running Flask routes and services.
3. **Data Tier**: Decoupled Supabase cloud infrastructure (PostgreSQL database and private object storage bucket).

*(Refer to `SYSTEM_ARCHITECTURE.md` for complete architectural and sequence diagrams).*

---

## 8. Module Description

The project is structured into modular, decoupled service layers:
1. **`PDFGeneratorService` (`services/pdf_service.py`)**: Assembles document Flowables (`Paragraph`, `Spacer`, `Table`), applies custom styling, and invokes `NumberedCanvas` to calculate total pages dynamically.
2. **`StorageService` (`services/storage_service.py`)**: Provides unified storage operations, filename sanitization, and dual-tier sync between cloud storage and local fallback.
3. **`SupabaseStorageService` (`services/supabase_storage_service.py`)**: Interacts with the Supabase Storage API to upload binaries, verify object existence, generate 1-hour signed preview/download URLs, and delete objects.
4. **`PostgresService` (`services/postgres_service.py`)**: Manages the relational database layer, scoped SQLAlchemy sessions, connection pooling, and parameterized queries.
5. **`AuthService` (`services/auth_service.py`)**: Manages account registration, password complexity validation, and bcrypt password hashing.
6. **`DocumentRepository` (`services/document_repository.py`)**: Coordinates metadata persistence across PostgreSQL, DynamoDB, and local JSON files.

---

## 9. Database Design

The PostgreSQL database utilizes two core relational entities:
- **`users`**: Contains `user_id` (PK), `name`, `email` (Unique, indexed), `password_hash`, `created_at`, and `is_active`.
- **`documents`**: Contains `doc_id` (PK), `user_id` (FK referencing `users.user_id` with `ON DELETE CASCADE`), `title`, `author`, `description`, `filename`, `storage_path`, `storage_bucket`, `storage_type`, `file_size`, `size_bytes`, `content_type`, `status`, and `created_at`.
- **Composite Index**: `idx_docs_user_created` on `(user_id, created_at)` optimizes timeline retrieval for authenticated users.

*(Refer to `DATABASE_DOCUMENTATION.md` for detailed entity tables and DDL schema).*

---

## 10. Security Features & Implementation

1. **Authentication Security**:
   - Salted bcrypt password hashing (cost factor 12).
   - Flask-Login session cookies configured with `HttpOnly`, `SameSite=Lax`, and `Secure` (HTTPS).
   - Cryptographically random 256-bit Flask `SECRET_KEY`.
2. **Authorization & Row-Level Isolation**:
   - Backend ownership validation ensures users cannot view, preview, download, or delete documents owned by other users (enforced with HTTP 403 Forbidden).
3. **Storage Security**:
   - Storage bucket `pdf-documents` is strictly private.
   - Files are accessed only via short-lived signed URLs with a 3600-second expiration.
   - Storage path sanitization strips path traversal sequences (`../`).
4. **Injection Prevention**:
   - All database queries use parameterized SQLAlchemy filters, eliminating SQL injection vulnerabilities.
   - Cross-Site Scripting (XSS) is mitigated through Jinja2 auto-escaping in templates.

---

## 11. Testing and Verification

A comprehensive automated test suite consisting of **58 test cases** was developed and executed using `pytest`:
- **Unit & Service Tests**: Validated ReportLab rendering, filename sanitization, bcrypt hashing, and email validation.
- **Database & Storage Tests**: Tested CRUD operations, foreign key cascade deletion, SQL injection resilience, and path traversal protection.
- **Multi-User Security Tests**: Verified cross-user isolation and HTTP 403 enforcement between test accounts.
- **Performance Tests**: Validated that 2-page document compilation latency remains below 0.1 seconds.

**Result**: All 58 tests passed with zero failures.

---

## 12. Deployment Configuration

The application is prepared for continuous deployment on Render Free Web Service:
- **Entry Point**: `app:app` served via Gunicorn (`Procfile`).
- **Runtime Pin**: Python 3.12.7 (`runtime.txt`).
- **Resource Constraints**: 2 Gunicorn sync workers configured to prevent exceeding the 512MB RAM free-tier limit.
- **Health Check**: Automated health monitoring configured at `/api/health`.

---

## 13. Advantages and Limitations

### Advantages
- **Platform Independent**: Accessible from any modern web browser without desktop software.
- **Zero Cost**: Entire stack operates comfortably within free tiers of Render, Supabase, and GitHub.
- **Decoupled Architecture**: Storage, compute, and database can scale independently.
- **High Security**: Ephemeral signed URLs, bcrypt password hashing, and multi-tenant data isolation.

### Limitations
- **Cold Starts**: Render Free Web Services sleep after 15 minutes of inactivity; initial wake-up takes ~30–50 seconds.
- **Storage Cap**: Supabase Free Tier provides 1 GB of storage and 500 MB of database capacity (ample for academic and small-team use, but requires upgrading for high-volume enterprise production).

---

## 14. Future Enhancements

1. **Rich Text & Markdown Editor**: Add Markdown / WYSIWYG authoring tools to allow custom headings, bold text, and embedded tables directly from the browser.
2. **Document Templates**: Implement pre-configured styling templates (e.g. Invoices, Academic Resumes, Certificates).
3. **Collaborative Sharing**: Implement document sharing with specific registered users with read/edit permissions.
4. **Digital Signatures**: Add cryptographic PDF signing (X.509 certificates) for verified document integrity.

---

## 15. Conclusion

The Cloud-Based PDF Generation System demonstrates the practical application of modern cloud architectures, combining Python Flask, ReportLab, Supabase Storage, and PostgreSQL into a robust, secure, and production-ready solution. By decoupling document generation from desktop hardware and centralizing storage in the cloud, the project successfully solves traditional document management challenges while maintaining strict security, multi-user isolation, and zero deployment cost.

---

## 16. References

1. ReportLab Inc., *"ReportLab PDF Generation User Guide"*, Version 4.2, 2024.
2. Pallets Projects, *"Flask Documentation (3.0.x)"*, https://flask.palletsprojects.com/.
3. Supabase Inc., *"Supabase Storage and PostgreSQL Documentation"*, https://supabase.com/docs.
4. Bayer, M., *"SQLAlchemy: The Database Toolkit for Python"*, 2024.
5. OWASP Foundation, *"OWASP Top 10 Web Application Security Risks"*, 2021.
