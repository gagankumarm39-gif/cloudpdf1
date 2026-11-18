# API Documentation: Cloud-Based PDF Generation System

## Milestone 12 Technical Reference

This document provides a comprehensive reference for all HTTP REST API endpoints and web routes available in the **Cloud-Based PDF Generation System**.

---

## 1. Global Endpoints

### 1.1 Health Check Probe
Monitors cloud services, database connectivity, and deployment readiness.

- **URL**: `/api/health`
- **Method**: `GET`
- **Auth Required**: No (Exempt from CSRF)
- **Response Format**: `application/json`

#### Successful Response (HTTP 200)
```json
{
  "status": "healthy",
  "service": "Cloud-Based PDF Generation System",
  "version": "9.0.0",
  "timestamp": "2026-11-18T14:45:00Z",
  "environment": "production",
  "milestone": "Milestone 10 – Complete Cloud Deployment Using Render",
  "cloud_services": {
    "supabase_storage": {
      "configured": true,
      "accessible": true,
      "status": "connected",
      "bucket": "pdf-documents",
      "public": false
    },
    "supabase_postgres": {
      "configured": true,
      "accessible": true,
      "status": "connected",
      "database": "Supabase PostgreSQL",
      "dialect": "postgresql"
    },
    "s3": {
      "configured": false,
      "accessible": false,
      "status": "unconfigured",
      "bucket": null,
      "region": "us-east-1"
    },
    "dynamodb_documents": {
      "configured": false,
      "accessible": false,
      "status": "unconfigured",
      "table": null,
      "region": "us-east-1"
    },
    "dynamodb_users": {
      "configured": false,
      "accessible": false,
      "status": "unconfigured",
      "table": null,
      "region": "us-east-1"
    }
  }
}
```

---

## 2. Authentication Routes

### 2.1 User Login
- **URL**: `/login`
- **Method**: `GET`, `POST`
- **Form Parameters (POST)**:
  - `email` (string, required): Registered user email.
  - `password` (string, required): User password.
  - `remember` (boolean, optional): Keep session active.
- **CSRF Token**: Required in form payload (`csrf_token`).
- **Response**: Redirects to `/` on success (302) or re-renders `/login` with flash error (401/400).

### 2.2 User Registration
- **URL**: `/register`
- **Method**: `GET`, `POST`
- **Form Parameters (POST)**:
  - `name` (string, required): Full name.
  - `email` (string, required): Valid email address.
  - `password` (string, required): Minimum 8 characters, with letters and numbers.
  - `confirm_password` (string, required): Must match `password`.
- **CSRF Token**: Required in form payload.
- **Response**: Redirects to `/` with auto-login on success (302).

### 2.3 User Logout
- **URL**: `/logout`
- **Method**: `GET`
- **Auth Required**: Yes
- **Response**: Terminates session, clears session cookies, redirects to `/login` (302).

---

## 3. PDF Generation Endpoint

### 3.1 Generate PDF Document
Compiles publication-quality PDF via ReportLab, stores binary in cloud storage (Supabase / S3), and indexes metadata in PostgreSQL.

- **URL**: `/api/generate-pdf`
- **Method**: `POST`
- **Auth Required**: Recommended (Falls back to `USER-DEMO-001` if unauthenticated).
- **Query Parameters**:
  - `download` (`boolean`, default: `true`):
    - `true`: Directly streams the generated `.pdf` binary file as an attachment.
    - `false`: Returns JSON metadata with direct preview and download URLs.
- **Request Body (`application/json`)**:
```json
{
  "title": "Quarterly Systems Audit",
  "author": "Cloud Systems Team",
  "description": "Comprehensive cloud security and architectural assessment.",
  "content": "Paragraph text representing detailed document findings..."
}
```

#### JSON Response (`download=false`, HTTP 201 Created)
```json
{
  "success": true,
  "message": "PDF generated, uploaded to cloud storage, and indexed in database successfully.",
  "document": {
    "id": "DOC-7412",
    "doc_id": "DOC-7412",
    "user_id": "USER-DEMO-001",
    "title": "Quarterly Systems Audit",
    "author": "Cloud Systems Team",
    "description": "Comprehensive cloud security and architectural assessment.",
    "filename": "DOC-7412_Quarterly_Systems_Audit.pdf",
    "storage_path": "USER-DEMO-001/DOC-7412_Quarterly_Systems_Audit.pdf",
    "storage_bucket": "pdf-documents",
    "storage_type": "supabase_and_local",
    "file_size": "214.2 KB",
    "size_bytes": 219340,
    "created_at": "2026-11-18T14:48:00Z",
    "status": "Ready",
    "cloud_synced": true,
    "supabase_synced": true,
    "postgres_synced": true
  },
  "download_url": "/api/documents/DOC-7412/download",
  "preview_url": "/api/documents/DOC-7412/preview",
  "cloud_synced": true,
  "supabase_synced": true,
  "postgres_synced": true
}
```

