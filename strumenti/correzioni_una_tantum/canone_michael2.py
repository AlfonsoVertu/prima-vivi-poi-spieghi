# -*- coding: utf-8 -*-
"""Il 1987 di Michael, come lo detta l'autore, e il mandato per riscrivere
i capitoli 3 e 4.

Il punto drammatico non e' il salvataggio: e' il PREZZO. Michael e' sotto
copertura per un'operazione di sorveglianza; salvare Lin significa bruciarla,
perdere la posizione e diventare lui stesso un fuggitivo. Chi scrivera' quei
capitoli deve sapere questo, altrimenti scrive di nuovo un buon samaritano.
"""
import sqlite3

DB = '/home/pos/progetti/prima-vivi-poi-spieghi/roman.db'
c = sqlite3.connect(DB)


def correggi(tabella, riga, campo, nuovo, fonte):
    vecchio = c.execute('select %s from %s where id=?' % (campo, tabella), (riga,)).fetchone()[0]
    if (vecchio or '') == nuovo:
        return
    c.execute('insert into canone_correzioni (tabella,riga,campo,prima,dopo,fonte,quando) '
              "values (?,?,?,?,?,?,datetime('now'))", (tabella, riga, campo, vecchio, nuovo, fonte))
    c.execute('update %s set %s=? where id=?' % (tabella, campo), (nuovo, riga))
    print('#%s[%d].%s aggiornato' % (tabella, riga, campo))


MICHAEL_BG = (
    "Nel 1987 e' in Cina per conto della CIA, sotto copertura vicino a un "
    "osservatorio astronomico: sorveglia i progressi spaziali cinesi. "
    "Incontra Lin bambino e per salvarlo ROMPE LA COPERTURA - brucia "
    "l'operazione, perde la posizione e fugge portandoselo dietro. E' il "
    "prezzo che paga, non un gesto senza conseguenze. "
    "Piu' tardi ex-intelligence; costruisce Arkana dall'ONU. Cardiopatico."
)
correggi('personaggi', 2, 'background', MICHAEL_BG, 'autore')

# Il mandato per i due capitoli da rifare, scritto dove chi genera lo legge.
BRIEF = (
    "DA RIGENERARE. Il testo attuale mette al centro un 'Ispettore Chen' che "
    "nel canone NON ESISTE. Al suo posto c'e' Michael, agente CIA sotto "
    "copertura presso un osservatorio astronomico, in Cina nel 1987. "
    "Il nodo drammatico e' che salvare Lin gli costa la copertura: brucia "
    "l'operazione e diventa un fuggitivo con un bambino a carico. "
    "La tensione non e' 'ce la faranno a passare', e' 'quest'uomo ha appena "
    "distrutto la propria vita per un bambino che non conosce'."
)
for cap in (3, 4):
    vecchio = c.execute('select background from capitoli where id=?', (cap,)).fetchone()[0]
    nuovo = (BRIEF + "\n\n" + (vecchio or '')).strip()
    correggi('capitoli', cap, 'background', nuovo, 'autore + analisi')
    c.execute("update capitoli set stato='da_rigenerare' where id=?", (cap,))

c.commit()
print('#capitoli marcati da rigenerare:',
      [r[0] for r in c.execute("select id from capitoli where stato='da_rigenerare'")])
