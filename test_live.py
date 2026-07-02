import httpx
import json

URL = "https://conversational-shl-assessment-recommender-qffs.onrender.com/chat"

payload = {
    "messages": [
        {"role": "user", "content": "Hi, I'm hiring a bilingual healthcare admin assistant in Spanish."}
    ]
}

print("Sending request to your live Render API...")
try:
    response = httpx.post(URL, json=payload, timeout=30.0)
    print(f"\nStatus Code: {response.status_code}")
    print("\n--- Live Reply ---")
    print(response.json()["reply"])
    print("\n--- Recommendations JSON ---")
    print(json.dumps(response.json()["recommendations"], indent=2))
    print(f"\nEnd of Conversation: {response.json()['end_of_conversation']}")
except Exception as e:
    print(f"Error calling live server: {e}")
