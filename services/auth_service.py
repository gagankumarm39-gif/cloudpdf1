"""
Authentication and User Management Service
Cloud-Based PDF Generation System - Milestone 6

Handles:
- User registration with email validation and bcrypt password hashing
- Password verification using constant-time comparison
- Flask-Login User model integration
- DynamoDB CloudPDFUsers table integration with local JSON storage fallback
- Email uniqueness enforcement
"""
import os
import re
import json
import uuid
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import bcrypt
from flask_login import UserMixin
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
from services.postgres_service import PostgresService

logger = logging.getLogger(__name__)

USERS_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
USERS_METADATA_FILE = os.path.join(USERS_STORAGE_DIR, "users_metadata.json")
DEFAULT_USERS_TABLE_NAME = "CloudPDFUsers"


class User(UserMixin):
    """
    Flask-Login User Model.
    """
    def __init__(self, user_id: str, name: str, email: str, is_active: bool = True):
        self.id = user_id
        self.user_id = user_id
        self.name = name
        self.email = email
        self._is_active = is_active

    @property
    def is_active(self):
        return self._is_active

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email,
            "is_active": self._is_active
        }


def hash_password(password: str) -> str:
    """Hash password securely using bcrypt with work factor salt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash in constant time."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def validate_email_format(email: str) -> bool:
    """Validate RFC-compliant email address structure."""
    if not email or len(email) > 254:
        return False
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email.strip()))


def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
    """Enforce minimum 8 characters with at least one number and one letter."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    return True, None


