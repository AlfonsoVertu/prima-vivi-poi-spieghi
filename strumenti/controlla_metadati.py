# -*- coding: utf-8 -*-
"""Trova i metadati che si contraddicono, prima che qualcuno ci scriva sopra.

PERCHE'. Il capitolo 48 aveva punto di vista "Liah" e luogo "Deserto di
Giudea", mentre la sua chiusa diceva "nel silenzio della cella NEDA capisce" e
il canone lo mette nel blocco 45-54, quello di Neda in carcere. Se non me ne
fossi accorto per caso, avrei fatto scrivere un capitolo su Liah nel deserto
al posto di Neda in cella - con tutto il resto del libro che dice il
contrario.

Quella contraddizione era verificabile a macchina: bastava confrontare i campi
fra loro. Questo lo fa per tutti e 66, invece di sperare che qualcuno guardi.

NON CORREGGE NIENTE. Segnala e basta: decidere quale campo abbia ragione
richiede di sapere cosa dice il romanzo, e questo e' un lavoro da persona.
"""
import re
import sqlite3
import sys

DB = '/home/pos/progetti/prima-vivi-poi-spieghi/roman.db'

# I blocchi che CANONE_DEFINITIVO.md assegna esplicitamente: "Capitoli 1-10:
# Lin", "Capitoli 45-54: Neda + carcere + fuga con Andriy", eccetera.
BLOCCHI = [
    (1, 10, ['Lin', 'Michael'], 'Lin: Cina, fuga, Europa/USA'),
    (11, 18, ['Lin', 'Artem', 'Sergej'], 'Donbass, morte di Lin, Sergej cresce Artem'),
    (19, 25, ['Artem', 'Michael'], 'Artem USA, NATO/ONU'),
    (26, 33, ['Omar', 'Liah'], 'Omar e Liah'),
    (34, 39, ['Yusuf', 'Eitan', 'Vash'], 'Yusuf ed Eitan, campo del Sinai'),
    (40, 44, ['Andriy'], 'Andriy, Kyiv e prigionia'),
    (45, 54, ['Neda', 'Andriy'], 'Neda, carcere di Teheran, fuga'),
    (55, 66, ['Artem', 'Yusuf', 'Vash', 'Neda', 'Omar', 'Liah', 'Ezra', 'Eitan'],
     'convergenza, Sinai, epilogo'),
]


def blocco_di(n):
    for a, b, chi, nome in BLOCCHI:
        if a <= n <= b:
            return chi, nome, '%d-%d' % (a, b)
    return None, None, None


def anno(testo):
    m = re.findall(r'(19|20)\d{2}', testo or '')
    a = re.findall(r'\b((?:19|20)\d{2})\b', testo or '')
    return [int(x) for x in a]


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    righe = [dict(r) for r in c.execute('select * from capitoli order by id')]
    nomi = [r['nome'] for r in c.execute('select nome from personaggi')]

    problemi = []
    for r in righe:
        n = r['id']
        attesi, nome_blocco, estremi = blocco_di(n)
        pov = (r.get('pov') or '').strip()
        segnala = []

        # 1. Il punto di vista appartiene al blocco?
        if attesi and pov:
            primo = re.split(r'[/,]', pov)[0].strip()
            if primo and primo not in attesi and primo.lower() not in ('tutti', 'corale'):
                segnala.append('POV "%s" fuori dal blocco %s (%s)' % (primo, estremi, nome_blocco))

        # 2. La chiusa nomina qualcuno che non e' il punto di vista?
        hook = r.get('hook_finale') or ''
        citati = [x for x in nomi if re.search(r'\b%s\b' % re.escape(x), hook)]
        if citati and pov and not any(x in pov for x in citati):
            segnala.append('la chiusa parla di %s ma il POV e %s' % (', '.join(citati), pov))

        # 3. La data va indietro rispetto al capitolo precedente dello stesso
        #    blocco? Un salto all'indietro puo' essere un flashback voluto, ma
        #    va saputo, non subito.
        if n > 1:
            prec = righe[n - 2]
            if blocco_di(n - 1)[2] == estremi:
                a1, a2 = anno(prec.get('data_narrativa')), anno(r.get('data_narrativa'))
                if a1 and a2 and max(a2) < min(a1):
                    segnala.append('data %r va indietro rispetto a cap%02d (%r)'
                                   % (r.get('data_narrativa'), n - 1, prec.get('data_narrativa')))

        # 4. Il luogo nomina un posto di un altro blocco?
        luogo = (r.get('luogo') or '').lower()
        for a, b, chi, nm in BLOCCHI:
            if (a, b) == (int(estremi.split('-')[0]), int(estremi.split('-')[1])):
                continue
        estranei = []
        for posto, blocco_posto in (('teheran', '45-54'), ('evin', '45-54'),
                                    ('kyiv', '40-44'), ('donbass', '11-18'),
                                    ('gaza', '34-39'), ('sinai', '34-39'),
                                    ('cina', '1-10')):
            if posto in luogo and estremi not in (blocco_posto, '55-66'):
                estranei.append('%s (tipico del blocco %s)' % (posto, blocco_posto))
        if estranei:
            segnala.append('luogo %r contiene: %s' % ((r.get('luogo') or '')[:40], '; '.join(estranei)))

        if segnala:
            problemi.append((n, r.get('titolo'), segnala))

    print('#capitoli con metadati sospetti: %d su %d' % (len(problemi), len(righe)))
    for n, tit, s in problemi:
        print('#cap%02d %-28s' % (n, (tit or '')[:28]))
        for x in s:
            print('#        - %s' % x)


if __name__ == '__main__':
    main()
