# -*- coding: utf-8 -*-
"""Gli altri fili, con lo stato verificato nel testo e non a memoria."""
import sqlite3

c = sqlite3.connect('/home/pos/progetti/prima-vivi-poi-spieghi/roman.db')

FILI = [
    ('cucchiaio',
     "Il cucchiaio piegato che Artem stringe nella casa colpita del Donbass, "
     "quando Lin lo salva. E' l'oggetto del momento in cui la sua vita "
     "diventa il prolungamento di quella di un altro.",
     '11, 12, 13, 14-25 (ricorrente), 50',
     '63 (Finale, epilogo in Maryland)',
     'chiuso',
     'cap63: "Lo posa sul granito scuro. Il suono del metallo che tocca la '
     'pietra e nitido. Il cucchiaio resta li, un frammento di acciaio piegato '
     'in mezzo alla perfezione della cucina."',
     "VERIFICATO chiuso. Cinquantun capitoli fra la semina e la raccolta. "
     "E' il modello di come si chiude un filo in questo romanzo: senza "
     "spiegarlo, mettendo l'oggetto dove non c'entra piu' niente."),

    ('spilla del Comitato',
     "La spilla di ferro dei funzionari, scolpita a forma di stella polare, "
     "che nel villaggio significa il potere di decidere chi mangia. Per Lin "
     "bambino e' la cosa che brilla mentre lo puniscono.",
     '1',
     'MAI',
     'aperto',
     'cap01: "la spilla del Comitato brillava cattiva"; "immancabilmente '
     'scolpite ad iconica forma di stella polare, che si mettevano a brillare, '
     'minacciando me e chi le guardava"',
     "VERIFICATO: la parola 'spilla' compare in UN SOLO capitolo su 66, il "
     "primo. Simbolo introdotto con forza nella scena piu' dura del romanzo e "
     "mai piu' ripreso. Da decidere con l'autore: chiuderlo (dove?) o "
     "accettare che resti un dettaglio d'ambiente."),

    ('prima vivi poi spieghi',
     "La frase che da' il titolo al libro. Passa da Lin ad Artem e diventa un "
     "principio operativo: si sopravvive prima, si rende conto dopo.",
     '2, 10, 12, 13, 16, 18, 19, 20 e oltre (ricorrente in tutto il romanzo)',
     '62 (Prima vivi poi spieghi)',
     'da verificare',
     "Presente in decine di capitoli. CANONE_DEFINITIVO.md: Michael riconosce "
     "Artem solo quando pronuncia la frase.",
     "Il capitolo 62 porta il titolo della frase ma e' al 22% dell'obiettivo "
     "(1347 parole su 6000): la raccolta esiste come titolo, non ancora come "
     "scena."),
]

for f in FILI:
    c.execute("""INSERT OR REPLACE INTO fili_narrativi
        (nome,principio,semina,raccolta,stato,riscontri,note) VALUES (?,?,?,?,?,?,?)""", f)
c.commit()

print('#%-24s %-14s %s' % ('FILO', 'STATO', 'RACCOLTA'))
for r in c.execute('select nome,stato,raccolta from fili_narrativi order by stato, nome'):
    print('#%-24s %-14s %s' % (r[0], r[1], str(r[2])[:44]))
