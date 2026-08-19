import requests
import json

def test_streaming_chat():
    url = "http://localhost:5000/api/chat/1"
    payload = {
        "message": "Ciao, chi sei?",
        "admin_mode": True,
        "stream": True,
        "history": []
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"Inviando richiesta STREAM a {url}...")
    try:
        # Usiamo stream=True in requests per leggere chunk per chunk
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=300)
        response.raise_for_status()
        
        print("\n--- RICEZIONE STREAM ---")
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith("data: "):
                    content = line_str[6:].strip()
                    if content == "[DONE]":
                        print("\n--- STREAM COMPLETATO ---")
                        break
                    try:
                        data = json.loads(content)
                        if "content" in data:
                            print(data["content"], end="", flush=True)
                    except:
                        continue
        print("\n------------------------\n")
    except Exception as e:
        print(f"Errore durante il test: {e}")

if __name__ == "__main__":
    test_streaming_chat()
