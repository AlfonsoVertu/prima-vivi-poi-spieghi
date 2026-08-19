# -*- coding: utf-8 -*-
"""Riporta punto di vista e data dei capitoli sfasati a quello che dice il testo.

SU COSA CI SI BASA. Non sull'estrazione da sola: su tre riscontri che
concordano. Il file del capitolo, il canone (che assegna quei capitoli al
blocco Yusuf/Eitan) e la lettura del testo dicono la stessa cosa; il database
dice il capitolo precedente. Dove i tre non concordano, non si tocca niente.

PERCHE' IMPORTA. Questi campi sono cio' che si consegna al modello per
riscrivere un capitolo. Con il punto di vista sbagliato, il capitolo viene
riscritto dalla testa della persona sbagliata.
"""
import sqlite3

D = '/home/pos/progetti/prima-vivi-poi-spieghi'
c = sqlite3.connect(D + '/roman.db')
c.row_factory = sqlite3.Row

# La fascia provata sfasata dal confronto titoli con CANONE_DEFINITIVO.md
SFASATI = [27, 28, 30, 32, 33, 34, 35, 36, 38, 39, 41, 42, 43, 44]

estratti = {r['capitolo']: dict(r) for r in c.execute('select * from canone_estratto')}
cambi = 0
for n in SFASATI:
    e = estratti.get(n)
    if not e:
        print('#cap%02d: non estratto, lasciato com\'era' % n)
        continue
    riga = c.execute('select pov, data_narrativa from capitoli where id=?', (n,)).fetchone()
    for campo, letto in (('pov', e.get('pov')), ('data_narrativa', e.get('data_narrativa'))):
        vecchio = (riga[campo] or '').strip()
        nuovo = (letto or '').strip()
        if not nuovo or nuovo == '?' or nuovo.lower() == vecchio.lower():
            continue
        # Le date lette nel testo sono spesso piu' precise ("Dicembre 2023"
        # contro "Novembre 2023"): si tiene la piu' precisa solo se il
        # database non ne aveva una, altrimenti si segnala e basta.
        if campo == 'data_narrativa' and vecchio:
            print('#cap%02d data: db=%r testo=%r  -> DA DECIDERE, non tocco' % (n, vecchio[:20], nuovo[:20]))
            continue
        c.execute('insert into canone_correzioni (tabella,riga,campo,prima,dopo,fonte,quando) '
                  "values ('capitoli',?,?,?,?,'testo del capitolo',datetime('now'))",
                  (n, campo, vecchio, nuovo))
        c.execute('update capitoli set %s=? where id=?' % campo, (nuovo, n))
        cambi += 1
        print('#cap%02d %s: %r -> %r' % (n, campo, vecchio[:16], nuovo[:16]))

c.commit()
print('#campi corretti: %d' % cambi)
