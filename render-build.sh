#!/usr/bin/env bash
set -o errexit

# --- Backend ---
pip install -r backend/requirements.txt

# --- Frontend ---
cd frontend
npm install
npm run build
cd ..

# --- Database migrations ---
cd backend
alembic upgrade head
