"""
Amazon DynamoDB Metadata Service
Cloud-Based PDF Generation System - Milestone 5

Table Name: CloudPDFDocuments
Primary Key: doc_id (String)

Attributes:
- doc_id: Primary key (e.g. "DOC-1234")
- title: Document Title
- author: Author Name
- description: Document Description / Abstract
- filename: Original sanitized filename
- s3_key: Amazon S3 object key
- file_size: Human-readable file size (e.g. "2.7 KB")
- size_bytes: Numeric size in bytes
- created_at: ISO 8601 formatted timestamp
- storage_type: "s3_and_local" or "s3" or "local"
- content_type: "application/pdf"
- status: Document status ("Ready")
"""
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = logging.getLogger(__name__)

DEFAULT_TABLE_NAME = "CloudPDFDocuments"


class DynamoDBService:
    """
    Dedicated Service for managing document metadata inside Amazon DynamoDB.
    Uses Boto3 credential provider chain (IAM role, profile, or env vars).
    """
    def __init__(self, table_name: Optional[str] = None, region_name: Optional[str] = None):
        if table_name is not None:
            self.table_name = table_name.strip()
        else:
            self.table_name = os.getenv("DYNAMODB_TABLE_NAME", "").strip()


        if region_name is not None:
            self.region_name = region_name.strip()
        else:
            self.region_name = os.getenv("AWS_REGION", "us-east-1").strip()

        self._dynamodb_resource = None
        self._dynamodb_client = None
        self._config = Config(
            region_name=self.region_name,
            retries={"max_attempts": 3, "mode": "standard"}
        )

    def is_configured(self) -> bool:
        """Checks whether DynamoDB table name is configured."""
        return bool(self.table_name)

    def check_connection(self) -> Dict[str, Any]:
        """
        Actively checks connection to configured Amazon DynamoDB table using describe_table.
        Returns detailed status for health check probes.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "accessible": False,
                "status": "unconfigured",
                "table": None
            }
        try:
            desc = self.client.describe_table(TableName=self.table_name)
            table_status = desc.get("Table", {}).get("TableStatus", "UNKNOWN")
            return {
                "configured": True,
                "accessible": True,
                "status": "connected",
                "table": self.table_name,
                "table_status": table_status,
                "region": self.region_name
            }
        except Exception as e:
            logger.warning(f"DynamoDB health check probe failed for table '{self.table_name}': {e}")
            return {
                "configured": True,
                "accessible": False,
                "status": "unreachable",
                "table": self.table_name,
                "error": str(e)
            }

    @property
    def resource(self):
        """Lazy-loaded boto3 dynamodb resource."""
        if self._dynamodb_resource is None:
            self._dynamodb_resource = boto3.resource("dynamodb", config=self._config)
        return self._dynamodb_resource

    @property
    def client(self):
        """Lazy-loaded boto3 dynamodb client."""
        if self._dynamodb_client is None:
            self._dynamodb_client = boto3.client("dynamodb", config=self._config)
        return self._dynamodb_client

    @property
    def table(self):
        """Returns the Boto3 Table resource."""
        return self.resource.Table(self.table_name)

    def create_table_if_not_exists(self) -> Dict[str, Any]:
        """
        Creates or initializes the CloudPDFDocuments table if it doesn't already exist.
        Schema:
          - Partition Key: doc_id (String)
          - BillingMode: PAY_PER_REQUEST (On-Demand)
        """
        if not self.is_configured():
            return {"success": False, "error": "DYNAMODB_NOT_CONFIGURED"}

        try:
            # Check if table exists
            existing_tables = self.client.list_tables().get("TableNames", [])
            if self.table_name in existing_tables:
                return {"success": True, "message": f"Table '{self.table_name}' already exists."}

            table = self.resource.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {"AttributeName": "doc_id", "KeyType": "HASH"}
                ],
                AttributeDefinitions=[
                    {"AttributeName": "doc_id", "AttributeType": "S"},
                    {"AttributeName": "user_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"}
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "UserDocIndex",
                        "KeySchema": [
                            {"AttributeName": "user_id", "KeyType": "HASH"},
                            {"AttributeName": "created_at", "KeyType": "RANGE"}
                        ],
                        "Projection": {"ProjectionType": "ALL"}
                    }
                ],
                BillingMode="PAY_PER_REQUEST"
            )
            table.wait_until_exists()
            return {"success": True, "message": f"Table '{self.table_name}' created successfully."}
        except NoCredentialsError:
            return {"success": False, "error": "NO_CREDENTIALS", "message": "AWS credentials not found."}
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            if error_code == "ResourceInUseException":
                return {"success": True, "message": f"Table '{self.table_name}' already exists."}
            return {"success": False, "error": error_code, "message": str(e)}
        except Exception as e:
            return {"success": False, "error": "TABLE_CREATION_FAILED", "message": str(e)}

    def insert_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts document metadata record into DynamoDB.
        Ensures all standard attributes and user ownership attributes are populated.
        """
        if not self.is_configured():
            return {"success": False, "error": "DYNAMODB_NOT_CONFIGURED"}

        doc_id = document.get("doc_id") or document.get("id")
        if not doc_id:
            return {"success": False, "error": "MISSING_DOC_ID", "message": "Document must contain a doc_id."}

        # Normalize created_at to ISO 8601 if needed
        created_at = document.get("created_at")
        if not created_at or "T" not in created_at:
            created_at = datetime.utcnow().isoformat() + "Z"

        item = {
            "doc_id": doc_id,
            "user_id": str(document.get("user_id", "USER-ANONYMOUS")).strip(),
            "title": str(document.get("title", "")).strip(),
            "author": str(document.get("author", "")).strip(),
            "description": str(document.get("description", "")).strip(),
            "filename": str(document.get("filename", "")).strip(),
            "s3_key": str(document.get("s3_key", "")).strip(),
            "file_size": str(document.get("size") or document.get("file_size", "0 KB")).strip(),
            "size_bytes": int(document.get("size_bytes", 0)),
            "created_at": created_at,
            "storage_type": str(document.get("storage_type", "s3_and_local")),
            "content_type": "application/pdf",
            "status": str(document.get("status", "Ready"))
        }

        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(doc_id)"
            )
            return {"success": True, "item": item}
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            logger.error(f"DynamoDB put_item error: {error_code} - {error_msg}")
            return {"success": False, "error": error_code, "message": error_msg}
        except Exception as e:
            logger.error(f"Unexpected error writing to DynamoDB: {str(e)}")
            return {"success": False, "error": "INSERT_FAILED", "message": str(e)}

    def get_document(self, doc_id: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Retrieves a document by its doc_id from DynamoDB.
        Returns (success, item, error_message).
        """
        if not self.is_configured():
            return False, None, "DYNAMODB_NOT_CONFIGURED"

        try:
            response = self.table.get_item(Key={"doc_id": doc_id})
            item = response.get("Item")
            if not item:
                return False, None, f"Document '{doc_id}' not found."
            item["id"] = item["doc_id"]
            return True, item, None
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            return False, None, f"DynamoDB Error: {error_code}"
        except Exception as e:
            return False, None, str(e)

    def list_documents(
        self,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "date",
        order: str = "desc"
    ) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
        """
        Lists documents from DynamoDB.
        When user_id is provided, queries the UserDocIndex GSI for user-isolated access.
        """
        if not self.is_configured():
            return False, [], "DYNAMODB_NOT_CONFIGURED"

        items = []
        try:
            # 1. Query by UserDocIndex GSI if user_id is provided
            if user_id:
                try:
                    res = self.table.query(
                        IndexName="UserDocIndex",
                        KeyConditionExpression="user_id = :uid",
                        ExpressionAttributeValues={":uid": user_id},
                        ScanIndexForward=(order.lower() == "asc")
                    )
                    items = res.get("Items", [])
                except Exception:
                    # Fallback to scan with FilterExpression
                    res = self.table.scan(
                        FilterExpression="user_id = :uid",
                        ExpressionAttributeValues={":uid": user_id}
                    )
                    items = res.get("Items", [])
            else:
                # Scan all
                res = self.table.scan()
                items = res.get("Items", [])
                while "LastEvaluatedKey" in res:
                    res = self.table.scan(ExclusiveStartKey=res["LastEvaluatedKey"])
                    items.extend(res.get("Items", []))

            # Normalize "id" key and migrate older records without user_id
            for it in items:
                it["id"] = it["doc_id"]
                it["size"] = it.get("file_size", "0 KB")
                if "user_id" not in it:
                    it["user_id"] = "USER-DEMO-001"

            # Search filter
            if search and search.strip():
                query = search.strip().lower()
                items = [
                    it for it in items
                    if query in it.get("title", "").lower()
                    or query in it.get("author", "").lower()
                    or query in it.get("doc_id", "").lower()
                ]

            # Sorting
            reverse = (order.lower() == "desc")
            if sort_by == "date":
                items.sort(key=lambda x: x.get("created_at", ""), reverse=reverse)
            elif sort_by == "title":
                items.sort(key=lambda x: x.get("title", "").lower(), reverse=reverse)
            elif sort_by == "size":
                items.sort(key=lambda x: int(x.get("size_bytes", 0)), reverse=reverse)

            return True, items, None
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            return False, [], f"DynamoDB Error: {error_code}"
        except Exception as e:
            return False, [], str(e)


    def update_document(self, doc_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates metadata attributes of an existing document in DynamoDB.
        """
        if not self.is_configured():
            return {"success": False, "error": "DYNAMODB_NOT_CONFIGURED"}

        update_expr = []
        expr_names = {}
        expr_values = {}

        for k, v in updates.items():
            if k == "doc_id":
                continue
            placeholder_name = f"#{k}"
            placeholder_val = f":{k}"
            update_expr.append(f"{placeholder_name} = {placeholder_val}")
            expr_names[placeholder_name] = k
            expr_values[placeholder_val] = v

        if not update_expr:
            return {"success": True, "message": "No updates specified."}

        try:
            self.table.update_item(
                Key={"doc_id": doc_id},
                UpdateExpression="SET " + ", ".join(update_expr),
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ConditionExpression="attribute_exists(doc_id)"
            )
            return {"success": True, "doc_id": doc_id}
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            return {"success": False, "error": error_code, "message": str(e)}

    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """
        Deletes document metadata record from DynamoDB.
        """
        if not self.is_configured():
            return {"success": False, "error": "DYNAMODB_NOT_CONFIGURED"}

        try:
            self.table.delete_item(Key={"doc_id": doc_id})
            return {"success": True, "deleted_id": doc_id}
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "ClientError")
            return {"success": False, "error": error_code, "message": str(e)}
        except Exception as e:
            return {"success": False, "error": "DELETE_FAILED", "message": str(e)}

    def document_exists(self, doc_id: str) -> bool:
        """Checks if a document exists in DynamoDB."""
        success, item, _ = self.get_document(doc_id)
        return success and (item is not None)
