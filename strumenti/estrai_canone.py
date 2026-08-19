# -*- coding: utf-8 -*-
"""Estrae il canone dai capitoli, leggendoli davvero con il modello locale.

PERCHE' SERVE. I metadati nel database e i testi sui file si sono scollati:
per una fascia di capitoli il file porta il titolo che il database assegna al
capitolo successivo, e alcuni titoli presenti nei file il database non li ha
proprio. Finche' non si sa cosa c'e' DENTRO ogni file, non si puo' dire quale
dei due abbia ragione - e i metadati sono esattamente cio' che verrebbe dato
in pasto al modello per rigenerare un capitolo. Sbagliati quelli, si
rigenererebbe il capitolo giusto con il punto di vista e la data di un altro.

COSA FA. Per ogni capitolo chiede al modello locale di estrarre solo fatti
verificabili nel testo: chi parla, dove, quando, chi compare, cosa succede.
Niente interpretazioni: quelle vengono dopo, e le fa una persona.

DOVE SCRIVE. In una tabella nuova, `canone_estratto`. Non tocca `capitoli`:
finche' non si e' certi di quale versione sia quella buona, sovrascrivere i
metadati esistenti vorrebbe dire perdere l'unica copia di confronto.
"""
import json
import os
import re
import sqlite3
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from llm_client import call_lmstudio_chat  # noqa: E402

DB = os.path.join(BASE, 'roman.db')
CAPITOLI = os.path.join(BASE, 'capitoli')
BASE_URL = os.environ.get('CANONE_BASE_URL', 'http://192.168.1.51:8088')
MODELLO = os.environ.get('CANONE_MODEL', 'gemma')

SCHEMA = """
CREATE TABLE IF NOT EXISTS canone_estratto (
    capitolo INTEGER PRIMARY KEY,
    titolo TEXT,
    pov TEXT,
    luogo TEXT,
    data_narrativa TEXT,
    personaggi TEXT,          -- separati da virgola, come nominati nel testo
    riassunto TEXT,           -- cosa succede, in tre o quattro frasi
    eventi_chiave TEXT,       -- JSON: elenco di fatti che altri capitoli devono rispettare
    oggetti_simboli TEXT,     -- JSON: cose che tornano altrove
    incongruenze TEXT,        -- JSON: cio' che il capitolo stesso non torna
    caratteri INTEGER,
    estratto_il TEXT
);
"""

ISTRUZIONI = """Sei un archivista, non un critico. Leggi il capitolo e riporti
SOLO cio' che il testo dice davvero.

Regole non negoziabili:
- Se un dato non c'e' nel testo, scrivi null. Non dedurlo, non inventarlo.
- Le date: riporta quelle scritte nel testo, non quelle che ti aspetteresti.
- I nomi: esattamente come compaiono, senza correggerli.
- "titolo": il titolo vero del capitolo. "Capitolo 12" NON e un titolo:
  se il testo non ne dichiara uno, scrivi null.
- "eventi_chiave": i fatti che gli altri capitoli devono rispettare per non
  contraddirsi (morti, ferite permanenti, promesse, spostamenti, decisioni).
- "incongruenze": SOLO contraddizioni interne a questo capitolo, per esempio
  una data che non torna con l'eta' dichiarata. Non confrontare con altri
  capitoli: non li hai letti.

Rispondi con un solo oggetto JSON, senza testo attorno e senza blocchi di
codice, con queste chiavi:
titolo, pov, luogo, data_narrativa, personaggi (lista), riassunto,
eventi_chiave (lista di stringhe), oggetti_simboli (lista di stringhe),
incongruenze (lista di stringhe)."""


def solo_json(testo):
    """Il primo oggetto JSON dentro la risposta.

    I modelli piccoli mettono volentieri il JSON dentro un blocco di codice o
    lo fanno precedere da una frase: si prende quello che serve invece di
    pretendere obbedienza.
    """
    t = (testo or '').strip()
    t = re.sub(r'^```(?:json)?|```$', '', t, flags=re.M).strip()
    inizio = t.find('{')
    if inizio < 0:
        return None
    profondita = 0
    for i, ch in enumerate(t[inizio:], inizio):
        if ch == '{':
            profondita += 1
        elif ch == '}':
            profondita -= 1
            if profondita == 0:
                try:
                    return json.loads(t[inizio:i + 1])
                except Exception:
                    return None
    return None


def testo_capitolo(n):
    f = os.path.join(CAPITOLI, 'cap%02d.txt' % n)
    if not os.path.exists(f):
        return None
    return open(f, encoding='utf-8', errors='replace').read()


def estrai(n, testo):
    messaggi = [
        {'role': 'system', 'content': ISTRUZIONI},
        {'role': 'user', 'content': 'CAPITOLO %d\n\n%s' % (n, testo)},
    ]
    risposta = call_lmstudio_chat(messaggi, BASE_URL, MODELLO,
                                  max_tokens=1600, temperature=0.1)
    if isinstance(risposta, dict):
        risposta = (risposta.get('content') or risposta.get('text') or '')
    return solo_json(risposta)


def main():
    da, a = 1, 66
    if len(sys.argv) > 2:
        da, a = int(sys.argv[1]), int(sys.argv[2])
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    c.commit()

    fatti = saltati = falliti = 0
    for n in range(da, a + 1):
        gia = c.execute('select 1 from canone_estratto where capitolo=?', (n,)).fetchone()
        if gia:
            saltati += 1
            continue
        testo = testo_capitolo(n)
        if not testo:
            print('#cap%02d: file assente' % n, flush=True)
            continue
        t0 = time.time()
        try:
            d = estrai(n, testo)
        except Exception as e:
            print('#cap%02d: errore %s' % (n, str(e)[:90]), flush=True)
            falliti += 1
            continue
        if not d:
            print('#cap%02d: risposta non interpretabile' % n, flush=True)
            falliti += 1
            continue
        c.execute("""INSERT OR REPLACE INTO canone_estratto
            (capitolo,titolo,pov,luogo,data_narrativa,personaggi,riassunto,
             eventi_chiave,oggetti_simboli,incongruenze,caratteri,estratto_il)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""", (
            n, d.get('titolo'), d.get('pov'), d.get('luogo'),
            d.get('data_narrativa'),
            ', '.join(d.get('personaggi') or []) if isinstance(d.get('personaggi'), list) else d.get('personaggi'),
            d.get('riassunto'),
            json.dumps(d.get('eventi_chiave') or [], ensure_ascii=False),
            json.dumps(d.get('oggetti_simboli') or [], ensure_ascii=False),
            json.dumps(d.get('incongruenze') or [], ensure_ascii=False),
            len(testo)))
        c.commit()
        fatti += 1
        print('#cap%02d ok in %.0fs | %s | POV %s | %s' % (
            n, time.time() - t0, str(d.get('titolo'))[:26],
            str(d.get('pov'))[:12], str(d.get('data_narrativa'))[:20]), flush=True)

    print('#FINE: %d estratti, %d gia presenti, %d falliti' % (fatti, saltati, falliti), flush=True)


if __name__ == '__main__':
    main()
