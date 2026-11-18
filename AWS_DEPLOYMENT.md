# AWS EC2 Production Deployment Guide

## Cloud-Based PDF Generation System — Milestone 7

This deployment runbook guides you through deploying the **Cloud-Based PDF Generation System** on an Amazon Web Services (AWS) EC2 Linux instance using **Gunicorn**, **systemd**, **Nginx**, and **IAM Instance Profiles**.

---

## 1. Architecture Overview

```
                      +---------------------------------------+
                      |               INTERNET                |
                      +---------------------------------------+
                                          |
                                   HTTP / HTTPS
                               (Ports 80 / 443)
                                          v
                      +---------------------------------------+
                      |       EC2 SECURITY GROUP              |
                      |  - Port 22 (SSH): <ADMIN_IP>/32       |
                      |  - Port 80 (HTTP): 0.0.0.0/0          |
                      |  - Port 443 (HTTPS): 0.0.0.0/0        |
                      +---------------------------------------+
                                          |
                                          v
+---------------------------------------------------------------------------------+
| AMAZON EC2 LINUX INSTANCE (Amazon Linux 2023 / Ubuntu 22.04 LTS)                |
|                                                                                 |
|  +--------------------+   reverse proxy    +---------------------------------+  |
|  | Nginx Web Server   | -----------------> | Gunicorn WSGI Application       |  |
|  | - Port 80 / 443    |   (127.0.0.1:8000) | - Flask app:app (3 workers)     |  |
|  | - Serves /static/  |                    | - ReportLab PDF Engine          |  |
|  | - Security Headers |                    | - systemd daemon (cloudpdf.srv) |  |
|  +--------------------+                    +---------------------------------+  |
|                                                               |                 |
|                                      Boto3 (IAM Instance Role)|                 |
+---------------------------------------------------------------|-----------------+
                                                                |
                               +--------------------------------+--------------------------------+
                               |                                                                 |
                               v                                                                 v
                +------------------------------+                                  +------------------------------+
                |        AMAZON S3             |                                  |       AMAZON DYNAMODB        |
                |  - Private PDF Storage Bucket|                                  |  - Table: CloudPDFDocuments  |
                |  - Block Public Access: ON   |                                  |    (PK: doc_id, GSI: UserDoc)|
                |  - Presigned URL Generation  |                                  |  - Table: CloudPDFUsers      |
                |                              |                                  |    (PK: user_id, GSI: Email) |
                +------------------------------+                                  +------------------------------+
```

---

## 2. Prerequisites & AWS Requirements

Before beginning deployment, ensure you have:
1. An active AWS Account.
2. AWS CLI installed and configured locally (`aws configure`).
3. An SSH Key Pair (`.pem`) generated in your target AWS region (e.g., `us-east-1`).

---

## 3. Step 1: Create the AWS IAM Instance Role

Never store AWS access keys on the EC2 server. Attach an IAM Role with least-privilege permissions.

### 3.1 Create the Trust Policy File (`ec2_trust_policy.json`)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ec2.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### 3.2 Create the IAM Role
```bash
aws iam create-role \
    --role-name CloudPDF-EC2-Role \
    --assume-role-policy-document file://ec2_trust_policy.json
```

