"""
Production Gunicorn Configuration for Kepler Tech Sales AI.
Optimized for 1 worker process with 4 threads for high concurrency without process lock contention.
"""

import os
import multiprocessing

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:5000")
workers = int(os.environ.get("GUNICORN_WORKERS", 1))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# Security and logging
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (%(D)s µs)'

# Preload app to share read-only catalogue memory across threads
preload_app = True
