# System Architecture Documentation

## Cloud-Based PDF Generation System — Milestone 12

This document describes the architectural design, component interactions, workflows, and deployment topology of the **Cloud-Based PDF Generation System**.

---

## 1. Overall System Architecture Diagram

```mermaid
graph TD
    Client["Web Browser (Client)\nHTML5 / CSS3 / Vanilla JS"]
    
    subgraph RenderPlatform["Render Cloud Platform (PaaS)"]
        Gunicorn["Gunicorn WSGI Server\n(0.0.0.0:$PORT | 2 Sync Workers)"]
        Flask["Flask Web Application\n(Application & Routing Logic)"]
        AuthModule["AuthService\n(Bcrypt / Flask-Login)"]
        PDFModule["PDFGeneratorService\n(ReportLab Flowables & NumberedCanvas)"]
        RepoModule["DocumentRepository\n(Data Orchestration & Local Fallback)"]
        StorageModule["StorageService\n(Dual-Tier Cloud & Local Sync)"]
    end

    subgraph SupabaseCloud["Supabase Managed Cloud Services"]
        PostgresDB[("Supabase PostgreSQL 15+\n(SQLAlchemy ORM / Pooler)\nTables: users, documents")]
        SupaStorage[("Supabase Storage\nBucket: pdf-documents (Private)\nPath: {user_id}/{doc_id}_{filename}")]
    end

    subgraph LocalDisk["Local Disk Fallback (Dev/Offline)"]
        LocalPDFs["storage/generated_pdfs/"]
        LocalUsers["storage/users_metadata.json"]
        LocalDocs["storage/documents_metadata.json"]
    end

    Client -->|HTTPS / Port 443| Gunicorn
    Gunicorn --> Flask
    Flask --> AuthModule
    Flask --> PDFModule
    Flask --> RepoModule
    Flask --> StorageModule

    AuthModule -->|SQLAlchemy Sessions| PostgresDB
    RepoModule -->|SQLAlchemy Queries| PostgresDB
    StorageModule -->|Official Supabase Python SDK| SupaStorage
    
    AuthModule -.->|Fallback if unconfigured| LocalUsers
    RepoModule -.->|Fallback if unconfigured| LocalDocs
    StorageModule -.->|Fallback if unconfigured| LocalPDFs
```

---

## 2. Component Descriptions

### 2.1 Presentation Layer (Frontend)
- **UI & Layout**: Responsive blue-and-white dashboard built with pure HTML5 and modern CSS3 (no bulky runtime UI frameworks like React/Angular required).
- **Client Scripting (`static/js/main.js`)**:
  - Handles asynchronous document creation requests via Fetch API.
  - Live character count feedback and title sanitization preview.
  - Interactive modal dialogs for inline PDF previewing (`<iframe>`) and document deletion confirmation.
  - Debounced client-side and server-side document search and sorting.

### 2.2 Application Layer (Backend Flask & Gunicorn)
- **WSGI Server (`gunicorn_config.py`)**: Runs Gunicorn with 2 worker processes and a 120-second timeout, tuned specifically for Render Free tier's 512MB RAM cap.
- **Flask Framework (`app.py`)**:
  - Handles routing, session management, CSRF token validation, and error reporting.
  - Exposes production health check monitoring at `/api/health`.

### 2.3 Business Logic & Processing Services
- **`PDFGeneratorService` (`services/pdf_service.py`)**:
  - Encapsulates ReportLab document assembly using Flowables (`Paragraph`, `Spacer`, `Table`).
  - Utilizes custom `NumberedCanvas` to calculate total pages dynamically on the second rendering pass ("Page X of Y").
  - Produces publication-quality A4 PDF documents in memory (`io.BytesIO`).
- **`StorageService` (`services/storage_service.py`)**:
  - Orchestrates dual-tier storage between Supabase Storage (cloud) and local filesystem fallback.
  - Enforces safe filename sanitization.
- **`SupabaseStorageService` (`services/supabase_storage_service.py`)**:
  - Integrates official `supabase` Python SDK.
  - Manages uploads to private bucket `pdf-documents`.
  - Generates signed URLs with 1-hour expiration for secure inline preview and attachment downloading.
- **`PostgresService` (`services/postgres_service.py`)**:
  - Manages relational data persistence via SQLAlchemy 2.0 ORM.
  - Handles connection pooling (`pool_pre_ping=True`) to maintain persistent database connections to Supabase PgBouncer pooler.
