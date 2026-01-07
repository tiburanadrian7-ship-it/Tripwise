import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GOOGLE_API_KEY")

if key:
    print(f"DEBUG: Key found! It starts with: {key[:5]}...")
    print(f"DEBUG: Length of key: {len(key)}")
else:
    print("DEBUG: No key found in environment variables.")