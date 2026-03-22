"""
compila_iterativo.py — Itera i capitoli e produce il pacchetto contestuale
per scrivere/espandere ogni capitolo con le info necessarie.

Uso:
  python compila_iterativo.py          # mostra tutti i capitoli da completare
  python compila_iterativo.py 5        # pacchetto completo per il cap 5
  python compila_iterativo.py 5 --prompt  # + prompt AI pronto al copy-paste
  python compila_iterativo.py next     # prossimo capitolo da scrivere (bozza o vuoto)
"""
import sqlite3, sys, os, textwrap

DB_PATH = "roman.db"
CAPITOLI_DIR = "capitoli"

def get_conn():
    if not os.path.exists(DB_PATH):
        print("Esegui prima: python setup_db.py"); sys.exit(1)
    return sqlite3.connect(DB_PATH)

def get_cap(conn, cap_id):
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM capitoli WHERE id=?", (cap_id,)).fetchone()
    if row:
        return dict(row)
    return None

def leggi_file(cap_id):
    path = os.path.join(CAPITOLI_DIR, f"cap{cap_id:02d}.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None

def pacchetto_capitolo(cap_id, include_prompt=False):
    conn = get_conn()
    cap = get_cap(conn, cap_id)
    if not cap:
        print(f"Capitolo {cap_id} non trovato."); return

    prev1 = get_cap(conn, cap_id - 1) if cap_id > 1 else None
    prev2 = get_cap(conn, cap_id - 2) if cap_id > 2 else None
    next1 = get_cap(conn, cap_id + 1) if cap_id < 66 else None
    conn.close()

    sep = "=" * 65

    print(f"\n{sep}")
    print(f"  PACCHETTO CAPITOLO {cap_id:02d} — {cap['titolo']}")
    print(f"{sep}")

    print(f"\n  POV: {cap['pov']}   |   LUOGO: {cap['luogo']}")
    print(f"  DATA: {cap['data_narrativa']}   |   STATO: {cap['stato']}  |  PAROLE FILE: {cap['parole_file']}")

    print(f"\n{'—'*65}")
    print(f"  TIMELINE OPERA")
    print(f"{'—'*65}")
    print(f"  {cap['timeline_opera'] or '(non compilata)'}")

    print(f"\n{'—'*65}")
    print(f"  DESCRIZIONE DEL CAPITOLO")
    print(f"{'—'*65}")
    for l in textwrap.wrap(cap['descrizione'] or '(non compilata)', 63):
        print(f"  {l}")

    print(f"\n{'—'*65}")
    print(f"  CONTESTO DAI 2 CAPITOLI PRECEDENTI")
    print(f"{'—'*65}")
    for prev in [prev2, prev1]:
        if prev:
            riass = prev['riassunto'] or prev['descrizione'] or '(riassunto non compilato)'
            print(f"  Cap {prev['id']:02d} [{prev['titolo']}] ({prev['pov']}, {prev['data_narrativa']}):")
            for l in textwrap.wrap(riass[:300], 61):
                print(f"    {l}")

    print(f"\n{'—'*65}")
    print(f"  INFO SUI PERSONAGGI — DA SAPERE PRIMA")
    print(f"{'—'*65}")
    for l in textwrap.wrap(cap['personaggi_precedenti'] or '(non compilato)', 63):
        print(f"  {l}")

    print(f"\n{'—'*65}")
    print(f"  COSA DEVE SUCCEDERE IN BACKGROUND")
    print(f"{'—'*65}")
    for l in textwrap.wrap(cap['background'] or '(non compilato)', 63):
        print(f"  {l}")

    print(f"\n{'—'*65}")
    print(f"  COSA SUCCEDE ALTROVE IN QUESTO MOMENTO")
    print(f"{'—'*65}")
    for l in textwrap.wrap(cap['parallelo'] or '(non compilato)', 63):
        print(f"  {l}")

    print(f"\n{'—'*65}")
    print(f"  OBIETTIVI DEI PERSONAGGI IN QUESTO CAPITOLO")
    print(f"{'—'*65}")
    for l in textwrap.wrap(cap['obiettivi_personaggi'] or '(non compilato)', 63):
        print(f"  {l}")

    print(f"\n{'—'*65}")
    print(f"  TIMELINE DEL CAPITOLO")
    print(f"{'—'*65}")
    for l in textwrap.wrap(cap['timeline_capitolo'] or '(non compilata)', 63):
        print(f"  {l}")

    if next1:
        print(f"\n{'—'*65}")
        print(f"  INFO PERSONAGGI DA CONSIDERARE PER IL CAPITOLO SUCCESSIVO")
        print(f"{'—'*65}")
        for l in textwrap.wrap(cap['personaggi_successivi'] or '(non compilato)', 63):
            print(f"  {l}")
        print(f"  >>> Prossimo: Cap {next1['id']:02d} [{next1['titolo']}] — {next1['pov']} @ {next1['luogo']}")

    # Anteprima file se esiste
    testo = leggi_file(cap_id)
    if testo:
        parole = len(testo.split())
        print(f"\n{'—'*65}")
        print(f"  TESTO EXISTENTE: capitoli/cap{cap_id:02d}.txt ({parole} parole)")
        print(f"{'—'*65}")
        preview = testo[:500].replace("\n\n", "\n")
        for l in preview.split("\n"):
            print(f"  {l}")
        print(f"  ... [{parole - len(preview.split())} parole rimanenti]")

    if include_prompt:
        print(f"\n{'='*65}")
        print(f"  PROMPT AI PRONTO (cap {cap_id:02d})")
        print(f"{'='*65}")
        prompt = build_prompt(cap, prev1, prev2)
        print(prompt)

    print(f"\n{sep}\n")

def estrai_snippet(cap_id, num_parole, dalla_fine=False):
    """Estrae un numero specifico di parole dall'inizio o dalla fine di un capitolo."""
    testo = leggi_file(cap_id)
    if not testo: return ""
    parole = testo.split()
    if dalla_fine:
        snippet = " ".join(parole[-num_parole:])
    else:
        snippet = " ".join(parole[:num_parole])
    return snippet

def build_prompt(cap, prev1, prev2, next1=None):
    ctx_prev = ""
    for prev in [prev2, prev1]:
        if prev:
            ctx_prev += f"- Cap {prev['id']:02d} [{prev['titolo']}, POV {prev['pov']}]: {(prev.get('riassunto_capitolo_successivo') or prev.get('riassunto') or prev.get('descrizione', ''))}\n"
    
    # Coherence Buffers
    snippet_prev = estrai_snippet(prev1['id'], 200, dalla_fine=True) if prev1 else ""
    snippet_next = estrai_snippet(next1['id'], 100, dalla_fine=False) if next1 else ""
    
    buffer_precedente = ""
    if prev1:
        buffer_precedente = f"""
--- BUFFER DI COERENZA (PRECEDENTE) ---
RIASSUNTO CAPITOLO PRECEDENTE (dal database del cap attuale): {cap.get('riassunto_capitolo_precedente', 'N/D')}
RIASSUNTO EFFETTIVO CAPITOLO {prev1['id']} (dal database): {prev1.get('riassunto', 'N/D')}
ULTIME 200 PAROLE DEL CAPITOLO {prev1['id']}:
{snippet_prev}
---------------------------------------
"""

    buffer_successivo = ""
    if next1:
        buffer_successivo = f"""
--- BUFFER DI COERENZA (SUCCESSIVO) ---
RIASSUNTO CAPITOLO SUCCESSIVO (dal database del cap attuale): {cap.get('riassunto_capitolo_successivo', 'N/D')}
RIASSUNTO EFFETTIVO CAPITOLO {next1['id']} (dal database): {next1.get('riassunto', 'N/D')}
PRIME 100 PAROLE DEL CAPITOLO {next1['id']}:
{snippet_next}
---------------------------------------
"""

    prompt = f"""Sei il co-autore del romanzo "Prima Vivi Poi Spieghi".
Sottotitolo: {os.getenv('PROJECT_SUBTITLE', '')}

CANONE DA RISPETTARE:
- Stile: prima persona, emotivo, crudo, realistico
- Nessun trionfalismo. In ogni salvataggio molti altri muoiono.
- Età: Lin 1978 | Michael 1955 | Artem 2001 | Sergej 1972 | Omar 2003 | Leah 1953 | Yusuf 2010 | Eitan 1999 | Andriy 2002 | Neda 2006
- Il motto "Prima vivi poi spieghi" viene da LIN che muore nel 2014, NON da Sergio/padre
- Leah (non Liah) nata 1953 = 73 anni nel 2026

CONTESTO DAI CAPITOLI PRECEDENTI:
{ctx_prev or '(inizio romanzo)'}

{buffer_precedente}
{buffer_successivo}

DATI TECNICI CAPITOLO {cap['id']:02d}:
Titolo: {cap['titolo']}
POV: {cap['pov']}
Linea Narrativa: {cap.get('linea_narrativa', 'Principale')}
Anno: {cap.get('anno', '')} | Data narrativa: {cap['data_narrativa']}
Luogo Macro: {cap.get('luogo_macro', '')} | Luogo Specifico: {cap['luogo']}
Tensione: {cap.get('tensione_capitolo') or 'crescente'}
Target: {cap.get('parole_target') or '2.500'} parole.

DESCRIZIONE NARRATIVA:
{cap.get('descrizione', '(non disponibile)')}

OBIETTIVI PERSONAGGI (Cosa succede in primo piano):
{cap.get('obiettivi_personaggi') or '(non specificati)'}

PERSONAGGI IN SCENA:
{cap.get('personaggi_capitolo', '')}

INFO BACKGROUND / COSA SUCCEDE ALTROVE:
- Background: {cap.get('background') or '(nessuno specifico)'}
- Parallelo: {cap.get('parallelo') or '(nessuno specifico)'}

RISCHI DI INCOERENZA (DA EVITARE ASSOLUTAMENTE):
{cap.get('rischi_incoerenza', 'Nessuno segnalato.')}

STRUTTURA DA SEGUIRE (SCENE OUTLINE):
{cap.get('scene_outline') or 'Libera ma in 3 atti (vita, transizione, pressione).'}

DETTAGLI STILISTICI:
- Oggetti Simbolo: {cap.get('oggetti_simbolo') or 'Qualcosa di quotidiano e consumato.'}
- Hook Finale: {cap.get('hook_finale') or 'Una tensione interrotta, un dubbio insinuato.'}
- Transizione: {cap.get('transizione_prossimo_capitolo') or "Prepara l'entrata del POV successivo."}

SCRIVI: In italiano, stile letterario crudo, prima persona vissuta. No spiegoni. Mostra tutto attraverso i sensi e le azioni del POV.
"""
    return prompt

def cmd_next():
    conn = get_conn()
    row = conn.execute("SELECT id, titolo, parole_file FROM capitoli WHERE parole_file=0 OR stato='bozza' ORDER BY id LIMIT 1").fetchone()
    conn.close()
    if row:
        print(f"\nProssimo capitolo da scrivere: Cap {row[0]:02d} — {row[1]} ({row[2]} parole)")
        print(f"Esegui: python compila_iterativo.py {row[0]} --prompt")
    else:
        print("Tutti i capitoli hanno testo. Ottimo!")

def cmd_lista_lavoro():
    conn = get_conn()
    rows = conn.execute("SELECT id, titolo, pov, stato, parole_file FROM capitoli ORDER BY id").fetchall()
    conn.close()
    print(f"\n{'ID':>3}  {'TITOLO':<28} {'POV':<12} {'STATO':<10} {'PAROLE':>7}")
    print("-"*65)
    for r in rows:
        mark = "✓" if r[4] >= 1800 else ("~" if r[4] > 0 else " ")
        print(f"{r[0]:>3}. {mark} {r[1]:<27} {r[2]:<12} {r[3]:<10} {r[4]:>7}")
    print()

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "list":
        cmd_lista_lavoro()
    elif args[0] == "next":
        cmd_next()
    else:
        try:
            cap_id = int(args[0])
            include_prompt = "--prompt" in args
            pacchetto_capitolo(cap_id, include_prompt)
        except ValueError:
            print("Uso: python compila_iterativo.py [N | list | next] [--prompt]")
