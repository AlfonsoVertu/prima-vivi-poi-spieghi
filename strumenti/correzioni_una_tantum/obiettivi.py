# -*- coding: utf-8 -*-
"""Porta nel database gli obiettivi di lunghezza e la funzione narrativa che
CANONE_DEFINITIVO.md assegna a ogni capitolo.

PERCHE'. Il canone dice quanto deve essere lungo ogni capitolo e cosa deve
farci succedere, ma sta in un file Markdown che il programma non legge. Il
risultato e' che nessuno sapeva che il romanzo e' al 53% del previsto, e che
quattro capitoli sono finiti mentre gli altri sono abbozzi.

Chi genera un capitolo deve sapere due cose che finora non aveva: quanto
scrivere, e a cosa serve quel capitolo dentro il libro.
"""
import os
import re
import sqlite3

D = '/home/pos/progetti/prima-vivi-poi-spieghi'
c = sqlite3.connect(D + '/roman.db')

c.executescript("""
ALTER TABLE capitoli ADD COLUMN parole_obiettivo INTEGER;
""") if not [r for r in c.execute('PRAGMA table_info(capitoli)') if r[1] == 'parole_obiettivo'] else None
if not [r for r in c.execute('PRAGMA table_info(capitoli)') if r[1] == 'funzione_narrativa']:
    c.execute('ALTER TABLE capitoli ADD COLUMN funzione_narrativa TEXT')

t = open(D + '/CANONE_DEFINITIVO.md', encoding='utf-8', errors='replace').read()

# "12. Gamba schiacciata — 15 pagineLin entra nella casa, trova Artem..."
# Le pagine e la funzione sono attaccate senza spazio: il file e' stato
# incollato da una chat e ha perso gli a capo.
righe = re.findall(r'^(\d{1,2})\.\s+(.+?)\s+—\s+(\d+)\s+pagine(.*)$', t, re.M)
print('#capitoli letti dal canone: %d' % len(righe))

aggiornati = 0
for num, titolo, pagine, funzione in righe:
    n = int(num)
    obiettivo = int(pagine) * 500          # il canone fissa 1 pagina = 500 parole
    funzione = funzione.strip()
    c.execute('update capitoli set parole_obiettivo=?, funzione_narrativa=? where id=?',
              (obiettivo, funzione, n))
    aggiornati += c.total_changes and 1 or 0

# Lo stato dice a colpo d'occhio cosa manca. Le soglie non sono arbitrarie:
# sotto il 40% il capitolo e' una traccia, non un capitolo.
for r in list(c.execute('select id, parole_obiettivo from capitoli where parole_obiettivo is not null')):
    n, obj = r
    f = '%s/capitoli/cap%02d.txt' % (D, n)
    reali = len(open(f, encoding='utf-8', errors='replace').read().split()) if os.path.exists(f) else 0
    q = reali / obj if obj else 0
    stato = ('completo' if q >= 0.9 else
             'da_espandere' if q >= 0.4 else
             'abbozzo')
    # I due con il personaggio inesistente restano marcati a parte: li' non
    # basta allungare, va rifatto il contenuto.
    if n in (3, 4):
        stato = 'da_rigenerare'
    c.execute('update capitoli set parole_file=?, stato=? where id=?', (reali, stato, n))

c.commit()
print('#obiettivi scritti su %d capitoli' % len(righe))
for s, n in c.execute('select stato, count(*) from capitoli group by stato order by count(*) desc'):
    print('#  %-16s %d capitoli' % (s, n))
