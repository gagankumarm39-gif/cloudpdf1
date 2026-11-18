# Complete Cloud Deployment Runbook: Render + Supabase

## Cloud-Based PDF Generation System — Milestone 10

This runbook guides you through deploying the complete **Cloud-Based PDF Generation System** using **Render Free Web Service**, **Supabase PostgreSQL**, and **Supabase Storage**.

---

## 1. System Architecture

```
                                  [ Browser / Client ]
                                           |
                                      (HTTPS / TLS)
                                           v
                             +---------------------------+
                             |   Render Web Service      |
                             |   - Gunicorn WSGI Server  |
                             |   - Python 3.12 Runtime   |
                             |   - Flask Application     |
                             |   - ReportLab PDF Engine  |
                             +---------------------------+
                                    |             |
                   +----------------+             +----------------+
                   | (SQLAlchemy / Pooler)                         | (Signed URLs / API)
                   v                                               v
+------------------------------------+          +------------------------------------+
|        SUPABASE POSTGRESQL         |          |          SUPABASE STORAGE          |
| - Host: pooler.supabase.com        |          | - Bucket: pdf-documents (Private)  |
| - Tables: users, documents         |          | - User folders: {user_id}/{doc_id} |
| - Connection: SSL / Pooler (5432)  |          | - Ephemeral presigned view/dl URLs |
+------------------------------------+          +------------------------------------+
```

---

## 2. Render Free Web Service Specifications

- **Plan**: Free ($0/month, student project friendly).
- **Compute**: 0.1 CPU core, 512 MB RAM.
- **Sleep Policy**: Free web services spin down (sleep) after **15 minutes of inactivity**. The first incoming request will take ~30–50 seconds to wake up the server (cold start).
- **Outbound Bandwidth**: 100 GB / month free.
- **TLS / SSL**: Free managed automatic SSL certificate (`https://<service-name>.onrender.com`).

---

## 3. Deployment Configuration Files

The project includes all required production descriptors:

1. **`Procfile`**:
   ```text
   web: gunicorn --config gunicorn_config.py app:app
   ```
2. **`runtime.txt`**:
   ```text
   python-3.12.7
   ```
3. **`gunicorn_config.py`**:
   - Dynamic port binding: `0.0.0.0:$PORT`
   - Worker count: `2` (conservative setting tailored to 512MB RAM on free tier)
   - Timeout: `120s` (sufficient time for ReportLab compilation and cloud uploads)
4. **`render.yaml`**: Infrastructure-as-code Blueprint definition.

---

## 4. Step-by-Step Render Deployment Guide

### Step 4.1: Push Project to GitHub
Ensure all code and configuration files are committed to your GitHub repository:
- Repository: `https://github.com/gagankumarm39-gif/cloudpdf1`
- Confirm `.env` is **NOT** committed (ignored via `.gitignore`).

### Step 4.2: Create a Web Service on Render
1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** $\rightarrow$ **Web Service**.
3. Under **Connect a repository**, select your GitHub account and choose `cloudpdf1`.
   *(If not visible, click "Configure GitHub App" to grant repository access).*
4. Fill in the following service details:
   - **Name**: `cloudpdf-studio` (or any custom name)
   - **Region**: `Singapore` (or choose the region closest to your Supabase Tokyo database: `ap-northeast-1`)
   - **Branch**: `main` (or your active branch)
   - **Root Directory**: Leave blank (uses project root)
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     gunicorn --config gunicorn_config.py app:app
     ```
   - **Instance Type**: Select **Free** ($0/mo).

### Step 4.3: Configure Environment Variables in Render
Scroll down to the **Environment Variables** section and add the following keys:

| Environment Variable | Recommended Value | Notes |
|---|---|---|
| `FLASK_ENV` | `production` | Enables production security & optimizations |
| `FLASK_DEBUG` | `false` | Disables Flask debug mode |
| `SECRET_KEY` | *(64-hex string)* | Generate via `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | `postgresql://postgres.tcqexhpsjaaiikmukzpb:[PASSWORD]@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres` | Replace `[PASSWORD]` with your actual Supabase DB password |
| `SUPABASE_URL` | `https://tcqexhpsjaaiikmukzpb.supabase.co` | Supabase Project URL |
| `SUPABASE_KEY` | *(Your Supabase Key)* | Use Service Role Key for backend storage access |
| `SUPABASE_BUCKET`| `pdf-documents` | Private storage bucket |
| `SESSION_COOKIE_SECURE_ENABLED` | `true` | Enforces HTTPS-only cookies on Render |
| `GUNICORN_WORKERS` | `2` | Keeps memory usage under 512MB |
| `GUNICORN_TIMEOUT` | `120` | Generous timeout for PDF rendering |

> [!IMPORTANT]
> **Supabase Secret API Key vs Publishable Key**:
> For server-side storage operations with private buckets (creating signed URLs, deleting user files), the backend uses the **Service Role Secret Key** from:
> **Supabase Dashboard $\rightarrow$ Project Settings $\rightarrow$ API $\rightarrow$ Project API keys $\rightarrow$ `service_role`**.
> Never expose this key in client-side code or GitHub.

### Step 4.4: Configure Health Check Endpoint
1. In the **Advanced** settings on Render, locate **Health Check Path**.
2. Enter:
   ```text
   /api/health
   ```
3. Render will monitor this path during deployments to ensure the application starts successfully before routing traffic.

### Step 4.5: Deploy and Access
1. Click **Create Web Service**.
2. Render will clone the repository, run `pip install -r requirements.txt`, and launch Gunicorn.
3. Once the build finishes, you will see a green checkmark and your live URL:
   `https://<your-service-name>.onrender.com`

---

## 5. Verification & Testing on Live Deployment

Once deployed, verify each component:

1. **Health Check**:
   Visit `https://<your-service-name>.onrender.com/api/health`.
   Verify `status` is `healthy` and `supabase_postgres` / `supabase_storage` report `configured: true`.
2. **Account Registration**:
   Navigate to `/register` and create an account. Verify credentials persist in Supabase PostgreSQL (`users` table).
3. **Login & Session**:
   Log in with the new account; verify cookies have `Secure` and `HttpOnly` flags.
4. **PDF Generation**:
   Use the Document Studio to generate a PDF with title, author, and description.
5. **PDF Preview**:
   Click the eye icon to view the PDF directly in the browser modal via a signed URL.
6. **PDF Download**:
   Click download to verify the attachment streams properly.
7. **Document Deletion**:
   Delete a document; verify removal from Supabase Storage and PostgreSQL.
