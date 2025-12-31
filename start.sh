#!/bin/bash
export PYTHONPATH=/opt/render/project/src/backend:$PYTHONPATH
cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}

