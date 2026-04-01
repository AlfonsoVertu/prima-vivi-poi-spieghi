import sqlite3, os, json, io, zipfile, logging, time
import requests
from functools import wraps

def with_retry(retries=3, delay=2):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            last_exc = None
            for i in range(retries):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    print(f"Tentativo {i+1} fallito: {e}. Riprovo tra {delay}s...")
                    time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator

@with_retry(retries=3, delay=5)
def call_openai(prompt=None, api_key=None, model="gpt-4o", max_tokens=4000, system=None, messages=None):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    if messages:
        final_messages = messages
    else:
        sys_msg = system if system else "Sei un premiato romanziere italiano specializzato in stili narrativi crudi e diretti in prima persona."
        final_messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt}
        ]
        
    payload = {
        "model": model,
        "messages": final_messages,
        "temperature": 0.7
    }
    if not model.startswith("o"): 
        payload["max_tokens"] = max_tokens
    
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    if response.status_code == 400:
        # Potenziale errore di context length - gestito dal caller o qui in futuro
        pass
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']

def call_anthropic(prompt=None, api_key=None, model="claude-3-7-sonnet-20250219", max_tokens=4000, system=None, messages=None):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    if messages:
        # Se abbiamo messaggi, il primo 'system' viene estratto se presente
        final_messages = []
        sys_msg = system or ""
        for m in messages:
            if m['role'] == 'system' and not sys_msg: sys_msg = m['content']
            elif m['role'] != 'system': final_messages.append(m)
        if not sys_msg: sys_msg = "Sei un poeta del realismo sporco."
    else:
        sys_msg = system if system else "Sei un premiato romanziere italiano specializzato in stili narrativi crudi e diretti in prima persona."
        final_messages = [{"role": "user", "content": prompt}]

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": sys_msg,
        "messages": final_messages
    }
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data['content'][0]['text']

