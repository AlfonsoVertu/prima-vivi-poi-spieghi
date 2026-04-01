import os
from dotenv import load_dotenv

def check():
    load_dotenv()
    print(f"DEBUG: LMSTUDIO_URL='{os.getenv('LMSTUDIO_URL')}'")
    print(f"DEBUG: ADMIN_CHAT_MODEL='{os.getenv('ADMIN_CHAT_MODEL')}'")
    print(f"DEBUG: LLM_PROVIDER='{os.getenv('LLM_PROVIDER')}'")

if __name__ == "__main__":
    check()
