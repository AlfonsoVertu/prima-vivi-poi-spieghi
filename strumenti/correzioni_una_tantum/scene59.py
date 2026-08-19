# -*- coding: utf-8 -*-
"""Le scene del capitolo 59, scritte a mano.

PERCHE' A MANO. Il modello scrive bene la prosa e male la struttura: gli si
chiede la scomposizione e restituisce cinque paragrafi che dicono la stessa
cosa. La struttura la decide chi ha letto tutto il libro; il modello la
riempie.

DA COSA SONO VINCOLATE. Non sono invenzioni: ogni scena e' costretta da fatti
gia' fissati altrove.
  - Dal capitolo 58: Ezra assedia il campo e TIENE LIAH.
  - Dal capitolo 64: il campo si salva, ma EITAN E' MORTO con una ferita al
    petto, e Artem ne trova il corpo. Quindi Eitan muore qui dentro.
  - Dal canone: "deviazione tattica dell'odio, scontro Artem vs Ezra".
  - Dal filo dell'aikido, aperto al capitolo 16: non si oppone forza alla
    forza, la si devia. Se Artem uccide Ezra, il filo non si chiude: si
    tradisce.
"""
import sqlite3

SCENE = """Scena 1 — Il campo, ultima luce. POV Artem, appena inserito con la task force.
Artem arriva e trova una posizione gia' persa sulla carta: Ezra tiene il lato
alto, il campo e' scoperto, e c'e' un ostaggio. Conta gli uomini e capisce che
non ci sono abbastanza minuti per una soluzione pulita. CAMBIA: smette di
cercare la soluzione pulita.

Scena 2 — Eitan sceglie. Il fuoco entra nel campo.
Eitan copre lo spostamento dei bambini verso la cisterna e resta esposto per
tenere aperta la linea. Prende un colpo al petto. Non c'e' una morte
cinematografica: si siede, chiede di Yusuf, e smette di rispondere. CAMBIA: il
campo si salva al prezzo dell'uomo che lo aveva fondato.

Scena 3 — Yusuf vede.
Yusuf, che Eitan aveva raccolto a Gaza dodici anni prima, capisce prima di
sapere. Vuole andare avanti, allo scoperto. Artem lo ferma con il corpo, non
con le parole. CAMBIA: Artem diventa per Yusuf quello che Lin era stato per
lui - qualcuno che si mette fisicamente fra te e la tua morte.

Scena 4 — Liah.
Ezra usa la sorella come schermo per farsi consegnare il campo. Artem non
tratta e non spara: lavora sulla distanza, sul terreno, sull'impazienza di
Ezra. Liah si sposta di un passo per conto suo, e quel passo apre lo spazio.
CAMBIA: Liah smette di essere un oggetto della trattativa.

Scena 5 — Artem contro Ezra. IL PUNTO DEL CAPITOLO.
Ezra attacca. Artem non oppone: entra nel movimento, lo devia, lo accompagna a
terra, gli toglie l'arma, lo immobilizza. E' l'aikido che a sedici anni
guardava su YouTube di nascosto mentre Sergej lo chiamava roba da femminucce.
Puo' ucciderlo e non lo fa. Non per bonta': perche' ucciderlo restituirebbe
alla catena esattamente cio' che la catena esiste per fermare. CAMBIA: l'odio
viene deviato invece che ricambiato, ed e' la tesi del romanzo in un gesto.

Scena 6 — Dopo, ma non ancora il lutto.
Il campo tace. Ezra e' vivo e legato, il che e' peggio per lui. Yusuf resta
accanto a Eitan senza toccarlo. Artem non dice niente a nessuno: conta i vivi.
CAMBIA: niente, ed e' il punto - la vittoria non consola.

NOTE PER CHI SCRIVE:
- Non nominare mai la parola "aikido" nella scena 5. Il gesto si descrive, non
  si etichetta: e' il modo in cui questo libro chiude i simboli (vedi il
  cucchiaio, capitolo 63).
- Ezra NON deve morire. E' una decisione, non una possibilita' aperta.
- Eitan muore nella scena 2, non piu' tardi: il capitolo 64 si apre con il suo
  corpo gia' freddo.
- Punto di vista fisso su Artem: non si sa cosa pensano gli altri, si vede
  cosa fanno."""

c = sqlite3.connect('/home/pos/progetti/prima-vivi-poi-spieghi/roman.db')
prima = c.execute('select scene_outline from capitoli where id=59').fetchone()[0]
c.execute('insert into canone_correzioni (tabella,riga,campo,prima,dopo,fonte,quando) '
          "values ('capitoli',59,'scene_outline',?,?,'scritte a mano su canone + fili',datetime('now'))",
          (prima, SCENE))
c.execute('update capitoli set scene_outline=? where id=59', (SCENE,))
c.commit()
print('#scene del cap59 sostituite: %d -> %d caratteri' % (len(prima or ''), len(SCENE)))
print('#le vecchie (punto d\'acqua) restano in canone_correzioni')
