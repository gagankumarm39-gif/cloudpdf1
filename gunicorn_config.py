"""
Gunicorn Production WSGI Server Configuration
Cloud-Based PDF Generation System - Milestone 7

Optimized for Amazon EC2 Linux instances (e.g., t3.micro, t3.small, t3.medium).
"""
import os
import multiprocessing

# Server Socket Binding
# On Render and cloud platforms, the PORT environment variable is automatically provided
port = os.getenv("PORT", "8000")
bind = os.getenv("GUNICORN_BIND", f"0.0.0.0:{port}")

# Worker Processes
# Render Free Web Services provide 0.1 CPU core and 512MB RAM.
# 2 to 3 workers are optimal to prevent exceeding the 512MB memory limit during PDF generation.
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
worker_class = "sync"
worker_connections = 1000

# Process Lifespan & Timeouts
# Set to 120 seconds to allow ReportLab compilation and cloud uploads on free-tier compute
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
keepalive = 5
graceful_timeout = 30

# Memory Management
# Automatically restart workers after serving requests to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Security & Permissions
umask = 0o007
proc_name = "cloudpdf-gunicorn"

# Logging Configuration
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (%(L)ss)'

# Preload Application
preload_app = False
