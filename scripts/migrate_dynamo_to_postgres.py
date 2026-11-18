"""
Migration Utility: DynamoDB & Local Metadata to Supabase PostgreSQL
College Cloud Computing Project - Milestone 9

Transfers user accounts and PDF document metadata from Amazon DynamoDB
and/or local JSON stores to Supabase PostgreSQL idempotently (upsert).
Does NOT delete or alter DynamoDB or local records.
"""
import os
import sys
import logging
from typing import Dict, Any, List

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.postgres_service import PostgresService
from services.dynamodb_service import DynamoDBService
from services.auth_service import AuthService
from services.document_repository import DocumentRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MigrateDynamoToPostgres")


def migrate_users(auth_service: AuthService, pg_service: PostgresService) -> Dict[str, int]:
    """
    Migrates users from DynamoDB or local users JSON store into PostgreSQL.
    """
    stats = {"scanned": 0, "inserted": 0, "skipped_or_updated": 0, "errors": 0}
    users: List[Dict[str, Any]] = []

    # 1. Try DynamoDB if configured
    if auth_service.is_dynamodb_configured():
        try:
            logger.info(f"Scanning DynamoDB users table '{auth_service.table_name}'...")
            res = auth_service.table.scan()
            users = res.get("Items", [])
            logger.info(f"Retrieved {len(users)} user(s) from DynamoDB.")
        except Exception as e:
            logger.warning(f"Failed to scan DynamoDB users table: {e}. Falling back to local users.")

    # 2. Fall back to local users store if DynamoDB is empty/unconfigured
    if not users:
        logger.info("Reading users from local store...")
        users = auth_service._read_local_users()
        logger.info(f"Found {len(users)} user(s) in local store.")

    stats["scanned"] = len(users)

    # 3. Upsert users into PostgreSQL
    for u in users:
        user_id = u.get("user_id")
        email = u.get("email")
        name = u.get("name", "User")
        pw_hash = u.get("password_hash")
        created_at = u.get("created_at")

        if not user_id or not email:
            continue

        try:
            user_dict, err = pg_service.create_user(
                user_id=user_id,
                name=name,
                email=email,
                password_hash=pw_hash,
                created_at=created_at
            )
            if err:
                if "already exists" in str(err).lower():
                    stats["skipped_or_updated"] += 1
                else:
                    logger.warning(f"Error creating user {user_id} ({email}): {err}")
                    stats["errors"] += 1
            else:
                stats["inserted"] += 1
        except Exception as e:
            logger.error(f"Exception creating user {user_id}: {e}")
            stats["errors"] += 1

    return stats


def migrate_documents(doc_repo: DocumentRepository, pg_service: PostgresService) -> Dict[str, int]:
    """
    Migrates documents from DynamoDB or local documents JSON store into PostgreSQL.
    """
    stats = {"scanned": 0, "inserted": 0, "errors": 0}
    docs: List[Dict[str, Any]] = []

    # 1. Try DynamoDB if configured
    if doc_repo.dynamodb.is_configured():
        try:
            logger.info(f"Scanning DynamoDB documents table '{doc_repo.dynamodb.table_name}'...")
            success, items, _ = doc_repo.dynamodb.list_documents()
            if success and items:
                docs = items
                logger.info(f"Retrieved {len(docs)} document(s) from DynamoDB.")
        except Exception as e:
            logger.warning(f"Failed to scan DynamoDB documents table: {e}. Falling back to local store.")

    # 2. Fall back to local documents store
    if not docs:
        logger.info("Reading documents from local storage...")
        docs = doc_repo._read_records()
        logger.info(f"Found {len(docs)} document(s) in local store.")

    stats["scanned"] = len(docs)

    # 3. Upsert documents into PostgreSQL
    for d in docs:
        try:
            res = pg_service.insert_document(d)
            if res.get("success"):
                stats["inserted"] += 1
            else:
                logger.warning(f"Failed to insert doc {d.get('doc_id')}: {res.get('message')}")
                stats["errors"] += 1
        except Exception as e:
            logger.error(f"Exception inserting doc {d.get('doc_id')}: {e}")
            stats["errors"] += 1

    return stats


def run_migration():
    """Main migration runner."""
    logger.info("=== Starting Migration to Supabase PostgreSQL ===")
    
    pg_service = PostgresService()
    if not pg_service.is_configured():
        logger.error(
            "PostgreSQL is not configured. Please set DATABASE_URL in your environment or .env file.\n"
            "Example: DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"
        )
        sys.exit(1)

    logger.info("Checking PostgreSQL connection...")
    conn_info = pg_service.check_connection()
    if not conn_info.get("accessible"):
        logger.error(f"Cannot reach PostgreSQL: {conn_info.get('error')}")
        sys.exit(1)

    logger.info("PostgreSQL connected successfully. Initializing schema tables...")
    init_res = pg_service.init_db()
    if not init_res.get("success"):
        logger.error(f"Failed to initialize PostgreSQL schema: {init_res.get('error')}")
        sys.exit(1)

    auth_service = AuthService()
    doc_repo = DocumentRepository()

    logger.info("Migrating Users...")
    user_stats = migrate_users(auth_service, pg_service)
    logger.info(f"User migration completed: {user_stats}")

    logger.info("Migrating Documents...")
    doc_stats = migrate_documents(doc_repo, pg_service)
    logger.info(f"Document migration completed: {doc_stats}")

    logger.info("=== Migration Completed Successfully ===")
    logger.info(
        f"Summary: Users inserted={user_stats['inserted']}, skipped/existing={user_stats['skipped_or_updated']}; "
        f"Documents inserted={doc_stats['inserted']}, errors={doc_stats['errors']}."
    )


if __name__ == "__main__":
    run_migration()
