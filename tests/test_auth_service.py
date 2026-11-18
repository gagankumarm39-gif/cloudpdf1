# Test file for Milestone 6: User Authentication and Security
import os
import io
import pytest
from moto import mock_aws
from app import app
from services.auth_service import (
    AuthService,
    hash_password,
    verify_password,
    validate_email_format,
    validate_password_strength
)
from services.dynamodb_service import DynamoDBService
from services.document_repository import DocumentRepository

@pytest.fixture(autouse=True)
def clean_users_store(tmp_path, monkeypatch):
    test_store = str(tmp_path / 'test_users_metadata.json')
    monkeypatch.setattr('services.auth_service.USERS_METADATA_FILE', test_store)
    from app import auth_service
    auth_service.metadata_file = test_store
    auth_service._ensure_local_store()

def test_password_hashing_and_verification():
    raw_pwd = 'SecurePassword123'
    hashed = hash_password(raw_pwd)
    assert hashed != raw_pwd
    assert hashed.startswith('$') or hashed.startswith('$')
    assert verify_password(raw_pwd, hashed) is True
    assert verify_password('WrongPassword', hashed) is False
    assert verify_password('', hashed) is False

def test_validation_utilities():
    assert validate_email_format('user@example.com') is True
    assert validate_email_format('student.name+test@university.edu') is True
    assert validate_email_format('invalid-email') is False
    assert validate_email_format('@missinguser.com') is False
    assert validate_email_format('missingdomain@') is False

    valid, err = validate_password_strength('Pass1234')
    assert valid is True
    assert err is None

    valid, err = validate_password_strength('short1')
    assert valid is False
    assert '8 characters' in err

    valid, err = validate_password_strength('alllowercaseletters')
    assert valid is False
    assert 'number' in err

    valid, err = validate_password_strength('12345678')
    assert valid is False
    assert 'letter' in err

def test_auth_service_local_fallback(tmp_path):
    metadata_file = str(tmp_path / 'users.json')
    service = AuthService(table_name='')
    service.metadata_file = metadata_file
    service._ensure_local_store()

    demo_user = service.get_user_by_email('kavya@cloudpdf.edu')
    assert demo_user is not None
    assert demo_user.user_id == 'USER-DEMO-001'

    user, err = service.register_user('Alice Wonder', 'alice@test.com', 'WonderPass1')
    assert err is None
    assert user is not None
    assert user.email == 'alice@test.com'

    dup_user, dup_err = service.register_user('Duplicate Alice', 'alice@test.com', 'WonderPass2')
    assert dup_user is None
    assert 'already exists' in dup_err

    auth_user, auth_err = service.authenticate_user('alice@test.com', 'WonderPass1')
    assert auth_err is None
    assert auth_user.user_id == user.user_id

    fail_user, fail_err = service.authenticate_user('alice@test.com', 'WrongPass')
    assert fail_user is None
    assert 'Invalid email or password' in fail_err

@mock_aws
def test_dynamodb_users_table_integration(tmp_path):
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    os.environ['AWS_ACCESS_KEY_ID'] = 'mock-key'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'mock-secret'

    auth_svc = AuthService(table_name='CloudPDFUsers', region_name='us-east-1')
    auth_svc.metadata_file = str(tmp_path / 'users_dynamo.json')
    auth_svc._ensure_local_store()

    init_res = auth_svc.create_table_if_not_exists()
    assert init_res['success'] is True

    user, err = auth_svc.register_user('Bob Cloud', 'bob@cloud.com', 'CloudPass123')
    assert err is None
    assert user is not None

    by_id = auth_svc.get_user_by_id(user.user_id)
    assert by_id is not None
    assert by_id.email == 'bob@cloud.com'

    by_email = auth_svc.get_user_by_email('bob@cloud.com')
    assert by_email is not None
    assert by_email.user_id == user.user_id

    authed, auth_err = auth_svc.authenticate_user('bob@cloud.com', 'CloudPass123')
    assert auth_err is None
    assert authed.user_id == user.user_id

def test_login_logout_web_flow():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Login' in resp.data

    login_resp = client.post('/login', data={
        'email': 'kavya@cloudpdf.edu',
        'password': 'Password123'
    }, follow_redirects=True)
    assert login_resp.status_code == 200
    assert b'Kavya M' in login_resp.data
    assert b'Logout' in login_resp.data

    logout_resp = client.get('/logout', follow_redirects=True)
    assert logout_resp.status_code == 200
    assert b'signed out' in logout_resp.data

def test_document_ownership_and_cross_user_isolation():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    reg_a = client.post('/register', data={
        'name': 'User A',
        'email': 'new_user_a@test.com',
        'password': 'PasswordA123',
        'confirm_password': 'PasswordA123'
    }, follow_redirects=True)
    assert reg_a.status_code == 200

    gen_resp = client.post('/api/generate-pdf?download=false', json={
        'title': 'User A Secret Document',
        'author': 'User A',
        'description': 'Classified data',
        'content': 'Confidential report content for User A.'
    })
    assert gen_resp.status_code == 201
    doc_a_id = gen_resp.get_json()['document']['id']

    doc_detail = client.get(f'/api/documents/{doc_a_id}')
    assert doc_detail.status_code == 200

    client.get('/logout', follow_redirects=True)

    reg_b = client.post('/register', data={
        'name': 'User B',
        'email': 'new_user_b@test.com',
        'password': 'PasswordB123',
        'confirm_password': 'PasswordB123'
    }, follow_redirects=True)
    assert reg_b.status_code == 200

    b_docs_resp = client.get('/api/documents')
    assert b_docs_resp.status_code == 200
    b_doc_ids = [d['id'] for d in b_docs_resp.get_json()['documents']]
    assert doc_a_id not in b_doc_ids

    detail_resp = client.get(f'/api/documents/{doc_a_id}')
    assert detail_resp.status_code == 403
    assert 'Access Denied' in detail_resp.get_json()['error']

    preview_resp = client.get(f'/api/documents/{doc_a_id}/preview')
    assert preview_resp.status_code == 403

    download_resp = client.get(f'/api/documents/{doc_a_id}/download')
    assert download_resp.status_code == 403

    delete_resp = client.delete(f'/api/documents/{doc_a_id}')
    assert delete_resp.status_code == 403
