#!/bin/bash

# DigitalOcean deployment startup script for FastAPI backend
# This script sets up and runs the FastAPI application

# Set environment variables
export PYTHONPATH=/app/src
export PORT=${PORT:-8000}

# Navigate to the application directory
cd /app

# Install dependencies
pip install -r requirements.txt

# Run database migrations if needed
python update_dealer_credit_limit.py

# Start the FastAPI application
python -m uvicorn src.main:app --host 0.0.0.0 --port $PORT