#### Binary Response (`download=true`, HTTP 200 OK)
- **Headers**:
  - `Content-Type`: `application/pdf`
  - `Content-Disposition`: `attachment; filename="DOC-7412_Quarterly_Systems_Audit.pdf"`
  - `X-Doc-Id`: `DOC-7412`
  - `X-Supabase-Synced`: `true`
  - `X-Postgres-Synced`: `true`

---

## 4. Document Management Endpoints

### 4.1 List Documents
Retrieves all documents owned by the authenticated user with search and sorting.

- **URL**: `/api/documents`
- **Method**: `GET`
- **Auth Required**: Recommended (scoped to `current_user.user_id`)
- **Query Parameters**:
  - `search` (string, optional): Filter by title, author, or doc_id.
  - `sort` (string, default: `date`): `date` | `title` | `size`.
  - `order` (string, default: `desc`): `desc` | `asc`.

#### Response (HTTP 200 OK)
```json
{
  "success": true,
  "count": 1,
  "documents": [
    {
      "id": "DOC-7412",
      "doc_id": "DOC-7412",
      "title": "Quarterly Systems Audit",
      "author": "Cloud Systems Team",
      "created_at": "2026-11-18T14:48:00Z",
      "size": "214.2 KB",
      "size_bytes": 219340,
      "filename": "DOC-7412_Quarterly_Systems_Audit.pdf",
      "storage_path": "USER-DEMO-001/DOC-7412_Quarterly_Systems_Audit.pdf",
      "storage_type": "supabase_and_local",
      "status": "Ready"
    }
  ],
  "statistics": {
    "total_generated": 1,
    "total_bytes": 219340,
    "storage_used": "214.2 KB",
    "cloud_storage_status": "Supabase Storage (pdf-documents)",
    "database_status": "Supabase PostgreSQL",
    "recent_count": 1
  }
}
```

### 4.2 Get Document Details
- **URL**: `/api/documents/<doc_id>`
- **Method**: `GET`
- **Auth Check**: Yes (Returns HTTP 403 Forbidden if requester is not document owner).
- **Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "document": {
    "id": "DOC-7412",
    "title": "Quarterly Systems Audit",
    "author": "Cloud Systems Team",
    "size": "214.2 KB"
  }
}
```

### 4.3 Preview Document (Inline View)
Streams the PDF inline or redirects to a secure signed URL for in-browser iframe viewing.

- **URL**: `/api/documents/<doc_id>/preview`
- **Method**: `GET`
- **Auth Check**: Yes (Enforces ownership).
- **Behavior**:
  - When Supabase Storage is active: Returns `HTTP 302 Found` redirecting to an ephemeral signed URL (`expiresIn: 3600`).
  - When local storage is active: Returns `HTTP 200 OK` with `Content-Type: application/pdf` and `Content-Disposition: inline`.

### 4.4 Download Document
Forces browser download of PDF as an attachment.

- **URL**: `/api/documents/<doc_id>/download`
- **Method**: `GET`
- **Auth Check**: Yes (Enforces ownership).
- **Behavior**:
  - When Supabase Storage is active: Returns `HTTP 302 Found` with download transform.
  - When local storage is active: Returns `HTTP 200 OK` with `Content-Disposition: attachment; filename="<safe_filename>.pdf"`.

### 4.5 Delete Document
Deletes document record from PostgreSQL and removes binary object from cloud/local storage.

- **URL**: `/api/documents/<doc_id>`
- **Method**: `DELETE`
- **Auth Check**: Yes (Enforces ownership).
- **Response (HTTP 200 OK)**:
```json
{
  "success": true,
  "message": "Document 'DOC-7412' deleted successfully from cloud storage and database.",
  "deleted_id": "DOC-7412",
  "statistics": {
    "total_generated": 0,
    "storage_used": "0 B"
  }
}
```

#### Error Response (HTTP 403 Forbidden)
```json
{
  "success": false,
  "error": "Access Denied: You do not have permission to delete this document."
}
```
