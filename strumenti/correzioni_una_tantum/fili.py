# -*- coding: utf-8 -*-
"""I fili narrativi: cose piantate in un capitolo che devono tornare in un altro.

PERCHE' SERVONO. Un modello piccolo vede un capitolo alla volta. Se in un
capitolo si pianta qualcosa che deve tornare trenta capitoli dopo, quel
qualcosa si perde - ed e' esattamente quello che e' successo qui: l'aikido
compare nei capitoli 16-23, poi una volta nel 57, e nel capitolo che il canone
chiama "Aikido nel deserto" NON C'E'. L'arco e' stato piantato e mai raccolto.

Questa tabella tiene i fili in un posto solo, con i capitoli dove nascono e
quelli dove devono chiudersi, cosi' chi genera un capitolo sa cosa deve
raccogliere prima ancora di cominciare.
"""
import sqlite3

D = '/home/pos/progetti/prima-vivi-poi-spieghi'
c = sqlite3.connect(D + '/roman.db')

c.executescript("""
CREATE TABLE IF NOT EXISTS fili_narrativi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    principio TEXT,          -- cosa dice il filo, in una frase
    semina TEXT,             -- capitoli dove viene piantato
    raccolta TEXT,           -- capitoli dove deve tornare
    stato TEXT,              -- 'aperto' = piantato e non ancora raccolto
    riscontri TEXT,          -- citazioni dal testo, per non lavorare a memoria
    note TEXT
);
CREATE TABLE IF NOT EXISTS decisioni_autore (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    argomento TEXT, scelta TEXT, scartate TEXT, quando TEXT
);
""")

c.execute("""INSERT OR REPLACE INTO fili_narrativi
    (nome, principio, semina, raccolta, stato, riscontri, note) VALUES (?,?,?,?,?,?,?)""", (
    'aikido',
    "Non opporre forza alla forza: deviarla. E' il modo in cui Artem "
    "sopravvive a Sergej prima, e il modo in cui affronta Ezra alla fine.",
    '16, 17, 18, 19, 20, 21, 22, 23, 25',
    '59 (Aikido nel deserto - scontro Artem vs Ezra)',
    'aperto',
    'cap16: "usavo l\'aikido per *ricevere* meglio i suoi colpi. Quando mi '
    'spingeva, invece di opporre forza muscolare, la deviavo". '
    'cap17 (POV Sergej): "per quanto lo chiamassi con disprezzo \'roba da '
    'femminucce\' davanti a lui, una parte di me..."',
    "VERIFICATO: la parola aikido non compare in cap59. L'arco e' piantato in "
    "dieci capitoli e mai raccolto. Chi scrive il 59 deve chiuderlo: la "
    "violenza di Ezra va deviata, non restituita."))

c.execute("""INSERT INTO decisioni_autore (argomento, scelta, scartate, quando)
    VALUES (?,?,?,datetime('now'))""", (
    'Struttura del finale (capitoli 55-63)',
    'IL DUELLO, come da CANONE_DEFINITIVO.md: 58 attacco dei coloni, '
    '59 aikido nel deserto (Artem vs Ezra), 60 salvataggio ad Akaba, '
    '61 il debito e pagato, 62 prima vivi poi spieghi, 63 finale in Maryland. '
    'Motivo: chiude l\'arco dell\'aikido aperto al capitolo 16.',
    'IL RICATTO (come scritto nel testo: Ezra cattura Liah e chiede a Vash di '
    'consegnare Omar). TITOLI DEL DATABASE (Disarmo, Tradimento, Foto...).'))

c.commit()
print('#filo registrato: aikido, stato aperto')
print('#decisione registrata: finale = duello (canone)')
for r in c.execute('select nome, stato, raccolta from fili_narrativi'):
    print('#  filo %-10s %-8s -> da chiudere in %s' % (r[0], r[1], r[2]))