class AuthService:
    """
    Service managing user accounts, authentication, and DynamoDB CloudPDFUsers table.
    """
    def __init__(
        self,
        table_name: Optional[str] = None,
        region_name: Optional[str] = None,
        postgres_service: Optional[PostgresService] = None
    ):
        if table_name is not None:
            self.table_name = table_name.strip()
        else:
            self.table_name = os.getenv("DYNAMODB_USERS_TABLE", "").strip()

        if region_name is not None:
            self.region_name = region_name.strip()
        else:
            self.region_name = os.getenv("AWS_REGION", "us-east-1").strip()

        self.postgres = postgres_service or PostgresService()
        self.metadata_file = USERS_METADATA_FILE
        self._lock = threading.Lock()
        self._dynamodb_resource = None
        self._dynamodb_client = None
        self._config = Config(
            region_name=self.region_name,
            retries={"max_attempts": 3, "mode": "standard"}
        )
        self._ensure_local_store()

    def is_postgres_configured(self) -> bool:
        """True if PostgreSQL DATABASE_URL is configured."""
        return self.postgres.is_configured()

    def is_dynamodb_configured(self) -> bool:
        """True if DYNAMODB_USERS_TABLE is set in environment or explicitly passed."""
        return bool(self.table_name)

    def check_connection(self) -> Dict[str, Any]:
        """
        Actively checks connection to configured database (Postgres priority, DynamoDB fallback).
        """
        if self.is_postgres_configured():
            return self.postgres.check_connection()

        if not self.is_dynamodb_configured():
            return {
                "configured": False,
                "accessible": False,
                "status": "unconfigured",
                "table": None
            }
        try:
            desc = self.client.describe_table(TableName=self.table_name)
            return {
                "configured": True,
                "accessible": True,
                "status": "connected",
                "table": self.table_name,
                "table_status": desc.get("Table", {}).get("TableStatus", "UNKNOWN"),
                "region": self.region_name
            }
        except Exception as e:
            logger.warning(f"DynamoDB users health check probe failed for table '{self.table_name}': {e}")
            return {
                "configured": True,
                "accessible": False,
                "status": "unreachable",
                "table": self.table_name,
                "error": str(e)
            }

    @property
    def resource(self):
        if self._dynamodb_resource is None:
            self._dynamodb_resource = boto3.resource("dynamodb", config=self._config)
        return self._dynamodb_resource

    @property
    def client(self):
        if self._dynamodb_client is None:
            self._dynamodb_client = boto3.client("dynamodb", config=self._config)
        return self._dynamodb_client

    @property
    def table(self):
        return self.resource.Table(self.table_name)

    def _ensure_local_store(self):
        """Ensures local user metadata store exists with default demo user."""
        os.makedirs(os.path.dirname(self.metadata_file), exist_ok=True)
        if not os.path.exists(self.metadata_file):
            default_demo = [
                {
                    "user_id": "USER-DEMO-001",
                    "name": "Kavya M",
                    "email": "kavya@cloudpdf.edu",
                    "password_hash": hash_password("Password123"),
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "is_active": True
                }
            ]
            self._write_local_users(default_demo)

    def _read_local_users(self) -> list:
        try:
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_local_users(self, users: list):
        temp_file = self.metadata_file + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        os.replace(temp_file, self.metadata_file)

    def create_table_if_not_exists(self) -> Dict[str, Any]:
        """
        Creates the CloudPDFUsers DynamoDB table with user_id as PK and EmailIndex GSI.
        """
        if not self.is_dynamodb_configured():
            return {"success": False, "error": "DYNAMODB_NOT_CONFIGURED"}

        try:
            existing = self.client.list_tables().get("TableNames", [])
            if self.table_name in existing:
                return {"success": True, "message": f"Table '{self.table_name}' already exists."}

            table = self.resource.create_table(
                TableName=self.table_name,
                KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "user_id", "AttributeType": "S"},
                    {"AttributeName": "email", "AttributeType": "S"}
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "EmailIndex",
                        "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                        "Projection": {"ProjectionType": "ALL"}
                    }
                ],
                BillingMode="PAY_PER_REQUEST"
            )
            table.wait_until_exists()
            return {"success": True, "message": f"Table '{self.table_name}' created."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def register_user(self, name: str, email: str, password: str) -> Tuple[Optional[User], Optional[str]]:
        """
        Registers a new user, hashes the password, and prevents duplicate emails.
        Returns: (User, None) on success or (None, error_message) on failure.
        """
        name = name.strip()
        email = email.strip().lower()

        if not name:
            return None, "Full name is required."
        if not validate_email_format(email):
            return None, "Please enter a valid email address."

        valid_pw, pw_err = validate_password_strength(password)
        if not valid_pw:
            return None, pw_err

        # Check duplicate email
        existing_user = self.get_user_by_email(email)
        if existing_user:
            return None, "An account with this email address already exists."

        user_id = f"USER-{uuid.uuid4().hex[:8].upper()}"
        pw_hash = hash_password(password)
        created_at = datetime.utcnow().isoformat() + "Z"

        record = {
            "user_id": user_id,
            "name": name,
            "email": email,
            "password_hash": pw_hash,
            "created_at": created_at,
            "is_active": True
        }

        # 1. PostgreSQL insertion if configured (Milestone 9 priority)
        if self.is_postgres_configured():
            pg_user, pg_err = self.postgres.create_user(
                user_id=user_id,
                name=name,
                email=email,
                password_hash=pw_hash
            )
            if pg_err:
                logger.warning(f"Postgres user creation warning: {pg_err}")
                if "already exists" in str(pg_err):
                    return None, "An account with this email address already exists."

        # 2. DynamoDB insertion if configured (Milestone 6 compatibility)
        if self.is_dynamodb_configured():
            try:
                self.table.put_item(
                    Item=record,
                    ConditionExpression="attribute_not_exists(user_id)"
                )
            except ClientError as e:
                logger.error(f"DynamoDB register user error: {e}")
                # Fall back to local store if DynamoDB is unavailable

        # 3. Sync to local JSON store
        with self._lock:
            users = self._read_local_users()
            users.append(record)
            self._write_local_users(users)

        user_obj = User(user_id=user_id, name=name, email=email, is_active=True)
        return user_obj, None

    def authenticate_user(self, email: str, password: str) -> Tuple[Optional[User], Optional[str]]:
        """
        Authenticates credentials against stored bcrypt hash.
        Returns: (User, None) on success or (None, error_message) on failure.
        """
        email = email.strip().lower()
        if not email or not password:
            return None, "Email and password are required."

        user_record = self._get_user_record_by_email(email)
        if not user_record:
            return None, "Invalid email or password."

        stored_hash = user_record.get("password_hash", "")
        if not verify_password(password, stored_hash):
            return None, "Invalid email or password."

        if not user_record.get("is_active", True):
            return None, "This account is inactive. Please contact administrator."

        user_obj = User(
            user_id=user_record["user_id"],
            name=user_record["name"],
            email=user_record["email"],
            is_active=user_record.get("is_active", True)
        )
        return user_obj, None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Loads User object by user_id for Flask-Login."""
        # 1. Try PostgreSQL (Milestone 9 priority)
        if self.is_postgres_configured():
            u_dict = self.postgres.get_user_by_id(user_id)
            if u_dict:
                return User(
                    user_id=u_dict["user_id"],
                    name=u_dict["name"],
                    email=u_dict["email"],
                    is_active=u_dict.get("is_active", True)
                )

        # 2. Try DynamoDB
        if self.is_dynamodb_configured():
            try:
                res = self.table.get_item(Key={"user_id": user_id})
                item = res.get("Item")
                if item:
                    return User(
                        user_id=item["user_id"],
                        name=item["name"],
                        email=item["email"],
                        is_active=item.get("is_active", True)
                    )
            except Exception:
                pass

        # 3. Fallback to local store
        with self._lock:
            for u in self._read_local_users():
                if u.get("user_id") == user_id:
                    return User(
                        user_id=u["user_id"],
                        name=u["name"],
                        email=u["email"],
                        is_active=u.get("is_active", True)
                    )
        return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Finds user by email address."""
        rec = self._get_user_record_by_email(email)
        if rec:
            return User(
                user_id=rec["user_id"],
                name=rec["name"],
                email=rec["email"],
                is_active=rec.get("is_active", True)
            )
        return None

    def _get_user_record_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        email = email.strip().lower()

        # 1. Try PostgreSQL (Milestone 9 priority)
        if self.is_postgres_configured():
            u_dict = self.postgres.get_user_by_email(email)
            if u_dict:
                return u_dict

        # 2. Try DynamoDB EmailIndex query or scan
        if self.is_dynamodb_configured():
            try:
                # Query GSI if available
                res = self.table.query(
                    IndexName="EmailIndex",
                    KeyConditionExpression="email = :e",
                    ExpressionAttributeValues={":e": email}
                )
                items = res.get("Items", [])
                if items:
                    return items[0]
            except Exception:
                # Fallback to scan in DynamoDB if index is initializing
                try:
                    res = self.table.scan(
                        FilterExpression="email = :e",
                        ExpressionAttributeValues={":e": email}
                    )
                    items = res.get("Items", [])
                    if items:
                        return items[0]
                except Exception:
                    pass

        # 3. Local store search
        with self._lock:
            for u in self._read_local_users():
                if u.get("email", "").lower() == email:
                    return u
        return None
