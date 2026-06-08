#!/bin/env bash
gunicorn \
  --workers 3 \
  --bind 127.0.0.1:8080 \
  --access-logfile - \
  --access-logformat '%(t)s [%(h)s] "%(r)s" %(s)s %(b)s "%(a)s"' \
  app:app
