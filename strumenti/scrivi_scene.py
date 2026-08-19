# -*- coding: utf-8 -*-
"""Scrive un capitolo una scena alla volta, fino a raggiungere le parole.

PERCHE' A SCENE. Chiedere seimila parole in un colpo a un modello da 12
miliardi di parametri non funziona: al primo tentativo ne ha rese 1676 su 6000
e ha ignorato il filo narrativo che gli era stato chiesto di chiudere, perche'
l'istruzione era sepolta a meta' di quattordicimila caratteri di prompt.

A scene funziona per due motivi. La richiesta e' corta e l'istruzione che
conta sta vicino al punto in cui serve - il filo dell'aikido si nomina solo
nella scena in cui va chiuso, e li' il modello non puo' non vederlo. E la
lunghezza si accumula invece di doverla produrre tutta insieme.

Ogni scena vede quello che e' stato scritto prima, perche' altrimenti
ricomincia da capo a descrivere il tramonto.
"""
import os
import re
import sqlite3
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from llm_client import call_lmstudio_chat  # noqa: E402

DB = os.path.join(BASE, 'roman.db')
USCITA = os.path.join(BASE, 'capitoli_generati')
BASE_URL = os.environ.get('SCRIVI_BASE_URL', 'http://192.168.1.51:8088')
MODELLO = os.environ.get('SCRIVI_MODEL', 'gemma')

VOCE = """Sei il romanziere di "Prima vivi poi spieghi". Scrivi in italiano.

Lo stile: crudo, fisico, logistico. Si racconta per azioni, oggetti, odori,
procedure, dolore del corpo. Niente commenti morali. Niente frasi che spiegano
il significato di cio' che accade: il significato sta nei fatti. I dialoghi
sono spezzati, la gente non fa discorsi.

Come si chiude un simbolo in questo libro: senza nominarlo. Nel capitolo 63
Artem posa sul granito di una cucina americana il cucchiaio piegato della casa
bombardata dove Lin lo salvo'. Nessuno spiega niente: l'oggetto viene messo
dove non c'entra piu', e basta.

Regole non negoziabili:
- Scrivi SOLO prosa narrativa. Niente titoli, niente "Scena 3", niente note.
- Non inventare personaggi: usa solo quelli elencati.
- Resta nel punto di vista indicato: si vede cosa fanno gli altri, non cosa
  pensano."""


def scomponi(outline):
    """Le scene dall'outline, piu' le note finali che valgono per tutte."""
    note = ''
    m = re.search(r'^NOTE PER CHI SCRIVE:(.*)$', outline, re.S | re.M)
    if m:
        note = m.group(1).strip()
        outline = outline[:m.start()]
    pezzi = re.split(r'\n(?=Scena \d+)', outline.strip())
    return [p.strip() for p in pezzi if p.strip().startswith('Scena')], note


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 59
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    cap = dict(c.execute('select * from capitoli where id=?', (n,)).fetchone())
    scene, note = scomponi(cap.get('scene_outline') or '')
    if not scene:
        raise SystemExit('cap%02d: nessuna scena nell outline' % n)

    obiettivo = cap.get('parole_obiettivo') or 5000
    per_scena = int(obiettivo / len(scene))
    personaggi = [r['nome'] for r in c.execute('select nome from personaggi')]

    fili = list(c.execute("select nome, principio, riscontri from fili_narrativi "
                          "where stato='aperto' and raccolta like ?", ('%%%d%%' % n,)))

    intestazione = (
        'CAPITOLO %d — "%s"\nPUNTO DI VISTA: %s\nLUOGO: %s\nQUANDO: %s\n'
        'PERSONAGGI ESISTENTI (solo questi): %s'
        % (n, cap['titolo'], cap['pov'], cap['luogo'], cap['data_narrativa'],
           ', '.join(personaggi)))

    print('#cap%02d: %d scene, obiettivo %d parole (~%d a scena)'
          % (n, len(scene), obiettivo, per_scena), flush=True)

    pezzi_scritti = []
    for i, s in enumerate(scene, 1):
        finora = '\n\n'.join(pezzi_scritti)
        coda = finora[-2600:] if finora else '(sei all inizio del capitolo)'
        richiesta = [intestazione, '', 'SCENA DA SCRIVERE ADESSO:', s, '',
                     'COME FINIVA IL TESTO FINO A QUI:', coda, '',
                     'Scrivi questa scena, circa %d parole. Solo prosa.' % per_scena]
        # Il filo si nomina SOLO nella scena in cui va chiuso: cosi' non e'
        # una riga fra tante, e' l'istruzione della richiesta.
        if fili and ('IL PUNTO DEL CAPITOLO' in s.upper() or i == len(scene) - 1):
            for f in fili:
                richiesta.insert(4, '>>> QUESTA SCENA CHIUDE UN FILO APERTO DA %d CAPITOLI <<<\n'
                                    '"%s": %s\nCome era stato piantato: %s'
                                 % (43, f['nome'], f['principio'], (f['riscontri'] or '')[:340]))
        if note:
            richiesta += ['', 'DA RISPETTARE IN TUTTO IL CAPITOLO:', note]

        t0 = time.time()
        r = call_lmstudio_chat(
            [{'role': 'system', 'content': VOCE}, {'role': 'user', 'content': '\n'.join(richiesta)}],
            BASE_URL, MODELLO, max_tokens=4000, temperature=0.85)
        if isinstance(r, dict):
            r = r.get('content') or r.get('text') or ''
        testo = (r or '').strip()
        pezzi_scritti.append(testo)
        print('#  scena %d: %d parole in %.0fs (totale %d)'
              % (i, len(testo.split()), time.time() - t0,
                 sum(len(x.split()) for x in pezzi_scritti)), flush=True)

    completo = '\n\n'.join(pezzi_scritti)
    os.makedirs(USCITA, exist_ok=True)
    f = os.path.join(USCITA, 'cap%02d.txt' % n)
    open(f, 'w', encoding='utf-8').write(completo)
    parole = len(completo.split())
    print('#TOTALE: %d parole su %d (%.0f%%) -> %s'
          % (parole, obiettivo, 100 * parole / obiettivo, f))


if __name__ == '__main__':
    main()
