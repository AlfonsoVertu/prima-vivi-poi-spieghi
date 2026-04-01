import requests
import json

def test_chat():
    url = "http://localhost:5000/api/chat/1"
    payload = {
        "message": "Chi è Lin e cosa gli succede nel primo capitolo?",
        "admin_mode": False,
        "history": []
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"Inviando richiesta a {url}...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        print("\n--- RISPOSTA AI ---")
        print(data.get("reply"))
        print("-------------------\n")
    except Exception as e:
        print(f"Errore durante il test: {e}")

if __name__ == "__main__":
    test_chat()
