#importing all the libraries installed and needed 
from dotenv import load_dotenv
import os
import requests

load_dotenv()   #loading the .env file so the API key and base URL can be accessed

# Getting the base URL from environment variables
BASE_URL = os.getenv(
"DIMENSION_DEPTHS_BASE_URL",
"https://dimension-depths-v2-production.up.railway.app"
).rstrip("/")

# Getting the API key from environment variables and ensuring it's not empty
API_KEY = os.getenv("DIMENSION_DEPTHS_API_KEY", "").strip()

if not API_KEY:
    raise RuntimeError("DIMENSION_DEPTHS_API_KEY is missing. Add it to your .env file.")

headers = {
"Authorization": f"Api-Key {API_KEY}"
}

# First test: dataset info
info_url = f"{BASE_URL}/api/soc/info/"
info_response = requests.get(info_url, headers=headers, timeout=30)
info_response.raise_for_status()

info_data = info_response.json()
print("INFO ENDPOINT WORKING")
print(info_data)

# Second test: pull a few assets
assets_url = f"{BASE_URL}/api/soc/assets/"
params = {
"limit": 5
}

assets_response = requests.get(assets_url, headers=headers, params=params, timeout=30)
assets_response.raise_for_status()

assets_data = assets_response.json()
print("\nASSETS ENDPOINT WORKING")
print(assets_data)
