# -*- coding: utf-8 -*-
"""Fa scrivere un capitolo al modello locale, con il canone in mano.

IL PROBLEMA CHE RISOLVE. Il progetto aveva i due pezzi giusti e non li aveva
mai uniti: `compila_iterativo.py` costruisce un ottimo pacchetto di contesto
ma si ferma a stamparlo perche' qualcuno lo copi a mano; `expand_chapters.py`
chiama il modello ma non gli passa NIENTE del canone - ne' punto di vista, ne'
data, ne' chi c'e', ne' a cosa serve il capitolo - e per giunta sovrascrive il
file originale.

E' esattamente cosi' che e' nato l'"Ispettore Chen": chiedi a un modello di
allungare un capitolo senza dirgli nulla del libro, e lui inventa un
personaggio per riempire lo spazio.

COSA FA QUESTO. Prende il canone dal database, ci aggiunge i fili narrativi da
raccogliere e i capitoli vicini, lo consegna al modello locale, e poi
CONTROLLA quello che e' tornato: la lunghezza, il punto di vista, i fili
raccolti, e soprattutto se sono comparsi nomi che nel romanzo non esistono.

NON SOVRASCRIVE MAI. Il capitolo nuovo va in capitoli_generati/, accanto
all'originale, perche' li si possa confrontare.
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
USCITA = os.path.join(BASE, 'capitoli_generati')
BASE_URL = os.environ.get('SCRIVI_BASE_URL', 'http://192.168.1.51:8088')
MODELLO = os.environ.get('SCRIVI_MODEL', 'gemma')

VOCE = """Sei il romanziere di "Prima vivi poi spieghi". Scrivi in italiano.

Lo stile del libro, che devi tenere: crudo, fisico, logistico. Si racconta
per azioni, oggetti, odori, procedure, dolore del corpo. Niente commenti
morali, niente frasi che spiegano il significato di quello che accade: il
significato sta nei fatti. I dialoghi sono spezzati, la gente non fa discorsi.

Come si chiude un simbolo in questo libro: senza nominarlo. Nel capitolo 63
Artem posa sul granito di una cucina americana il cucchiaio piegato della
casa bombardata dove Lin lo salvo' cinquant'anni prima. Nessuno spiega niente.
L'oggetto viene messo dove non c'entra piu', e basta.

Regole non negoziabili:
- Scrivi SOLO il testo del capitolo. Nessuna nota, nessun commento, nessun
  titolo aggiunto, nessun "ecco il capitolo".
- Non inventare personaggi. Usa solo quelli elencati nel canone qui sotto.
  Un nome nuovo e' un errore, non una trovata.
