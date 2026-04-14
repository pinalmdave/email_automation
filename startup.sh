#!/bin/bash
gunicorn --bind=0.0.0.0:8000 --workers=1 --timeout=120 -k uvicorn.workers.UvicornWorker api.server:app
