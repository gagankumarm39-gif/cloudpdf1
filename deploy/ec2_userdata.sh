#!/usr/bin/env bash
# ==============================================================================
# Amazon EC2 User Data / Cloud-Init Script
# Cloud-Based PDF Generation System - Milestone 7
#
# Supported Operating Systems:
# - Amazon Linux 2023 (Default recommended)
# - Ubuntu 22.04 LTS
# ==============================================================================

set -euo pipefail

echo "==> [CloudPDF] Starting EC2 Instance Provisioning..."

APP_DIR="/opt/cloudpdfgenerator"
CONF_DIR="/etc/cloudpdf"
APP_USER="ec2-user"

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME=$ID
else
    OS_NAME="unknown"
fi

echo "==> [CloudPDF] Detected OS: ${OS_NAME}"

# 1. Update system packages & install base dependencies
if [[ "${OS_NAME}" == "amzn" || "${OS_NAME}" == "al2023" ]]; then
    dnf update -y
    dnf install -y python3.12 python3.12-pip python3.12-devel git nginx gcc libffi-devel
elif [[ "${OS_NAME}" == "ubuntu" || "${OS_NAME}" == "debian" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv git nginx gcc libffi-dev build-essential
    APP_USER="ubuntu"
fi

# 2. Prepare Application Directory
echo "==> [CloudPDF] Setting up application path at ${APP_DIR}..."
mkdir -p "${APP_DIR}"
mkdir -p "${CONF_DIR}"
mkdir -p "/var/log/cloudpdf"
chown -R ${APP_USER}:${APP_USER} "/var/log/cloudpdf"

# 3. Create Python Virtual Environment
echo "==> [CloudPDF] Initializing Python Virtual Environment..."
if [ ! -d "${APP_DIR}/venv" ]; then
    python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/pip" install --upgrade pip setuptools wheel

# 4. Clone or pull project code if repository URL is provided
# (Replace REPO_URL with your GitHub/CodeCommit repo)
if [ ! -f "${APP_DIR}/app.py" ]; then
    echo "==> [CloudPDF] Note: Clone your application repository into ${APP_DIR} or deploy via SCP/CI-CD."
fi

# 5. Prepare Default Environment File
if [ ! -f "${CONF_DIR}/cloudpdf.env" ]; then
    cat <<EOF > "${CONF_DIR}/cloudpdf.env"
# Cloud-Based PDF Generation System - Production Environment
FLASK_ENV=production
FLASK_DEBUG=false
SECRET_KEY=$(head -c 32 /dev/urandom | base64)
SESSION_COOKIE_SECURE_ENABLED=false

# AWS Cloud Integration (Uses IAM Instance Role for credentials)
AWS_REGION=us-east-1
S3_BUCKET_NAME=my-cloud-pdf-bucket
DYNAMODB_TABLE_NAME=CloudPDFDocuments
DYNAMODB_USERS_TABLE=CloudPDFUsers

# Gunicorn Settings
GUNICORN_BIND=127.0.0.1:8000
GUNICORN_WORKERS=3
GUNICORN_TIMEOUT=60
EOF
    chmod 600 "${CONF_DIR}/cloudpdf.env"
    chown root:${APP_USER} "${CONF_DIR}/cloudpdf.env"
fi

echo "==> [CloudPDF] Base provisioning completed."
echo "==> Next steps: Deploy code to ${APP_DIR}, run 'pip install -r requirements.txt', then start systemd and Nginx."