- Non cambiare cosa succede: la funzione narrativa e' decisa.
- Rispetta il punto di vista indicato. Se e' Artem, si sta nella sua testa e
  non si sa cosa pensano gli altri."""


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def nomi_canonici(c):
    return [r['nome'] for r in c.execute('select nome from personaggi order by id')]


def pacchetto(c, n):
    """Tutto quello che serve per scrivere il capitolo n, dal database."""
    cap = c.execute('select * from capitoli where id=?', (n,)).fetchone()
    if not cap:
        raise SystemExit('capitolo %d inesistente' % n)
    cap = dict(cap)

    vicini = []
    for m in (n - 2, n - 1, n + 1):
        v = c.execute('select id,titolo,pov,data_narrativa,riassunto from capitoli where id=?',
                      (m,)).fetchone()
        if v:
            quando = 'PRIMA' if m < n else 'DOPO'
            vicini.append('[%s] Cap %d "%s" (POV %s, %s): %s' % (
                quando, v['id'], v['titolo'], v['pov'], v['data_narrativa'],
                (v['riassunto'] or '')[:420]))

    presenti = [x.strip() for x in re.split(r'[,;/]', cap.get('personaggi_capitolo') or '') if x.strip()]
    schede = []
    for p in presenti:
        r = c.execute('select nome,ruolo,background,tratti_psicologici,arco_narrativo '
                      'from personaggi where lower(nome)=lower(?)', (p,)).fetchone()
        if r:
            schede.append('- %s (%s): %s | %s' % (
                r['nome'], r['ruolo'] or '', (r['background'] or '')[:260],
                (r['tratti_psicologici'] or '')[:110]))

    fili = []
    for f in c.execute("select * from fili_narrativi where stato in ('aperto','da verificare')"):
        if str(n) in re.split(r'[,\s(]+', f['raccolta'] or ''):
            fili.append('DA CHIUDERE QUI - "%s": %s\n  Come e stato piantato: %s' % (
                f['nome'], f['principio'], (f['riscontri'] or '')[:400]))
    return cap, vicini, schede, fili


def prompt(c, n):
    cap, vicini, schede, fili = pacchetto(c, n)
    obiettivo = cap.get('parole_obiettivo') or 5000
    testo = ''
    f = os.path.join(BASE, 'capitoli', 'cap%02d.txt' % n)
    if os.path.exists(f):
        testo = open(f, encoding='utf-8', errors='replace').read()

    pezzi = [
        'CAPITOLO %d — "%s"' % (n, cap['titolo']),
        'PUNTO DI VISTA: %s' % cap['pov'],
        'LUOGO: %s' % cap['luogo'],
        'QUANDO: %s' % cap['data_narrativa'],
        '',
        'A COSA SERVE QUESTO CAPITOLO (deciso, non negoziabile):',
        cap.get('funzione_narrativa') or cap.get('descrizione') or '',
        '',
        'LUNGHEZZA RICHIESTA: circa %d parole. E la lunghezza che il canone '
        'assegna a questo capitolo: non e un suggerimento.' % obiettivo,
    ]
    if cap.get('scene_outline'):
        pezzi += ['', 'SCENE DA ATTRAVERSARE:', cap['scene_outline'][:2200]]
    if cap.get('obiettivi_personaggi'):
        pezzi += ['', 'COSA VUOLE CIASCUNO IN QUESTO CAPITOLO:', cap['obiettivi_personaggi'][:1200]]
    if schede:
        pezzi += ['', 'CHI C\'E (usa SOLO questi):'] + schede
    if fili:
        pezzi += ['', '>>> FILI NARRATIVI CHE SI CHIUDONO QUI <<<'] + fili
    if vicini:
        pezzi += ['', 'COSA SUCCEDE INTORNO (non contraddirlo):'] + vicini
    if cap.get('hook_finale'):
        pezzi += ['', 'COME DEVE FINIRE:', cap['hook_finale'][:600]]
    if testo:
        pezzi += ['', 'BOZZA ATTUALE DA RISCRIVERE ED ESPANDERE '
                      '(tieni quello che funziona, non buttarlo):', testo[:14000]]
    pezzi += ['', 'Ora scrivi il capitolo completo. Solo il testo.']
    return '\n'.join(pezzi), obiettivo


def verifica(c, n, testo, obiettivo):
    """Controlla il capitolo tornato indietro. E' la parte che manca a chi
    genera e basta: senza, non si sa se e uscito qualcosa di usabile."""
    esiti = []
    parole = len(testo.split())
    esiti.append(('lunghezza', parole, '%d/%d (%.0f%%)' % (parole, obiettivo, 100 * parole / obiettivo),
                  parole >= obiettivo * 0.75))

    canonici = {x.lower() for x in nomi_canonici(c)}
    # Nomi propri sospetti: maiuscoli isolati, non a inizio frase.
    candidati = set(re.findall(r'(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{3,})\b', testo, re.M))
    comuni = {'Sinai', 'Israele', 'Gaza', 'Teheran', 'Ucraina', 'Donbass', 'Maryland',
              'Ginevra', 'Cisgiordania', 'Giordania', 'Anakara', 'Arkana', 'Comitato',
              'Quando', 'Poi', 'Adesso', 'Dopo', 'Prima', 'Niente', 'Forse', 'Aveva',
              'Erano', 'Nessuno', 'Ogni', 'Tutto', 'Sotto', 'Sopra', 'Ancora'}
    nuovi = sorted(x for x in candidati if x.lower() not in canonici and x not in comuni)[:12]
    esiti.append(('nomi non canonici', len(nuovi), ', '.join(nuovi) or 'nessuno', not nuovi))

    cap = c.execute('select pov from capitoli where id=?', (n,)).fetchone()
    pov = (cap['pov'] or '').split('/')[0].strip()
    esiti.append(('il POV compare', testo.count(pov), '%s citato %d volte' % (pov, testo.count(pov)),
                  testo.count(pov) > 0))

    for f in c.execute("select nome from fili_narrativi where stato='aperto'"):
        chiave = f['nome'].split()[0].lower()
        n_occ = testo.lower().count(chiave)
        esiti.append(('filo "%s"' % f['nome'], n_occ, '%d occorrenze' % n_occ, None))
    return esiti


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 59
    c = conn()
    p, obiettivo = prompt(c, n)
    print('#prompt: %d caratteri, obiettivo %d parole' % (len(p), obiettivo), flush=True)
    os.makedirs(USCITA, exist_ok=True)
    open(os.path.join(USCITA, 'cap%02d.prompt.txt' % n), 'w', encoding='utf-8').write(p)

    t0 = time.time()
    r = call_lmstudio_chat(
        [{'role': 'system', 'content': VOCE}, {'role': 'user', 'content': p}],
        BASE_URL, MODELLO, max_tokens=16000, temperature=0.85)
    if isinstance(r, dict):
        r = r.get('content') or r.get('text') or ''
    r = (r or '').strip()
    print('#generato in %.0f s' % (time.time() - t0), flush=True)

    f = os.path.join(USCITA, 'cap%02d.txt' % n)
    open(f, 'w', encoding='utf-8').write(r)
    print('#scritto in %s' % f)

    print('#--- verifica ---')
    for nome, _v, testo, ok in verifica(c, n, r, obiettivo):
        segno = '  ' if ok is None else ('OK' if ok else 'NO')
        print('#%s %-24s %s' % (segno, nome, testo))


if __name__ == '__main__':
    main()
