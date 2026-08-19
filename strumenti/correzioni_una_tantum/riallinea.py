# -*- coding: utf-8 -*-
"""Riallinea i metadati dei capitoli al canone.

IL DIFETTO. Il database aveva perso alcuni titoli - "Acqua", il capitolo 28
del canone, non c'era affatto - e gli altri erano scivolati di una posizione a
riempire il buco. Risultato: per quattordici capitoli il database descriveva
il capitolo precedente. Sono esattamente i dati che si darebbero a un modello
per riscrivere un capitolo: con quelli, scriverebbe il capitolo giusto con il
punto di vista e la data di un altro.

CHI HA RAGIONE. Il canone, per decisione dell'autore. E i file dei capitoli
concordano con il canone: e' il database ad essersi scollato da tutti e due.

COSA TOCCA. Solo il titolo, che e' l'unico campo su cui il canone e' esplicito
capitolo per capitolo. Punto di vista, luogo e data restano come sono e
vengono confrontati a parte con quello che si legge nei testi: correggerli
adesso vorrebbe dire indovinare.
"""
import re
import sqlite3

D = '/home/pos/progetti/prima-vivi-poi-spieghi'
c = sqlite3.connect(D + '/roman.db')

t = open(D + '/CANONE_DEFINITIVO.md', encoding='utf-8', errors='replace').read()
canone = {int(m.group(1)): m.group(2).strip()
          for m in re.finditer(r'^(\d{1,2})\.\s+(.+?)\s+—\s+\d+\s+pagine', t, re.M)}

cambiati = 0
for n, titolo in sorted(canone.items()):
    prima = c.execute('select titolo from capitoli where id=?', (n,)).fetchone()
    if not prima:
        continue
    prima = (prima[0] or '').strip()
    if prima.lower() == titolo.lower():
        continue
    c.execute('insert into canone_correzioni (tabella,riga,campo,prima,dopo,fonte,quando) '
              "values ('capitoli',?,'titolo',?,?,'CANONE_DEFINITIVO.md',datetime('now'))",
              (n, prima, titolo))
    c.execute('update capitoli set titolo=? where id=?', (titolo, n))
    cambiati += 1
    print('#cap%02d  %-30s -> %s' % (n, prima[:30], titolo))

c.commit()
print('#titoli riallineati: %d' % cambiati)
print('#correzioni tracciate in tutto: %d' %
      c.execute('select count(*) from canone_correzioni').fetchone()[0])
