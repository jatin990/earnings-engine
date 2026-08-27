"""Vercel serverless entry point for Earnings Engine FastAPI app."""

import os

# Ensure serverless environment flags are active before importing server
os.environ["VERCEL"] = "1"
os.environ["SERVERLESS"] = "1"

from earnings_engine.api.server import app
