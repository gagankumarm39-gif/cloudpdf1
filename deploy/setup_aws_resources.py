#!/usr/bin/env python3
"""
AWS Resource Verification and Initialization Script
Cloud-Based PDF Generation System - Milestone 7

Run this script once on your EC2 instance (or locally with AWS credentials)
to verify or create:
1. Amazon S3 Bucket: Private bucket with Block Public Access enabled.
2. Amazon DynamoDB Table: CloudPDFDocuments with UserDocIndex (user_id + created_at).
3. Amazon DynamoDB Table: CloudPDFUsers with EmailIndex (email).

Usage:
  python deploy/setup_aws_resources.py
"""
import os
import sys
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Load env variables if present
load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1").strip()
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "").strip()
DOCS_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "CloudPDFDocuments").strip()
USERS_TABLE_NAME = os.getenv("DYNAMODB_USERS_TABLE", "CloudPDFUsers").strip()


def verify_or_create_s3():
    print(f"\n[1/3] Checking Amazon S3 Bucket: '{S3_BUCKET_NAME}'...")
    if not S3_BUCKET_NAME:
        print("  [!] S3_BUCKET_NAME is not set. Skipping S3 setup.")
        return False

    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        s3.head_bucket(Bucket=S3_BUCKET_NAME)
        print(f"  [✓] Bucket '{S3_BUCKET_NAME}' exists and is accessible.")
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ["404", "NoSuchBucket"]:
            print(f"  [*] Bucket '{S3_BUCKET_NAME}' does not exist. Creating in region '{AWS_REGION}'...")
            try:
                if AWS_REGION == "us-east-1":
                    s3.create_bucket(Bucket=S3_BUCKET_NAME)
                else:
                    s3.create_bucket(
                        Bucket=S3_BUCKET_NAME,
                        CreateBucketConfiguration={"LocationConstraint": AWS_REGION}
                    )
                # Enforce Block Public Access
                s3.put_public_access_block(
                    Bucket=S3_BUCKET_NAME,
                    PublicAccessBlockConfiguration={
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True
                    }
                )
                print(f"  [✓] Bucket '{S3_BUCKET_NAME}' created with Public Access Block enabled.")
                return True
            except Exception as create_err:
                print(f"  [✗] Failed to create bucket: {create_err}")
                return False
        else:
            print(f"  [✗] Error checking S3 bucket: {e}")
            return False


def verify_or_create_docs_table():
    print(f"\n[2/3] Checking DynamoDB Documents Table: '{DOCS_TABLE_NAME}'...")
    client = boto3.client("dynamodb", region_name=AWS_REGION)
    try:
        desc = client.describe_table(TableName=DOCS_TABLE_NAME)
        status = desc["Table"]["TableStatus"]
        print(f"  [✓] Table '{DOCS_TABLE_NAME}' exists (Status: {status}).")

        # Verify UserDocIndex
        gsis = [g["IndexName"] for g in desc["Table"].get("GlobalSecondaryIndexes", [])]
        if "UserDocIndex" in gsis:
            print("  [✓] UserDocIndex GSI is present.")
        else:
            print("  [!] Warning: UserDocIndex GSI is missing. Adding index...")
            client.update_table(
                TableName=DOCS_TABLE_NAME,
                AttributeDefinitions=[
                    {"AttributeName": "user_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"}
                ],
                GlobalSecondaryIndexUpdates=[
                    {
                        "Create": {
                            "IndexName": "UserDocIndex",
                            "KeySchema": [
                                {"AttributeName": "user_id", "KeyType": "HASH"},
                                {"AttributeName": "created_at", "KeyType": "RANGE"}
                            ],
                            "Projection": {"ProjectionType": "ALL"}
                        }
                    }
                ]
            )
            print("  [✓] UserDocIndex GSI creation initiated.")
        return True
    except client.exceptions.ResourceNotFoundException:
        print(f"  [*] Table '{DOCS_TABLE_NAME}' not found. Creating table with UserDocIndex...")
        resource = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = resource.create_table(
            TableName=DOCS_TABLE_NAME,
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
        print(f"  [✓] Table '{DOCS_TABLE_NAME}' created successfully.")
        return True
    except Exception as e:
        print(f"  [✗] DynamoDB error on documents table: {e}")
        return False


def verify_or_create_users_table():
    print(f"\n[3/3] Checking DynamoDB Users Table: '{USERS_TABLE_NAME}'...")
    client = boto3.client("dynamodb", region_name=AWS_REGION)
    try:
        desc = client.describe_table(TableName=USERS_TABLE_NAME)
        status = desc["Table"]["TableStatus"]
        print(f"  [✓] Table '{USERS_TABLE_NAME}' exists (Status: {status}).")

        # Verify EmailIndex
        gsis = [g["IndexName"] for g in desc["Table"].get("GlobalSecondaryIndexes", [])]
        if "EmailIndex" in gsis:
            print("  [✓] EmailIndex GSI is present.")
        else:
            print("  [!] Warning: EmailIndex GSI is missing. Adding index...")
            client.update_table(
                TableName=USERS_TABLE_NAME,
                AttributeDefinitions=[
                    {"AttributeName": "email", "AttributeType": "S"}
                ],
                GlobalSecondaryIndexUpdates=[
                    {
                        "Create": {
                            "IndexName": "EmailIndex",
                            "KeySchema": [
                                {"AttributeName": "email", "KeyType": "HASH"}
                            ],
                            "Projection": {"ProjectionType": "ALL"}
                        }
                    }
                ]
            )
            print("  [✓] EmailIndex GSI creation initiated.")
        return True
    except client.exceptions.ResourceNotFoundException:
        print(f"  [*] Table '{USERS_TABLE_NAME}' not found. Creating table with EmailIndex...")
        resource = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = resource.create_table(
            TableName=USERS_TABLE_NAME,
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "email", "AttributeType": "S"}
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "EmailIndex",
                    "KeySchema": [
                        {"AttributeName": "email", "KeyType": "HASH"}
                    ],
                    "Projection": {"ProjectionType": "ALL"}
                }
            ],
            BillingMode="PAY_PER_REQUEST"
        )
        table.wait_until_exists()
        print(f"  [✓] Table '{USERS_TABLE_NAME}' created successfully.")
        return True
    except Exception as e:
        print(f"  [✗] DynamoDB error on users table: {e}")
        return False


def main():
    print("=" * 60)
    print(" CloudPDF System: AWS Infrastructure Verification")
    print(f" Region: {AWS_REGION}")
    print("=" * 60)

    try:
        s3_ok = verify_or_create_s3()
        docs_ok = verify_or_create_docs_table()
        users_ok = verify_or_create_users_table()

        print("\n" + "=" * 60)
        if s3_ok and docs_ok and users_ok:
            print(" [SUCCESS] All AWS Cloud resources are ready for production!")
        else:
            print(" [WARNING] Some resources could not be verified. Check IAM permissions.")
        print("=" * 60 + "\n")
    except NoCredentialsError:
        print("\n[✗] ERROR: No AWS credentials found.")
        print("Attach an EC2 IAM role with the CloudPDF policy or configure ~/.aws/credentials.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