def call_gemini(prompt=None, api_key=None, model="gemini-2.0-flash", max_tokens=4000, system=None, messages=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json",
    }
    
    if messages:
        final_contents = []
        sys_msg = system or ""
        for m in messages:
            if m['role'] == 'system' and not sys_msg: sys_msg = m['content']
            elif m['role'] != 'system':
                # Semplice mapping per Gemini: user/model -> user/model
                role = "user" if m['role'] == "user" else "model"
                final_contents.append({"role": role, "parts": [{"text": m['content']}]})
        if not sys_msg: sys_msg = "Sei un autore crudo."
    else:
        sys_msg = system if system else "Sei un premiato romanziere italiano specializzato in stili narrativi crudi e diretti in prima persona."
        final_contents = [{"role": "user", "parts": [{"text": prompt}]}]

    payload = {
        "system_instruction": {"parts": [{"text": sys_msg}]},
        "contents": final_contents,
        "generationConfig": {"maxOutputTokens": max_tokens}
    }
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    try:
        return data['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError):
        return str(data)

def extract_think_content(text):
    """
    Estrae il contenuto tra i tag <think> e </think> e il resto del testo.
    Ritorna (thinking, content).
    """
    import re
    # Rimuove il thinking se presente
    think_match = re.search(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
    thinking = think_match.group(1).strip() if think_match else ""
    content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
    return thinking, content

def extract_narrative(text):
    """
    Estrae ESCLUSIVAMENTE la parte narrativa dal testo prodotto dall'AI.
    Cerca tag <prose>, <narrative> o pulisce prefissi/suffissi chatter.
    """
    import re
    
    # 1. Rimuove il thinking (già fatto solitamente ma per sicurezza lo ripetiamo)
    _, text = extract_think_content(text)
    
    # 2. Cerca tag espliciti <prose> o <narrative>
    for tag in ['prose', 'narrative', 'testo']:
        pattern = f'<{tag}>(.*?)</{tag}>'
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
    # 3. Fallback: se non ci sono tag, proviamo a pulire il chatter comune
    # Rimuove "Ecco il testo:", "Sicuramente:", etc. all'inizio
    # Rimuove "Spero che ti piaccia", etc. alla fine
    lines = text.split('\n')
    if len(lines) > 2:
        # Se la prima riga è corta e finisce con : è probabile sia chatter
        if len(lines[0]) < 100 and lines[0].strip().endswith(':'):
            text = '\n'.join(lines[1:]).strip()
        # Se l'ultima riga è corta e sembra un saluto
        last_line = lines[-1].strip().lower()
        if len(last_line) < 100 and any(x in last_line for x in ["spero", "fammi sapere", "ecco", "revisione"]):
            text = '\n'.join(lines[:-1]).strip()

    # Rimuove eventuali residui di markdown code blocks se l'AI ha ignorato le istruzioni
    if "```" in text:
        text = re.sub(r'```[a-zA-Z]*\n?', '', text)
        text = text.replace('```', '')

    return text.strip()

def call_lmstudio(prompt, base_url, model, max_tokens=4000, system=None, api_key=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    else:
        messages.append({"role": "system", "content": "Sei un premiato romanziere italiano specializzato in stili narrativi crudi e diretti in prima persona."})
    
    messages.append({"role": "user", "content": prompt})
    return call_lmstudio_chat(messages, base_url, model, max_tokens, api_key)

@with_retry(retries=3, delay=5)
def call_lmstudio_chat(messages, base_url, model, max_tokens=4000, api_key=None):
    url = f"{base_url}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    print(f"DEBUG: Invio richiesta chat a {url} (Modello: {model}, Messaggi: {len(messages)})")
    response = requests.post(url, headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']



def call_openai_compatible_chat(messages, base_url, model, max_tokens=4000, api_key=None):
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=180)
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']


def call_ollama_chat(messages, base_url, model, max_tokens=4000):
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.7,
        },
    }
    response = requests.post(url, json=payload, timeout=300)
    response.raise_for_status()
    data = response.json()
    if 'message' in data and isinstance(data['message'], dict):
        return data['message'].get('content', '')
    return str(data)

def get_lmstudio_models(base_url, api_key=None):
    url = f"{base_url}/v1/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return [m['id'] for m in data['data']]
    except Exception as e:
        raise Exception(f"Errore discovery LM Studio: {str(e)}")

def generate_content(prompt, model_name, max_tokens=2000, system=None):
    """
    Funzione di supporto per la chat e utilizzi generici.
    Determina il provider in base al nome del modello o alle impostazioni ENV.
    """
    # Se il modello contiene l'IP di LM Studio o se è un modello custom
    if os.getenv("LLM_PROVIDER") == "lmstudio" or "192.168.1" in os.getenv("LMSTUDIO_URL", ""):
        provider = "lmstudio"
    elif "gpt" in model_name or "o1" in model_name or "o3" in model_name or "openai" in model_name:
        provider = "openai"
    elif "claude" in model_name:
        provider = "anthropic"
    elif "gemini" in model_name:
        provider = "google"
    elif "ollama" in model_name:
        provider = "ollama"
    elif "openai-compatible" in model_name or "openai_compatible" in model_name:
        provider = "openai_compatible"
    else:
        # Tenta di usare il provider di default
        provider = os.getenv("LLM_PROVIDER", "openai")

    api_key = ""
    if provider == "openai": api_key = os.getenv("OPENAI_API_KEY")
    elif provider == "anthropic": api_key = os.getenv("CLAUDE_API_KEY")
    elif provider == "google": api_key = os.getenv("GEMINI_API_KEY")
    elif provider == "lmstudio": api_key = os.getenv("LMSTUDIO_API_KEY", "")
    elif provider == "openai_compatible": api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
    elif provider == "ollama": api_key = ""
    
    return generate_chapter_text(prompt, provider, model_name, api_key, system=system, max_tokens=max_tokens)

def generate_chapter_text(prompt, provider, model, api_key, system=None, max_tokens=4000, messages=None):
    """
    Invia la chiamata API al modello selezionato.
    Supporta flussi multi-messaggio per tutti i provider.
    """
    try:
        if provider == "openai":
            if not api_key: raise ValueError("API Key OpenAI mancante.")
            try:
                return call_openai(prompt, api_key, model, system=system, max_tokens=max_tokens, messages=messages)
            except Exception as e:
                if "context_length_exceeded" in str(e).lower() and messages:
                    # Fallback Incrementale: Riduciamo il contesto dei riassunti (Step 2)
                    print("ATTENZIONE: Context Window superata. Applico potatura incrementale...")
                    slim_messages = [m for m in messages if "Step 2" not in str(m.get('content', ''))]
                    return call_openai(prompt, api_key, model, system=system, max_tokens=max_tokens, messages=slim_messages)
                raise e
        elif provider == "anthropic":
            if not api_key: raise ValueError("API Key Anthropic mancante.")
            return call_anthropic(prompt, api_key, model, system=system, max_tokens=max_tokens, messages=messages)
        elif provider == "google":
            if not api_key: raise ValueError("API Key Google mancante.")
            return call_gemini(prompt, api_key, model, system=system, max_tokens=max_tokens, messages=messages)
        elif provider == "lmstudio":
            base_url = os.getenv("LMSTUDIO_URL", "http://192.168.1.62:1234")
            if messages:
                return call_lmstudio_chat(messages, base_url, model, max_tokens=max_tokens, api_key=api_key)
            else:
                return call_lmstudio(prompt, base_url, model, system=system, max_tokens=max_tokens, api_key=api_key)
        elif provider == "openai_compatible":
            base_url = os.getenv("OPENAI_COMPATIBLE_URL", "").strip()
            if not base_url:
                raise ValueError("OPENAI_COMPATIBLE_URL non impostato.")
            final_messages = messages if messages else [
                {"role": "system", "content": system or "Sei un assistente narrativo."},
                {"role": "user", "content": prompt},
            ]
            return call_openai_compatible_chat(final_messages, base_url, model, max_tokens=max_tokens, api_key=api_key)
        elif provider == "ollama":
            base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
            final_messages = messages if messages else [
                {"role": "system", "content": system or "Sei un assistente narrativo."},
                {"role": "user", "content": prompt},
            ]
            return call_ollama_chat(final_messages, base_url, model, max_tokens=max_tokens)
        else:
            raise ValueError(f"Provider {provider} non supportato.")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        err_text = e.response.text
        raise Exception(f"Errore HTTP API {status}: {err_text}")
    except Exception as e:
        raise Exception(f"Errore generazione LLM: {str(e)}")


def generate_with_agent(
    agent_cfg: dict,
    *,
    prompt: str | None = None,
    system: str | None = None,
    messages: list[dict] | None = None
) -> str:
    cfg = agent_cfg or {}
    provider = cfg.get("provider", "openai")
    model = cfg.get("model", "gpt-4o")
    max_tokens = int(cfg.get("max_tokens", 1200) or 1200)
    sys_prompt = system if system is not None else cfg.get("system_prompt")

    api_key = ""
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
    elif provider == "anthropic":
        api_key = os.getenv("CLAUDE_API_KEY", "")
    elif provider == "google":
        api_key = os.getenv("GEMINI_API_KEY", "")
    elif provider == "lmstudio":
        api_key = os.getenv("LMSTUDIO_API_KEY", "")
    elif provider == "openai_compatible":
        api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
    elif provider == "ollama":
        api_key = ""

    if messages is None:
        messages = [
            {"role": "system", "content": sys_prompt or "Sei un assistente."},
            {"role": "user", "content": prompt or ""},
        ]

    return generate_chapter_text(
        prompt or "",
        provider,
        model,
        api_key,
        system=sys_prompt,
        max_tokens=max_tokens,
        messages=messages,
    )
