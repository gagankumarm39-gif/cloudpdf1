"""
Cloud-Based PDF Generation System
College Cloud Computing Project
Milestone 6 – User Authentication and Security
"""
import random
import io
import os
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request, send_file, redirect, url_for, flash
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from flask_wtf.csrf import CSRFProtect

# Load environment variables from .env if present
load_dotenv()

from services.pdf_service import PDFGeneratorService
from services.s3_service import S3Service
from services.supabase_storage_service import SupabaseStorageService
from services.dynamodb_service import DynamoDBService
from services.postgres_service import PostgresService
from services.storage_service import StorageService
from services.document_repository import DocumentRepository
from services.auth_service import AuthService

app = Flask(__name__)
# Generate secure fallback key in development if SECRET_KEY is not set in environment
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY", "cloud-pdf-fallback-insecure-dev-key")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# In production behind HTTPS (Render, AWS ALB/CloudFront), enforce secure session cookies
# Can be explicitly controlled via SESSION_COOKIE_SECURE_ENABLED or auto-enabled when FLASK_ENV=production
flask_env = os.getenv("FLASK_ENV", "development").lower()
cookie_secure_env = os.getenv("SESSION_COOKIE_SECURE_ENABLED", "").lower()
if cookie_secure_env in ["true", "1", "yes"] or (flask_env == "production" and cookie_secure_env != "false"):
    app.config["SESSION_COOKIE_SECURE"] = True
else:
    app.config["SESSION_COOKIE_SECURE"] = False

