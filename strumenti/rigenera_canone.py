# -*- coding: utf-8 -*-
"""Rigenera CANONE_AGGIORNATO.md dal database.

COM'ERA. Un file su una riga sola, con gli a capo scritti come "\\n" letterali
e tutti i conteggi parole a zero. Generato male da qualcosa e mai riletto da
nessuno: illeggibile per una persona e inutile per un programma.

COSA DIVENTA. Lo stato reale del manoscritto, preso dal database e dai file:
titolo, punto di vista, quando, quanto e' lungo, quanto dovrebbe esserlo
secondo CANONE_DEFINITIVO.md, e a che punto sta. Serve a rispondere in dieci
secondi alla domanda "a che punto siamo", che finora richiedeva di aprire
sessantasei file.

CANONE_DEFINITIVO.md resta la fonte: quello lo scrive l'autore, questo lo
scrive il programma.
"""
import os
import sqlite3

D = '/home/pos/progetti/prima-vivi-poi-spieghi'
c = sqlite3.connect(D + '/roman.db')
c.row_factory = sqlite3.Row

righe = [dict(r) for r in c.execute('select * from capitoli order by id')]
tot_reali = tot_obiettivo = 0
corpo = []

BLOCCHI = {1: 'BLOCCO I — Lin', 11: 'BLOCCO II — Donbass, Artem, Sergej',
           19: 'BLOCCO III — Artem USA, NATO/ONU', 26: 'BLOCCO IV — Omar e Liah',
           34: 'BLOCCO V — Yusuf ed Eitan', 40: 'BLOCCO VI — Andriy',
           45: 'BLOCCO VII — Neda, carcere, fuga',
           55: 'BLOCCO VIII — convergenza, Sinai, epilogo'}

for r in righe:
    n = r['id']
    if n in BLOCCHI:
        corpo.append('')
        corpo.append('### %s' % BLOCCHI[n])
        corpo.append('')
        corpo.append('| Cap | Titolo | POV | Quando | Parole | Obiettivo | % | Stato |')
        corpo.append('|---|---|---|---|---|---|---|---|')
    f = '%s/capitoli/cap%02d.txt' % (D, n)
    reali = len(open(f, encoding='utf-8', errors='replace').read().split()) if os.path.exists(f) else 0
    obj = r.get('parole_obiettivo') or 0
    tot_reali += reali
    tot_obiettivo += obj
    perc = ('%.0f%%' % (100 * reali / obj)) if obj else '-'
    corpo.append('| %02d | %s | %s | %s | %d | %d | %s | %s |' % (
        n, r.get('titolo') or '', r.get('pov') or '', r.get('data_narrativa') or '',
        reali, obj, perc, r.get('stato') or ''))

stati = {}
for r in righe:
    stati[r.get('stato') or '?'] = stati.get(r.get('stato') or '?', 0) + 1

testa = [
    '# Stato del manoscritto — Prima vivi poi spieghi',
    '',
    '> Generato da `strumenti/rigenera_canone.py` a partire da `roman.db` e dai',
    '> file dei capitoli. **Non si modifica a mano**: si rigenera.',
    '> La fonte del canone e\' `CANONE_DEFINITIVO.md`, che invece scrive l\'autore.',
    '',
    '## A che punto siamo',
    '',
    '| | |',
    '|---|---|',
    '| Parole scritte | **%d** |' % tot_reali,
    '| Obiettivo dal canone | %d |' % tot_obiettivo,
    '| Completamento | **%.0f%%** |' % (100 * tot_reali / tot_obiettivo if tot_obiettivo else 0),
    '| Capitoli | %d |' % len(righe),
    '',
    '**Stato dei capitoli:** ' + ', '.join('%s %d' % (k, v) for k, v in
                                           sorted(stati.items(), key=lambda x: -x[1])),
    '',
    '- `completo` — almeno il 90% dell\'obiettivo del canone',
    '- `da_espandere` — fra il 40% e il 90%',
    '- `abbozzo` — sotto il 40%: e\' una traccia, non un capitolo',
    '- `da_rigenerare` — il testo non e\' utilizzabile e va rifatto',
    '',
    '## Capitolo per capitolo',
]

open(D + '/CANONE_AGGIORNATO.md', 'w', encoding='utf-8').write(
    '\n'.join(testa + corpo) + '\n')
print('#CANONE_AGGIORNATO.md rigenerato: %d capitoli, %d parole su %d (%.0f%%)'
      % (len(righe), tot_reali, tot_obiettivo, 100 * tot_reali / tot_obiettivo))
