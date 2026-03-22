# Prima Vivi Poi Spieghi

Applicazione web Flask per la scrittura, revisione e gestione del romanzo corale *Prima Vivi Poi Spieghi*.

## Struttura del Progetto

```
prima-vivi-poi-spieghi/
├── app.py                  # Server Flask principale
├── llm_client.py           # Client AI multi-provider (OpenAI, Anthropic, Gemini)
├── ai_queue.py             # Coda per le generazioni AI
├── compila_iterativo.py    # Builder dei prompt per l'AI
├── roman.db                # Database SQLite (capitoli, personaggi, timeline)
├── prompts.json            # Prompt di sistema per l'AI
├── ui_settings.json        # Impostazioni UI
├── CANONE_DEFINITIVO.md    # Canon del romanzo (usato come contesto AI)
├── CANONE_AGGIORNATO.md    # Canon aggiornato
├── capitoli/               # Testi dei 66 capitoli (cap01.txt - cap66.txt)
└── docs/                   # Documentazione del progetto
```

## Avvio

```bash
# 1. Crea il file .env con le chiavi API
cp .env.example .env  # oppure crealo manualmente

# 2. Installa le dipendenze
pip install flask python-dotenv requests

# 3. Avvia il server
python app.py
```

L'applicazione sarà disponibile su `http://localhost:5000`.

## Funzionalità

- **Dashboard Admin**: gestione capitoli, metadati, timeline e personaggi
- **Editor Testo**: scrittura e revisione con analisi AI on-save
- **Generazione AI**: generazione automatica di metadati (titolo, POV, riassunti)
- **Chat AI**: assistente contestuale per l'autore e per il lettore
- **Timeline**: gestione degli archi temporali del romanzo
- **Personaggi**: schede complete con tracking presenza per capitolo

## Variabili d'Ambiente (.env)

```
ADMIN_USER=<utente>
ADMIN_PASS=<password>
OPENAI_API_KEY=<chiave>
ANTHROPIC_API_KEY=<chiave>
GOOGLE_API_KEY=<chiave>
```

## Licenza

Progetto privato — tutti i diritti riservati.
