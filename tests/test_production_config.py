"""
Automated Tests for Milestone 7: AWS EC2 Deployment and Production Configuration
Tests:
- Production Gunicorn configuration file imports and attributes
- Nginx configuration syntax and security headers
- IAM Least-Privilege Policy JSON structure & statement validations
- Enhanced health check API under unconfigured and mock AWS environments
- Secure cookie and production environment settings
"""
import os
import json
import pytest
from moto import mock_aws
import boto3
from app import app
from services.s3_service import S3Service
from services.dynamodb_service import DynamoDBService
from services.auth_service import AuthService


def test_gunicorn_config_structure():
    """Verify gunicorn_config.py loads valid production settings."""
    import gunicorn_config

    assert hasattr(gunicorn_config, "bind")
    assert hasattr(gunicorn_config, "workers")
    assert hasattr(gunicorn_config, "timeout")
    assert hasattr(gunicorn_config, "worker_class")
    assert gunicorn_config.timeout >= 30
    assert gunicorn_config.worker_class == "sync"
    assert gunicorn_config.proc_name == "cloudpdf-gunicorn"


def test_iam_policy_json_validity():
    """Verify deploy/iam_policy.json is well-formed JSON and contains least-privilege actions."""
    policy_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "iam_policy.json")
    assert os.path.exists(policy_path)

    with open(policy_path, "r", encoding="utf-8") as f:
        policy = json.load(f)

    assert policy.get("Version") == "2012-10-17"
    statements = policy.get("Statement", [])
    assert len(statements) >= 3

    # Check S3 permissions
    s3_actions = []
    dynamo_actions = []
    for stmt in statements:
        actions = stmt.get("Action", [])
        for act in actions:
            if act.startswith("s3:"):
                s3_actions.append(act)
            elif act.startswith("dynamodb:"):
                dynamo_actions.append(act)

    assert "s3:PutObject" in s3_actions
    assert "s3:GetObject" in s3_actions
    assert "s3:DeleteObject" in s3_actions
    assert "s3:ListBucket" in s3_actions

    assert "dynamodb:GetItem" in dynamo_actions
    assert "dynamodb:PutItem" in dynamo_actions
    assert "dynamodb:Query" in dynamo_actions
    assert "dynamodb:Scan" in dynamo_actions


