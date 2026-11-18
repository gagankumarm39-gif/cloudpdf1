# Security Policy & Validation Architecture

## Cloud-Based PDF Generation System — Milestone 11

This document outlines the security architecture, threat model, authorization controls, and cryptographic implementations applied across the Cloud-Based PDF Generation System.

---

## 1. Authentication & Identity Management

- **Password Hashing**:
  - Implemented in `services/auth_service.py` using **bcrypt** with automatic salt generation and work factor 12. Plaintext passwords are never stored or logged.
- **Session Security**:
  - Backed by **Flask-Login** session cookies.
  - `SESSION_COOKIE_HTTPONLY = True`: Blocks JavaScript `document.cookie` access, preventing XSS-based session hijacking.
  - `SESSION_COOKIE_SAMESITE = "Lax"`: Protects against Cross-Site Request Forgery (CSRF).
  - `SESSION_COOKIE_SECURE`: Automatically enforced in production environments behind HTTPS (Render / TLS termination).
- **Flask `SECRET_KEY` Handling**:
  - The secret key signs session cookies and CSRF tokens.
  - Generated using Python `secrets.token_hex(32)` (256-bit cryptographically secure pseudorandom number generator).
  - Kept strictly in backend environment variables (`SECRET_KEY`). Never hardcoded, never committed to GitHub, and never logged in stdout/stderr.

---

## 2. Multi-User Authorization & Data Isolation

The application enforces strict multi-tenant data boundaries:

- **Row-Level Ownership**:
  - Every document record contains a foreign key to `users.user_id`.
  - When querying documents (`GET /api/documents`), results are strictly filtered by `user_id = current_user.user_id`.
- **Access Control Checks**:
  - On `/api/documents/<doc_id>`, `/preview`, `/download`, and `DELETE /api/documents/<doc_id>`, the backend loads the document and explicitly verifies:
    ```python
    if doc.get("user_id") != current_user.user_id:
        return jsonify({"error": "Access Denied"}), 403
    ```
  - Cross-user viewing, downloading, or deleting is blocked with **HTTP 403 Forbidden**.

---

## 3. Storage Security (Supabase Storage)

- **Private Bucket Protection**:
  - The `pdf-documents` bucket is configured as **Private** (public bucket setting is OFF).
  - Files cannot be directly read or enumerated via unauthenticated public HTTP GET requests.
- **User-Isolated Storage Paths**:
  - Files are uploaded to segmented paths: `{user_id}/{doc_id}_{filename}.pdf`.
  - Path traversal attempts (e.g. `../../etc/passwd` or `..\\windows\\system32`) are stripped using `sanitize_storage_path()` regex filters.
- **Ephemeral Signed URLs**:
  - For browser previewing and attachment downloads, the backend generates short-lived signed URLs (`create_signed_url`) with a default lifespan of 3600 seconds (1 hour). Once expired, access is revoked automatically.
- **Service Role Secret Key vs. Publishable Key**:
  - Server-side administrative operations (uploading, deleting private objects) utilize the Supabase `service_role` key stored securely on Render.
  - The publishable key is never used to circumvent storage security, and secret keys are never passed to the browser.

---

## 4. Database Security & SQL Injection Prevention

- **SQLAlchemy ORM & Parameterized Queries**:
  - All database queries in `services/postgres_service.py` use SQLAlchemy models and ORM filters (`filter()`, `filter_by()`, `session.merge()`).
  - Search queries use parameterized `ilike()` wildcards.
  - Direct string concatenation or raw `f"SELECT ... {input}"` statements are strictly forbidden, mitigating SQL injection vulnerabilities.
- **Foreign Key Constraints & Cascading Deletes**:
  - Document records reference `users(user_id) ON DELETE CASCADE`. If a user account is removed, all associated documents are automatically cleaned up to prevent orphaned records.

---

## 5. Input Validation & Content Security

- **PDF Compilation Guardrails**:
  - Inputs (`title`, `author`, `description`, `content`) are validated on the backend. Missing or empty fields trigger **HTTP 400 Bad Request**.
  - Document filenames are sanitized via `StorageService.sanitize_filename()` to remove dangerous filesystem characters (`/ \ : * ? " < > |`).
- **CSRF Token Protection**:
  - Enabled via `Flask-WTF` (`CSRFProtect`).
  - Login, registration, and web forms require valid CSRF tokens. REST API endpoints intended for JSON payloads are explicitly exempted.

---

## 6. Security Testing & Verification Matrix

| Vulnerability / Test Area | Defense Mechanism | Automated Test Status |
|---|---|---|
| Plaintext Password Exposure | Bcrypt salted hashing (12 rounds) | Verified in `test_auth_service.py` |
| Cross-User Document Access | Backend ownership check (HTTP 403) | Verified in `test_milestone11_validation.py` |
| SQL Injection in Search / Form | Parameterized ORM queries | Verified in `test_milestone11_validation.py` |
| Path Traversal in Storage | Regex path sanitization (`..` removed) | Verified in `test_milestone11_validation.py` |
| Session Hijacking | `HttpOnly` + `SameSite=Lax` + `Secure` cookies | Verified in `test_production_config.py` |
| Unauthenticated File Deletion | Backend ownership validation | Verified in `test_milestone11_validation.py` |
| Secret Leaks in Health Check | Credential masking in JSON output | Verified in `test_production_config.py` |