# Initialize CSRF Protection
csrf = CSRFProtect(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access your cloud documents."
login_manager.login_message_category = "error"

# Instantiate services
postgres_service = PostgresService()
if postgres_service.is_configured():
    try:
        postgres_service.init_db()
    except Exception as e:
        app.logger.warning(f"PostgreSQL init_db failed on startup: {e}")

supabase_storage_service = SupabaseStorageService()
s3_service = S3Service()
dynamodb_service = DynamoDBService()
storage_service = StorageService(supabase_service=supabase_storage_service, s3_service=s3_service)
pdf_service = PDFGeneratorService()
document_repo = DocumentRepository(dynamodb_service=dynamodb_service, postgres_service=postgres_service)
auth_service = AuthService(postgres_service=postgres_service)

# Exempt REST API routes from CSRF token validation so JSON/fetch requests work seamlessly
csrf.exempt("app.health_check")
csrf.exempt("app.get_documents")
csrf.exempt("app.get_document_details")
csrf.exempt("app.preview_document")
csrf.exempt("app.download_document")
csrf.exempt("app.delete_document")
csrf.exempt("app.generate_pdf")
csrf.exempt("app.download_pdf_legacy")


@login_manager.user_loader
def load_user(user_id: str):
    """Load user by user_id for Flask-Login session management."""
    return auth_service.get_user_by_id(user_id)


def get_current_stats(user_id: str = None):
    """Helper to get fresh dashboard statistics scoped to user."""
    return document_repo.get_statistics(
        s3_bucket=s3_service.bucket_name,
        s3_configured=s3_service.is_configured(),
        supabase_bucket=supabase_storage_service.bucket_name,
        supabase_configured=supabase_storage_service.is_configured(),
        dynamodb_table=dynamodb_service.table_name,
        dynamodb_configured=dynamodb_service.is_configured(),
        postgres_configured=postgres_service.is_configured(),
        region=s3_service.region_name,
        user_id=user_id
    )


# ============================================================================
# Authentication Routes
# ============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """Sign-in page and authentication handler."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not email or not password:
            flash("Please enter both email address and password.", "error")
            return render_template("login.html", email=email), 400

        user, err = auth_service.authenticate_user(email, password)
        if err or not user:
            flash(err or "Invalid email or password.", "error")
            return render_template("login.html", email=email), 401

        login_user(user, remember=remember)
        flash(f"Welcome back, {user.name}!", "success")

        next_page = request.args.get("next")
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration page and handler."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("All fields marked with an asterisk are required.", "error")
            return render_template("register.html", name=name, email=email), 400

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html", name=name, email=email), 400

        user, err = auth_service.register_user(name=name, email=email, password=password)
        if err or not user:
            flash(err or "Registration failed.", "error")
            return render_template("register.html", name=name, email=email), 400

        # Auto-login upon successful registration
        login_user(user)
        flash("Your account has been created successfully! Welcome to CloudPDF Studio.", "success")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Clear user session and redirect to login."""
    logout_user()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for("login"))


# ============================================================================
# Core Application & Dashboard Routes
# ============================================================================

@app.route("/")
def index():
    """
    Render the dashboard and PDF studio homepage.
    If authenticated, shows the user's documents; otherwise prompts or uses demo account.
    """
    user_id = current_user.user_id if current_user.is_authenticated else None
    docs = document_repo.list_all(user_id=user_id)
    stats = get_current_stats(user_id=user_id)
    return render_template(
        "index.html",
        metrics=stats,
        documents=docs
    )


@app.route("/api/health", methods=["GET"])
def health_check():
    """
    Production health check API route for monitoring deployment status and cloud readiness.
    Reports live connectivity to Supabase Storage, PostgreSQL, S3, and DynamoDB without exposing secrets or credentials.
    """
    supabase_conn = supabase_storage_service.check_connection()
    postgres_conn = postgres_service.check_connection()
    s3_conn = s3_service.check_connection()
    dynamodb_conn = dynamodb_service.check_connection()
    auth_conn = auth_service.check_connection()

    # Determine overall cloud health status
    overall_status = "healthy"
    if supabase_storage_service.is_configured() and not supabase_conn.get("accessible"):
        overall_status = "degraded"
    if postgres_service.is_configured() and not postgres_conn.get("accessible"):
        overall_status = "degraded"
    if s3_service.is_configured() and not s3_conn.get("accessible"):
        overall_status = "degraded"
    if dynamodb_service.is_configured() and not dynamodb_conn.get("accessible"):
        overall_status = "degraded"

    return jsonify({
        "status": overall_status,
        "service": "Cloud-Based PDF Generation System",
        "version": "9.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": os.getenv("FLASK_ENV", "development"),
        "milestone": "Milestone 9 – Supabase PostgreSQL Integration",
        "cloud_services": {
            "supabase_storage": {
                "configured": supabase_conn["configured"],
                "accessible": supabase_conn["accessible"],
                "status": supabase_conn["status"],
                "bucket": supabase_conn.get("bucket"),
                "public": supabase_conn.get("public", False)
            },
            "supabase_postgres": {
                "configured": postgres_conn["configured"],
                "accessible": postgres_conn["accessible"],
                "status": postgres_conn["status"],
                "host": postgres_conn.get("host"),
                "database": postgres_conn.get("database"),
                "dialect": postgres_conn.get("dialect")
            },
            "s3": {
                "configured": s3_conn["configured"],
                "accessible": s3_conn["accessible"],
                "status": s3_conn["status"],
                "bucket": s3_conn.get("bucket"),
                "region": s3_service.region_name
            },
            "dynamodb_documents": {
                "configured": dynamodb_conn["configured"],
                "accessible": dynamodb_conn["accessible"],
                "status": dynamodb_conn["status"],
                "table": dynamodb_conn.get("table"),
                "region": dynamodb_service.region_name
            },
            "dynamodb_users": {
                "configured": auth_conn["configured"],
                "accessible": auth_conn["accessible"],
                "status": auth_conn["status"],
                "table": auth_conn.get("table"),
                "region": auth_service.region_name
            }
        }
    }), 200


@app.route("/api/documents", methods=["GET"])
def get_documents():
    """
    List all documents with optional search and sorting, scoped to authenticated user.
    Query parameters:
    - search: filter by title, author, or document id
    - sort: 'date' | 'title' | 'size' (default: 'date')
    - order: 'desc' | 'asc' (default: 'desc')
    """
    user_id = current_user.user_id if current_user.is_authenticated else None
    search_query = request.args.get("search", "").strip()
    sort_by = request.args.get("sort", "date").strip()
    order = request.args.get("order", "desc").strip()

    docs = document_repo.list_all(search=search_query, sort_by=sort_by, order=order, user_id=user_id)
    stats = get_current_stats(user_id=user_id)

    return jsonify({
        "success": True,
        "count": len(docs),
        "documents": docs,
        "statistics": stats
    }), 200


@app.route("/api/documents/<doc_id>", methods=["GET"])
def get_document_details(doc_id):
    """Retrieve metadata for a specific document with user ownership check."""
    doc = document_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({
            "success": False,
            "error": f"Document with ID '{doc_id}' not found."
        }), 404

    # Ownership check
    if current_user.is_authenticated:
        doc_owner = doc.get("user_id") or "USER-DEMO-001"
        if doc_owner != current_user.user_id:
            return jsonify({
                "success": False,
                "error": "Access Denied: You do not have permission to view this document."
            }), 403

    return jsonify({
        "success": True,
        "document": doc
    }), 200


@app.route("/api/documents/<doc_id>/preview", methods=["GET"])
def preview_document(doc_id):
    """
    Preview PDF inline in the browser without triggering file download.
    Enforces user ownership check.
    If stored in Amazon S3 or Supabase Storage, redirects to a secure short-lived signed URL.
    Otherwise, streams directly from local storage.
    """
    doc = document_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({
            "success": False,
            "error": f"Document with ID '{doc_id}' not found."
        }), 404

    # Ownership check
    if current_user.is_authenticated:
        doc_owner = doc.get("user_id") or "USER-DEMO-001"
        if doc_owner != current_user.user_id:
            return jsonify({
                "success": False,
                "error": "Access Denied: You do not have permission to preview this document."
            }), 403

    filename = doc.get("filename")
    storage_path = doc.get("storage_path") or doc.get("s3_key")

    try:
        source_type, target = storage_service.get_preview_stream_or_url(filename, storage_path=storage_path)
        if source_type == "url":
            return redirect(target, code=302)
        else:
            return send_file(
                target,
                mimetype="application/pdf",
                as_attachment=False,
                download_name=filename
            )
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": f"Document file '{filename}' was not found in storage."
        }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Failed to preview document",
            "message": str(e)
        }), 500


@app.route("/api/documents/<doc_id>/download", methods=["GET"])
def download_document(doc_id):
    """
    Download PDF attachment by its document ID with user ownership check.
    If cloud storage (Supabase / S3) is enabled, redirects to secure signed download URL.
    Otherwise, streams directly from local storage.
    """
    doc = document_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({
            "success": False,
            "error": f"Document with ID '{doc_id}' not found."
        }), 404

    # Ownership check
    if current_user.is_authenticated:
        doc_owner = doc.get("user_id") or "USER-DEMO-001"
        if doc_owner != current_user.user_id:
            return jsonify({
                "success": False,
                "error": "Access Denied: You do not have permission to download this document."
            }), 403

    filename = doc.get("filename")
    storage_path = doc.get("storage_path") or doc.get("s3_key")

    try:
        source_type, target = storage_service.get_download_stream_or_url(filename, storage_path=storage_path)
        if source_type == "url":
            return redirect(target, code=302)
        else:
            return send_file(
                target,
                mimetype="application/pdf",
                as_attachment=True,
                download_name=filename
            )
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": f"Document file '{filename}' was not found in storage."
        }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Failed to download document",
            "message": str(e)
        }), 500


@app.route("/api/documents/<doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    """
    Delete a document from database, Supabase Storage / Amazon S3, and local storage.
    Enforces user ownership check.
    """
    doc = document_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({
            "success": False,
            "error": f"Document with ID '{doc_id}' not found."
        }), 404

    # Ownership check
    if current_user.is_authenticated:
        doc_owner = doc.get("user_id") or "USER-DEMO-001"
        if doc_owner != current_user.user_id:
            return jsonify({
                "success": False,
                "error": "Access Denied: You do not have permission to delete this document."
            }), 403

    filename = doc.get("filename")
    storage_path = doc.get("storage_path") or doc.get("s3_key")

    # 1. Remove physical files (local and cloud)
    storage_service.delete_file(filename, storage_path=storage_path)

    # 2. Remove metadata entry from DynamoDB & local repository
    deleted = document_repo.delete(doc_id)
    if not deleted:
        return jsonify({
            "success": False,
            "error": "Failed to delete document from metadata catalog."
        }), 500

    # 3. Return updated stats
    user_id = current_user.user_id if current_user.is_authenticated else None
    new_stats = get_current_stats(user_id=user_id)
    return jsonify({
        "success": True,
        "message": f"Document '{doc_id}' deleted successfully from cloud storage and database.",
        "deleted_id": doc_id,
        "statistics": new_stats
    }), 200


@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf():
    """
    4-Step PDF Generation Pipeline:
    Step 1: Generate PDF using ReportLab engine.
    Step 2: Upload PDF to Amazon S3 (with local fallback).
    Step 3: Store document metadata in Amazon DynamoDB.
            (Handles partial failure: if DynamoDB fails, rolls back uploaded S3 object).
    Step 4: Return successful response to frontend with binary stream or JSON.
    """
    storage_meta = None
    try:
        data = request.get_json(silent=True) or request.form.to_dict()

        if not data:
            return jsonify({
                "success": False,
                "error": "Invalid request: Payload must be JSON or Form Data."
            }), 400

        title = str(data.get("title", "")).strip()
        author = str(data.get("author", "")).strip()
        description = str(data.get("description", "")).strip()
        content = str(data.get("content", "")).strip()

        # Determine user ownership
        user_id = current_user.user_id if current_user.is_authenticated else "USER-DEMO-001"
        if not author and current_user.is_authenticated:
            author = current_user.name

        # Validation
        errors = {}
        if not title:
            errors["title"] = "Document title is required."
        if not author:
            errors["author"] = "Author name is required."
        if not content:
            errors["content"] = "Main document content is required."

        if errors:
            return jsonify({
                "success": False,
                "error": "Validation failed",
                "details": errors
            }), 400

        # Unique Document ID
        doc_id = f"DOC-{random.randint(1000, 9999)}"

        # Step 1: Generate PDF using ReportLab
        pdf_bytes = pdf_service.generate_pdf(
            title=title,
            author=author,
            description=description,
            content=content,
            doc_id=doc_id
        )

        # Step 2: Upload PDF to Cloud Storage (Supabase Storage with local backup)
        storage_meta = storage_service.save_pdf(
            pdf_bytes=pdf_bytes,
            doc_id=doc_id,
            title=title,
            author=author,
            user_id=user_id
        )

        # Step 3: Store document metadata in DynamoDB (and sync with local cache)
        doc_record = {
            "id": doc_id,
            "doc_id": doc_id,
            "user_id": user_id,
            "title": title,
            "author": author,
            "description": description,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "size": storage_meta["size_formatted"],
            "file_size": storage_meta["size_formatted"],
            "size_bytes": storage_meta["size_bytes"],
            "status": "Ready",
            "storage_type": storage_meta["storage_type"],
            "filename": storage_meta["filename"],
            "storage_path": storage_meta["storage_path"],
            "s3_key": storage_meta.get("s3_key"),
            "storage_bucket": storage_meta.get("supabase_bucket") or storage_meta.get("s3_bucket"),
            "supabase_bucket": storage_meta.get("supabase_bucket"),
            "s3_bucket": storage_meta.get("s3_bucket"),
            "cloud_synced": storage_meta.get("cloud_synced", False),
            "supabase_synced": storage_meta.get("supabase_synced", False),
            "s3_synced": storage_meta.get("s3_synced", False),
            "content_type": "application/pdf"
        }

        try:
            document_repo.add(doc_record)
        except Exception as db_err:
            app.logger.error(f"DynamoDB metadata storage failed: {db_err}. Rolling back cloud storage object.", exc_info=True)
            # Partial failure recovery: cleanup uploaded cloud object to prevent orphaned cloud files
            if storage_meta.get("supabase_synced") and storage_meta.get("storage_path"):
                supabase_storage_service.delete_file(storage_meta["storage_path"])
            if storage_meta.get("s3_synced") and storage_meta.get("s3_key"):
                s3_service.delete_object(storage_meta["s3_key"])
            raise RuntimeError(f"Database metadata insertion failed: {str(db_err)}")

        # Step 4: Return response to caller
        want_binary = request.args.get("download", "true").lower() in ["true", "1", "yes"]

        if want_binary:
            response = send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=storage_meta["filename"]
            )
            response.headers["X-Doc-Id"] = doc_id
            response.headers["X-Doc-Title"] = title
            response.headers["X-Doc-Author"] = author
            response.headers["X-Doc-Size"] = storage_meta["size_formatted"]
            response.headers["X-Doc-Filename"] = storage_meta["filename"]
            response.headers["X-Cloud-Synced"] = "true" if storage_meta.get("cloud_synced") else "false"
            response.headers["X-Supabase-Synced"] = "true" if storage_meta.get("supabase_synced") else "false"
            response.headers["X-S3-Synced"] = "true" if storage_meta.get("s3_synced") else "false"
            response.headers["X-Postgres-Synced"] = "true" if postgres_service.is_configured() else "false"
            response.headers["X-DynamoDB-Synced"] = "true" if dynamodb_service.is_configured() else "false"
            response.headers["Access-Control-Expose-Headers"] = "X-Doc-Id, X-Doc-Title, X-Doc-Author, X-Doc-Size, X-Doc-Filename, X-Cloud-Synced, X-Supabase-Synced, X-S3-Synced, X-Postgres-Synced, X-DynamoDB-Synced"
            return response

        return jsonify({
            "success": True,
            "message": "PDF generated, uploaded to cloud storage, and indexed in database successfully.",
            "document": doc_record,
            "download_url": f"/api/documents/{doc_id}/download",
            "preview_url": f"/api/documents/{doc_id}/preview",
            "cloud_synced": storage_meta.get("cloud_synced", False),
            "supabase_synced": storage_meta.get("supabase_synced", False),
            "s3_synced": storage_meta.get("s3_synced", False),
            "postgres_synced": postgres_service.is_configured(),
            "dynamodb_synced": dynamodb_service.is_configured()
        }), 201

    except Exception as e:
        app.logger.error(f"Error in PDF generation pipeline: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to generate and record PDF document.",
            "message": str(e)
        }), 500


# Legacy download route preserved for backwards compatibility
@app.route("/api/download-pdf/<filename>", methods=["GET"])
def download_pdf_legacy(filename):
    try:
        filepath = storage_service.get_file_path(filename)
        return send_file(
            filepath,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    is_debug = os.getenv("FLASK_DEBUG", "false").lower() in ["true", "1", "yes"]
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=is_debug)
