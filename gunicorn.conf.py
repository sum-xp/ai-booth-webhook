import os

# Bind to the port that Render assigns
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# Worker timeout — must be longer than the in-app retry budget so gunicorn
# doesn't kill workers mid-retry. Current budget:
#   2 NB Pro attempts × 50s + 1s delay = 101s
#   + optional fallback × 50s + 2s delay = 153s
# 180s gives a comfortable margin.
timeout = 180

# 2 workers + preload to share memory (Standard plan = 2GB)
# preload loads styles once in master, shared across workers via fork
workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
preload_app = True

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
