import os
from typing import Dict, List

import requests


def _clean_base_url(base_url: str, fallback: str = "") -> str:
    base = (base_url or fallback or "").strip()
    if not base:
        return ""
    return base.rstrip("/")


def _auth_headers(api_key: str = "") -> Dict[str, str]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def discover_lmstudio(base_url: str, api_key: str = "") -> List[str]:
    url = f"{_clean_base_url(base_url, os.getenv('LMSTUDIO_URL', 'http://127.0.0.1:1234'))}/v1/models"
    response = requests.get(url, headers=_auth_headers(api_key), timeout=10)
    response.raise_for_status()
    data = response.json()
    return sorted([m["id"] for m in data.get("data", [])])


def test_lmstudio(base_url: str, api_key: str = "") -> Dict[str, str]:
    discover_lmstudio(base_url, api_key)
    return {"status": "success", "message": "Connessione LM Studio riuscita"}


def discover_ollama(base_url: str) -> List[str]:
    url = f"{_clean_base_url(base_url, os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434'))}/api/tags"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    return sorted([m.get("name", "") for m in data.get("models", []) if m.get("name")])


def test_ollama(base_url: str) -> Dict[str, str]:
    discover_ollama(base_url)
    return {"status": "success", "message": "Connessione Ollama riuscita"}


def discover_openai_compatible(base_url: str, api_key: str = "") -> List[str]:
    cleaned = _clean_base_url(base_url, os.getenv('OPENAI_COMPATIBLE_URL', ''))
    if not cleaned:
        raise ValueError("Base URL OpenAI-compatible mancante")
    url = f"{cleaned}/v1/models"
    response = requests.get(url, headers=_auth_headers(api_key), timeout=10)
    response.raise_for_status()
    data = response.json()
    return sorted([m["id"] for m in data.get("data", []) if m.get("id")])


def test_openai_compatible(base_url: str, api_key: str = "") -> Dict[str, str]:
    discover_openai_compatible(base_url, api_key)
    return {"status": "success", "message": "Connessione OpenAI-compatible riuscita"}


def discover_models(provider_type: str, base_url: str = "", api_key: str = "") -> List[str]:
    provider = (provider_type or "").strip().lower()
    if provider == "lmstudio":
        return discover_lmstudio(base_url, api_key)
    if provider == "ollama":
        return discover_ollama(base_url)
    if provider in {"openai_compatible", "openai-compatible"}:
        return discover_openai_compatible(base_url, api_key)
    raise ValueError(f"Provider discovery non supportato: {provider_type}")


def test_provider(provider_type: str, base_url: str = "", api_key: str = "") -> Dict[str, str]:
    provider = (provider_type or "").strip().lower()
    if provider == "lmstudio":
        return test_lmstudio(base_url, api_key)
    if provider == "ollama":
        return test_ollama(base_url)
    if provider in {"openai_compatible", "openai-compatible"}:
        return test_openai_compatible(base_url, api_key)
    raise ValueError(f"Provider test non supportato: {provider_type}")