- **`AuthService` (`services/auth_service.py`)**:
  - Implements password hashing via bcrypt (work factor 12).
  - Enforces RFC email format validation and password complexity rules.

---

## 3. Core Interaction Workflows

### 3.1 User Authentication Flow
```mermaid
sequenceDiagram
    autonumber
    actor User as User / Browser
    participant App as Flask Auth Route
    participant Auth as AuthService
    participant DB as Supabase PostgreSQL

    User->>App: POST /register (name, email, password)
    App->>Auth: register_user(name, email, password)
    Auth->>Auth: Validate RFC email & password strength
    Auth->>DB: Query existing user by email
    alt Email already exists
        DB-->>Auth: User record exists
        Auth-->>App: Registration Error ("Email exists")
        App-->>User: 400 Bad Request
    else Email unique
        Auth->>Auth: Hash password with bcrypt (salt 12)
        Auth->>DB: INSERT into users (user_id, name, email, password_hash)
        DB-->>Auth: Success
        Auth-->>App: Return User object
        App->>User: Set session cookie (HttpOnly, SameSite=Lax) & Redirect /
    end
```

### 3.2 4-Step PDF Generation Pipeline
```mermaid
sequenceDiagram
    autonumber
    actor User as User / Browser
    participant API as POST /api/generate-pdf
    participant PDF as PDFGeneratorService
    participant Storage as SupabaseStorageService
    participant DB as PostgresService

    User->>API: Submit Title, Author, Description, Content
    API->>PDF: generate_pdf_bytes(title, author, description, content)
    PDF->>PDF: Compile ReportLab Flowables & NumberedCanvas
    PDF-->>API: Return binary PDF bytes

    API->>Storage: upload_file(user_id/doc_id.pdf, pdf_bytes)
    alt Cloud Upload Fails
        Storage-->>API: Upload Error
        API->>API: Fallback to local disk (storage/generated_pdfs/)
    else Cloud Upload OK
        Storage-->>API: Cloud Sync OK
    end

    API->>DB: insert_document(doc_record)
    alt Database Insertion Fails
        DB-->>API: Rollback trigger
        API->>Storage: delete_file(user_id/doc_id.pdf) [Compensating Transaction]
        API-->>User: 500 Error ("Database failure, cloud file cleaned up")
    else Database Insertion OK
        DB-->>API: Document indexed successfully
        API-->>User: 201 Created (JSON or Binary stream)
    end
```

### 3.3 Private PDF Preview & Download Flow
```mermaid
sequenceDiagram
    autonumber
    actor User as User / Browser
    participant API as GET /api/documents/<id>/preview
    participant Repo as DocumentRepository
    participant Storage as SupabaseStorageService
    participant Supa as Supabase Storage Bucket

    User->>API: Request PDF Preview
    API->>Repo: get_by_id(doc_id)
    Repo-->>API: Document metadata (owner: user_id)
    alt User is not owner
        API-->>User: 403 Forbidden ("Access Denied")
    else User is verified owner
        API->>Storage: create_signed_url(storage_path, expiresIn=3600)
        Storage->>Supa: Sign ephemeral token
        Supa-->>Storage: Signed HTTPS URL
        Storage-->>API: Signed URL
        API-->>User: 302 Found (Redirect to Signed URL)
        User->>Supa: Fetch private binary via signed URL
        Supa-->>User: Stream PDF to browser iframe
    end
```

---

## 4. Cloud Deployment Architecture

```mermaid
graph LR
    subgraph GitHub["GitHub Repository"]
        Repo["gagankumarm39-gif/cloudpdf1\n(Excludes .env via .gitignore)"]
    end

    subgraph Render["Render Free Cloud Platform"]
        Build["Build Phase:\npip install -r requirements.txt"]
        WSGI["Execution:\ngunicorn --config gunicorn_config.py app:app"]
        Health["Monitoring:\nGET /api/health (200 OK)"]
    end

    subgraph Supabase["Supabase Cloud Platform (Tokyo/Singapore)"]
        Storage["Storage Service:\nBucket 'pdf-documents'"]
        Postgres["PostgreSQL 15+:\naws-1-ap-northeast-1.pooler.supabase.com:5432"]
    end

    Repo -->|git push main| Build
    Build --> WSGI
    WSGI --> Health
    WSGI -->|HTTPS API / Signed URLs| Storage
    WSGI -->|SQLAlchemy / SSL| Postgres
```
