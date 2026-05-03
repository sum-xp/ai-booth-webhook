import os

# Bind to the port that Render assigns
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# Worker timeout — Google GenAI calls typically take 20-40s
# 120s allows for retries (3 attempts with backoff)
timeout = 120

# 2 workers + preload to share memory (Standard plan = 2GB)
# preload loads styles once in master, shared across workers via fork
workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
preload_app = True

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
