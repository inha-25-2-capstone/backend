#!/usr/bin/env python3
"""
Run the FastAPI application.

Usage:
    python scripts/run_api.py
"""
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if __name__ == "__main__":
    import uvicorn
    
    # Run with hot reload in development
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