### 3.3 Attach the Least-Privilege Policy
Edit [`deploy/iam_policy.json`](file:///c:/Users/Kavya%20M/OneDrive/Desktop/cloudpdfgenerator/deploy/iam_policy.json) to substitute `${S3_BUCKET_NAME}`, `${AWS_REGION}`, and `${AWS_ACCOUNT_ID}` with your specific AWS account values:

```bash
aws iam put-role-policy \
    --role-name CloudPDF-EC2-Role \
    --policy-name CloudPDF-LeastPrivilege-Policy \
    --policy-document file://deploy/iam_policy.json
```

### 3.4 Create the IAM Instance Profile
```bash
aws iam create-instance-profile --instance-profile-name CloudPDF-EC2-Profile
aws iam add-role-to-instance-profile \
    --instance-profile-name CloudPDF-EC2-Profile \
    --role-name CloudPDF-EC2-Role
```

---

## 4. Step 2: Configure EC2 Security Group

Create an EC2 Security Group with restricted SSH access:

```bash
# Create Security Group
SG_ID=$(aws ec2 create-security-group \
    --group-name "cloudpdf-sg" \
    --description "Security group for CloudPDF production server" \
    --query "GroupId" --output text)

# Allow SSH only from your specific IP (Replace 203.0.113.25 with your IP)
aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp --port 22 --cidr "<YOUR_PUBLIC_IP>/32"

# Allow HTTP and HTTPS for web traffic
aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp --port 80 --cidr "0.0.0.0/0"
aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp --port 443 --cidr "0.0.0.0/0"
```

---

## 5. Step 3: Launch the EC2 Instance

Launch an Amazon Linux 2023 instance (Free Tier eligible `t3.micro` or `t3.small`):

```bash
# Find latest Amazon Linux 2023 AMI
AMI_ID=$(aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query "Parameters[0].Value" --output text)

# Launch Instance with attached IAM Profile
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --instance-type t3.micro \
    --key-name "your-ssh-key" \
    --security-group-ids $SG_ID \
    --iam-instance-profile Name="CloudPDF-EC2-Profile" \
    --user-data file://deploy/ec2_userdata.sh \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=CloudPDF-Server}]" \
    --query "Instances[0].InstanceId" --output text)

echo "Launched Instance: $INSTANCE_ID"
```

Wait for the instance to transition to `running` and note its public IP:
```bash
PUBLIC_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
    --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
echo "Instance Public IP: $PUBLIC_IP"
```

---

## 6. Step 4: Deploy Application Code to EC2

### 6.1 SSH into Instance
```bash
ssh -i "your-ssh-key.pem" ec2-user@$PUBLIC_IP
```

### 6.2 Clone the Repository or Upload Code
```bash
sudo chown -R ec2-user:ec2-user /opt/cloudpdfgenerator
cd /opt/cloudpdfgenerator

# Clone repository:
git clone <YOUR_GIT_REPOSITORY_URL> .

# Or upload files via SCP from your local machine:
# scp -i your-ssh-key.pem -r * ec2-user@$PUBLIC_IP:/opt/cloudpdfgenerator/
```

### 6.3 Install Python Dependencies
```bash
/opt/cloudpdfgenerator/venv/bin/pip install --upgrade pip
/opt/cloudpdfgenerator/venv/bin/pip install -r requirements.txt
```

---

## 7. Step 5: Configure Environment & AWS Resources

### 7.1 Set Up `/etc/cloudpdf/cloudpdf.env`
```bash
sudo mkdir -p /etc/cloudpdf
sudo nano /etc/cloudpdf/cloudpdf.env
```

Paste your production settings:
```ini
FLASK_ENV=production
FLASK_DEBUG=false
SECRET_KEY=generate-a-strong-random-key-here
SESSION_COOKIE_SECURE_ENABLED=false

AWS_REGION=us-east-1
S3_BUCKET_NAME=my-cloudpdf-storage-vault
DYNAMODB_TABLE_NAME=CloudPDFDocuments
DYNAMODB_USERS_TABLE=CloudPDFUsers

GUNICORN_BIND=127.0.0.1:8000
GUNICORN_WORKERS=3
GUNICORN_TIMEOUT=60
```
Secure the file permissions:
```bash
sudo chmod 600 /etc/cloudpdf/cloudpdf.env
sudo chown root:ec2-user /etc/cloudpdf/cloudpdf.env
```

### 7.2 Run AWS Infrastructure Verification Script
The provided verification script creates/checks the S3 bucket with Block Public Access and provisions the DynamoDB tables with required Global Secondary Indexes:
```bash
/opt/cloudpdfgenerator/venv/bin/python deploy/setup_aws_resources.py
```
Expected output:
```
[1/3] Checking Amazon S3 Bucket: 'my-cloudpdf-storage-vault'...
  [✓] Bucket exists and is accessible.
[2/3] Checking DynamoDB Documents Table: 'CloudPDFDocuments'...
  [✓] Table exists and UserDocIndex GSI is present.
[3/3] Checking DynamoDB Users Table: 'CloudPDFUsers'...
  [✓] Table exists and EmailIndex GSI is present.
[SUCCESS] All AWS Cloud resources are ready for production!
```

---

## 8. Step 6: Configure systemd Service & Nginx

### 8.1 Install and Enable systemd Service
```bash
sudo cp deploy/cloudpdf.service /etc/systemd/system/cloudpdf.service
sudo systemctl daemon-reload
sudo systemctl enable cloudpdf
sudo systemctl start cloudpdf
```

Check status:
```bash
sudo systemctl status cloudpdf
```

### 8.2 Configure Nginx Reverse Proxy
```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/cloudpdf.conf
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
```

---

## 9. Step 7: Verify Production Deployment

### 9.1 Health Check Probe
In your terminal or browser, query the health endpoint:
```bash
curl -i http://$PUBLIC_IP/api/health
```

Expected Response:
```json
{
  "status": "healthy",
  "service": "Cloud-Based PDF Generation System",
  "version": "7.0.0",
  "environment": "production",
  "cloud_services": {
    "s3": {
      "accessible": true,
      "configured": true,
      "status": "connected",
      "bucket": "my-cloudpdf-storage-vault"
    },
    "dynamodb_documents": {
      "accessible": true,
      "configured": true,
      "status": "connected",
      "table": "CloudPDFDocuments"
    },
    "dynamodb_users": {
      "accessible": true,
      "configured": true,
      "status": "connected",
      "table": "CloudPDFUsers"
    }
  }
}
```

### 9.2 Functional Verification
1. Open `http://<PUBLIC_IP>` in your browser.
2. Sign in with the pre-seeded demo user (`kavya@cloudpdf.edu` / `Password123`) or register a new user.
3. Fill in the PDF form and click **Generate PDF**.
4. Verify that:
   - The PDF downloads automatically to your browser.
   - The document appears in **Document History**.
   - Clicking **Preview** opens the inline modal.
   - S3 and DynamoDB metrics update on the dashboard.

---

## 10. Operational Runbook: Start, Stop, and Monitoring

| Action | Command |
|---|---|
| **Start Service** | `sudo systemctl start cloudpdf` |
| **Stop Service** | `sudo systemctl stop cloudpdf` |
| **Restart Service** | `sudo systemctl restart cloudpdf` |
| **Reload Code (Zero-Downtime)** | `sudo systemctl reload cloudpdf` |
| **View Live Application Logs** | `sudo journalctl -u cloudpdf -f` |
| **View Nginx Access Logs** | `sudo tail -f /var/log/nginx/cloudpdf_access.log` |
| **View Nginx Error Logs** | `sudo tail -f /var/log/nginx/cloudpdf_error.log` |

---

## 11. HTTPS / SSL Termination (Optional Domain Setup)

When pointing a custom domain (e.g. `pdf.yourdomain.com`) to the EC2 Public IP:

1. Install Certbot:
   ```bash
   sudo dnf install -y certbot python3-certbot-nginx
   # Or on Ubuntu: sudo apt install -y certbot python3-certbot-nginx
   ```
2. Request and bind free Let's Encrypt certificate:
   ```bash
   sudo certbot --nginx -d pdf.yourdomain.com
   ```
3. Enable HTTPS secure cookies in `/etc/cloudpdf/cloudpdf.env`:
   ```ini
   SESSION_COOKIE_SECURE_ENABLED=true
   ```
4. Restart application:
   ```bash
   sudo systemctl restart cloudpdf
   ```

---

## 12. Troubleshooting Guide

| Issue | Likely Cause | Resolution |
|---|---|---|
| **502 Bad Gateway** | Gunicorn process is not running or socket/port blocked | Run `sudo systemctl status cloudpdf` and check `journalctl -u cloudpdf -e`. |
| **403 Access Denied on S3/DynamoDB** | IAM role missing or not attached to EC2 instance | Verify IAM role attachment: `aws ec2 describe-iam-instance-profile-associations`. Ensure policy matches your bucket and table names. |
| **Session drops after sign-in** | `SESSION_COOKIE_SECURE_ENABLED=true` used over plain HTTP | Set `SESSION_COOKIE_SECURE_ENABLED=false` until an SSL certificate is configured. |
| **PDF compilation timeout** | ReportLab parsing large file exceeding Gunicorn timeout | Increase `GUNICORN_TIMEOUT=120` in `/etc/cloudpdf/cloudpdf.env` and reload systemd. |
| **Static files 404** | Nginx `location /static/` pointing to incorrect path | Verify `/opt/cloudpdfgenerator/static/` exists and has read permissions for the `nginx` user (`chmod -R 755 /opt/cloudpdfgenerator/static`). |