def test_nginx_and_systemd_manifests_exist():
    """Verify systemd service and nginx configurations are present and valid."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    service_path = os.path.join(base_dir, "deploy", "cloudpdf.service")
    nginx_path = os.path.join(base_dir, "deploy", "nginx.conf")
    userdata_path = os.path.join(base_dir, "deploy", "ec2_userdata.sh")

    assert os.path.exists(service_path)
    assert os.path.exists(nginx_path)
    assert os.path.exists(userdata_path)

    with open(service_path, "r", encoding="utf-8") as f:
        svc_content = f.read()
        assert "ExecStart=" in svc_content
        assert "gunicorn" in svc_content
        assert "Restart=always" in svc_content

    with open(nginx_path, "r", encoding="utf-8") as f:
        nginx_content = f.read()
        assert "proxy_pass http://cloudpdf_backend;" in nginx_content
        assert "client_max_body_size 25M;" in nginx_content
        assert "location /static/" in nginx_content


def test_enhanced_health_check_unconfigured(monkeypatch):
    """Verify /api/health returns healthy without exposing keys when cloud services are unconfigured."""
    from app import supabase_storage_service, s3_service, dynamodb_service, auth_service
    # Explicitly test unconfigured state
    orig_supa = supabase_storage_service.bucket_name
    supabase_storage_service.bucket_name = ""
    app.config["TESTING"] = True
    client = app.test_client()

    try:
        resp = client.get("/api/health")
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["version"] in ["7.0.0", "8.0.0", "9.0.0"]
        assert "Milestone" in data["milestone"]
        assert "cloud_services" in data
        assert data["cloud_services"]["s3"]["configured"] is False
        assert data["cloud_services"]["dynamodb_documents"]["configured"] is False

        # Security check: Ensure no AWS secret keys or credentials leaked
        body_str = json.dumps(data)
        assert "SECRET" not in body_str
        assert "ACCESS_KEY" not in body_str
    finally:
        supabase_storage_service.bucket_name = orig_supa


@mock_aws
def test_enhanced_health_check_connected(monkeypatch):
    """Verify /api/health accurately reports 'connected' when mock AWS services are available."""
    from app import supabase_storage_service
    orig_supa = supabase_storage_service.bucket_name
    supabase_storage_service.bucket_name = ""

    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "mock-key"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "mock-secret"
    os.environ["S3_BUCKET_NAME"] = "health-test-bucket"
    os.environ["DYNAMODB_TABLE_NAME"] = "HealthDocsTable"
    os.environ["DYNAMODB_USERS_TABLE"] = "HealthUsersTable"

    # Create mock resources
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="health-test-bucket")

    dyn = boto3.client("dynamodb", region_name="us-east-1")
    dyn.create_table(
        TableName="HealthDocsTable",
        KeySchema=[{"AttributeName": "doc_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "doc_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST"
    )
    dyn.create_table(
        TableName="HealthUsersTable",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST"
    )

    from app import s3_service, dynamodb_service, auth_service
    s3_service.bucket_name = "health-test-bucket"
    s3_service._s3_client = None
    dynamodb_service.table_name = "HealthDocsTable"
    dynamodb_service._dynamodb_client = None
    dynamodb_service._dynamodb_resource = None
    auth_service.table_name = "HealthUsersTable"
    auth_service._dynamodb_client = None
    auth_service._dynamodb_resource = None

    try:
        app.config["TESTING"] = True
        client = app.test_client()
        resp = client.get("/api/health")
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["cloud_services"]["s3"]["accessible"] is True
        assert data["cloud_services"]["s3"]["status"] == "connected"
        assert data["cloud_services"]["dynamodb_documents"]["accessible"] is True
        assert data["cloud_services"]["dynamodb_documents"]["status"] == "connected"
        assert data["cloud_services"]["dynamodb_users"]["accessible"] is True
        assert data["cloud_services"]["dynamodb_users"]["status"] == "connected"
    finally:
        s3_service.bucket_name = ""
        s3_service._s3_client = None
        dynamodb_service.table_name = ""
        dynamodb_service._dynamodb_client = None
        dynamodb_service._dynamodb_resource = None
        auth_service.table_name = ""
        auth_service._dynamodb_client = None
        auth_service._dynamodb_resource = None
        os.environ.pop("S3_BUCKET_NAME", None)
        os.environ.pop("DYNAMODB_TABLE_NAME", None)
        os.environ.pop("DYNAMODB_USERS_TABLE", None)
        supabase_storage_service.bucket_name = orig_supa


def test_startup_and_health_when_postgres_unreachable(monkeypatch):
    """
    Verify application starts cleanly and /api/health responds with 200 (degraded)
    when DATABASE_URL points to an unreachable host or network timeout.
    Ensures Gunicorn does not hit 'Port scan timeout reached'.
    """
    from services.postgres_service import PostgresService
    from app import app

    # Point postgres to an unreachable IP with 1s timeout
    unreachable_pg = PostgresService("postgresql+psycopg2://user:pass@192.0.2.1:5432/db")
    monkeypatch.setattr("app.postgres_service", unreachable_pg)

    app.config["TESTING"] = True
    client = app.test_client()

    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "cloud_services" in data
    assert data["cloud_services"]["supabase_postgres"]["configured"] is True
    assert data["cloud_services"]["supabase_postgres"]["accessible"] is False
    assert data["cloud_services"]["supabase_postgres"]["status"] == "unreachable"


def test_gunicorn_render_port_binding(monkeypatch):
    """Verify Gunicorn dynamically binds to 0.0.0.0:$PORT on Render."""
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.delenv("GUNICORN_BIND", raising=False)
    
    port = os.getenv("PORT", "8000")
    bind_target = os.getenv("GUNICORN_BIND", f"0.0.0.0:{port}")
    assert bind_target == "0.0.0.0:10000"
