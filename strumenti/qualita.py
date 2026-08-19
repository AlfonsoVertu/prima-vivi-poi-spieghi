# -*- coding: utf-8 -*-
"""Il metro con cui si accetta o si rifiuta una scena generata.

PERCHE' ESISTE. Contare le parole non basta e inganna: la prima generazione a
scene ha reso il 176% dell'obiettivo e sembrava un successo, ma erano 1741
frasi da sei parole con "artem guarda" ripetuto 340 volte. Un capitolo da
tremila parole moltiplicato per ripetizione.

DA DOVE VENGONO LE SOGLIE. Non le ho scelte io: le ho misurate sul romanzo.
Il capitolo 1, che il canone considera completo, sta a 21,8 parole per frase e
al 4% di inizi ripetuti. Quello e' il suono di questo libro.

Le due prove fatte finora, per capire cosa misura davvero questo metro:
  - senza freni:        6,1 parole/frase, 82% ripetuti  -> macchina bloccata
  - con freni e istruzione: 40,0 parole/frase, 14% ripetuti -> gonfio, letterario
Nessuna delle due e' il libro. Il bersaglio sta in mezzo.
"""
import re

# Misurato su cap01, che il canone da' per completo.
RIFERIMENTO = {'parole_per_frase': 21.8, 'inizi_ripetuti': 0.04}

# Fuori da questa forbice non e' prosa di questo romanzo: sotto e' balbuzie,
# sopra e' periodare letterario che qui stona.
MIN_PAROLE_FRASE = 12.0
MAX_PAROLE_FRASE = 30.0
MAX_INIZI_RIPETUTI = 0.20

# Parole che questo libro non usa. "Egli" e' comparso al primo tentativo con
# le penalita' attive: il modello, spinto ad allungare, scivola nel registro
# scolastico.
PAROLE_FUORI_REGISTRO = [
    r'\begli\b', r'\bessi\b', r'\bcolui\b', r'\bcoloro che\b',
    r'\bsiffatt', r'\bcotest', r'\borbene\b', r'\bnondimeno\b',
]


def misura(testo):
    frasi = [f.strip() for f in re.split(r'(?<=[.!?])\s+', testo) if len(f.strip()) > 3]
    parole = len(testo.split())
    if not frasi:
        return None
    inizi = {}
    for f in frasi:
        k = ' '.join(f.split()[:2]).lower()
        inizi[k] = inizi.get(k, 0) + 1
    ripetuti = sum(v for v in inizi.values() if v > 3)
    fuori = []
    for p in PAROLE_FUORI_REGISTRO:
        n = len(re.findall(p, testo, re.I))
        if n:
            fuori.append('%s x%d' % (p.strip('\\b'), n))
    return {
        'parole': parole,
        'frasi': len(frasi),
        'parole_per_frase': parole / len(frasi),
        'inizi_ripetuti': ripetuti / len(frasi),
        'inizi_frequenti': sorted(inizi.items(), key=lambda x: -x[1])[:3],
        'fuori_registro': fuori,
    }


def giudica(testo, parole_attese=None):
    """Restituisce (accettata, motivi). Nessun motivo = si tiene."""
    m = misura(testo)
    if not m:
        return False, ['testo vuoto']
    motivi = []
    if m['parole_per_frase'] < MIN_PAROLE_FRASE:
        motivi.append('frasi troppo corte (%.1f parole, minimo %.0f): e il sintomo '
                      'della ripetizione a raffica'
                      % (m['parole_per_frase'], MIN_PAROLE_FRASE))
    if m['parole_per_frase'] > MAX_PAROLE_FRASE:
        motivi.append('frasi troppo lunghe (%.1f parole, massimo %.0f): sta '
                      'periodando invece di raccontare'
                      % (m['parole_per_frase'], MAX_PAROLE_FRASE))
    if m['inizi_ripetuti'] > MAX_INIZI_RIPETUTI:
        motivi.append('inizi ripetuti al %.0f%% (massimo %.0f%%): %s'
                      % (100 * m['inizi_ripetuti'], 100 * MAX_INIZI_RIPETUTI,
                         ', '.join('"%s" x%d' % (k, v) for k, v in m['inizi_frequenti'])))
    # Una parola arcaica isolata in quattromila parole e' una svista da
    # correggere a mano, non un capitolo da rifare. Si boccia solo quando la
    # densita' dice che il modello (o chi ha scritto) e' scivolato di registro
    # per tutto il testo. Soglia: piu' di una ogni duemila parole.
    n_arcaismi = sum(int(x.split('x')[-1]) for x in m['fuori_registro'])
    if n_arcaismi and n_arcaismi > max(1, m['parole'] / 2000):
        motivi.append('registro sbagliato, %d occorrenze in %d parole: %s'
                      % (n_arcaismi, m['parole'], ', '.join(m['fuori_registro'])))
    elif m['fuori_registro']:
        m['da_correggere_a_mano'] = m['fuori_registro']
    if parole_attese and m['parole'] < parole_attese * 0.5:
        motivi.append('troppo corta: %d parole su %d attese' % (m['parole'], parole_attese))
    return (not motivi), motivi


if __name__ == '__main__':
    import sys
    for f in sys.argv[1:]:
        t = open(f, encoding='utf-8', errors='replace').read()
        ok, motivi = giudica(t)
        m = misura(t)
        print('%-42s %s | %.1f parole/frase | %.0f%% ripetuti'
              % (f.split('/')[-1], 'ACCETTATA' if ok else 'RIFIUTATA',
                 m['parole_per_frase'], 100 * m['inizi_ripetuti']))
        for x in motivi:
            print('    - %s' % x)
