import sys
import os

# Add the root directory to the path so that 'app' can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

# This is required for Vercel to find the FastAPI instance
handler = app
