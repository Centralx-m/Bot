#!/bin/bash

echo "🚀 Deploying XTAAGC Bot..."

# Install dependencies
pip install -r requirements.txt

# Test Bitget connection
python -c "
import asyncio
from backend import bitget_service
asyncio.run(bitget_service.connect())
print('✅ Bitget connection test passed')
"

# Test Firebase
python -c "
from backend import firebase_service
firebase_service.initialize()
print('✅ Firebase connection test passed')
"

# Start server
uvicorn backend:app --host 0.0.0.0 --port 8000 --reload