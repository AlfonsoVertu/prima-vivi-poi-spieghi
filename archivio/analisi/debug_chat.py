import os
from dotenv import load_dotenv
load_dotenv()

import app
import llm_client

def debug_chat():
    cap_id = 1
    provider = os.getenv("LLM_PROVIDER", "lmstudio")
    model_name = os.getenv("ADMIN_CHAT_MODEL", "zai-org/glm-4.6v-flash")
    api_key = os.getenv("LMSTUDIO_API_KEY", "")
    user_msg = "Chi è Lin?"
    
    print(f"DEBUG: Provider={provider}, Model={model_name}, URL={os.getenv('LMSTUDIO_URL')}")
    
    try:
        print("DEBUG: Avvio run_deep_context_pipeline...")
        history = app.run_deep_context_pipeline(cap_id, provider, model_name, api_key, user_msg=user_msg, admin_mode=False)
        print(f"DEBUG: Pipeline completata, messaggi: {len(history)}")
        
        print("DEBUG: Avvio generazione risposta...")
        # Simulazione dello step finale
        reply = llm_client.generate_chapter_text("", provider, model_name, api_key, max_tokens=1000, messages=history)
        print("\n--- RISPOSTA ---")
        print(reply)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_chat()
