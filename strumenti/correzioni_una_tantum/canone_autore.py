# -*- coding: utf-8 -*-
"""Canone dettato dall'autore, scritto nei campi che lo riguardano.

Ogni voce qui dentro viene da una decisione dell'autore, non da una deduzione
sul testo. Il testo puo' sbagliare - e in un caso sbaglia: nei capitoli 3 e 4
compare un "Ispettore Chen" che nel canone non esiste.

Prima di scrivere si salva com'era: se una di queste correzioni e' stata
capita male, si torna indietro senza indovinare.
"""
import json
import sqlite3
import sys

DB = '/home/pos/progetti/prima-vivi-poi-spieghi/roman.db'
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

c.executescript("""
CREATE TABLE IF NOT EXISTS canone_correzioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabella TEXT, riga INTEGER, campo TEXT,
    prima TEXT, dopo TEXT, fonte TEXT, quando TEXT
);
""")


def correggi(tabella, riga, campo, nuovo, fonte):
    vecchio = c.execute('select %s from %s where id=?' % (campo, tabella), (riga,)).fetchone()[0]
    if (vecchio or '') == nuovo:
        return False
    c.execute('insert into canone_correzioni (tabella,riga,campo,prima,dopo,fonte,quando) '
              "values (?,?,?,?,?,?,datetime('now'))", (tabella, riga, campo, vecchio, nuovo, fonte))
    c.execute('update %s set %s=? where id=?' % (tabella, campo), (nuovo, riga))
    print('#%s[%d].%s aggiornato' % (tabella, riga, campo))
    return True


# ── Michael ───────────────────────────────────────────────────────────────
MICHAEL_BG = (
    "Nel 1987 e' in Cina per conto della CIA, di stanza vicino a un "
    "osservatorio astronomico: il suo incarico e' sorvegliare i progressi "
    "spaziali cinesi. E' li' che incontra Lin bambino e lo porta via. "
    "Piu' tardi ex-intelligence; costruisce Arkana dall'ONU. Cardiopatico."
)
correggi('personaggi', 2, 'background', MICHAEL_BG, 'autore')

MICHAEL_NOTE = (
    "ATTENZIONE ai capitoli 3 e 4: il testo attuale attribuisce il "
    "salvataggio di Lin a un 'Ispettore Chen', personaggio che NON esiste nel "
    "canone. Quei capitoli vanno rigenerati con Michael al suo posto, nel "
    "ruolo di agente CIA presso l'osservatorio. "
    "Da chiarire con l'autore: eta_iniziale=74 non puo' riferirsi al 1987 "
    "(sarebbe nato nel 1913); verosimilmente e' l'eta' nel presente narrativo."
)
correggi('personaggi', 2, 'note', MICHAEL_NOTE, 'analisi + autore')

c.commit()
print('#correzioni registrate:', c.execute('select count(*) from canone_correzioni').fetchone()[0])
