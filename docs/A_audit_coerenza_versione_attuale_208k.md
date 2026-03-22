# Report A — audit di coerenza versione attuale (208k)

## Sintesi

- File sorgente: **`prima-vivi-poi-spieghi_testi_e_metadati-208000-parole.zip`**
- Capitoli analizzati: **66**
- Parole dichiarate negli header: **208.768**
- Parole stimate sul corpo narrativo pulito: **208.334**
- Media parole per capitolo: **3157**
- Capitoli con **slittamento header→corpo** (inner header diverso dall'header esterno): **21**
- Capitoli con **header interno duplicato ma non slittato**: **2**
- Capitoli con **drift di contenuto senza inner header**: **6**
- Capitoli con **contenuto mancante/placeholder**: **1**
- Distribuzione priorità: **Alta 29 / Media 25 / Bassa 12**

## Quadro generale

Questa versione è molto più ampia e più vicina all'architettura del romanzo, ma soffre ancora di due problemi sistemici distinti:

1. **packaging drift**: il file e l'header esterno dichiarano un capitolo, ma il corpo contiene un altro capitolo già impaginato;
2. **drift di contenuto**: il capitolo non ha un inner header diverso, ma la scena effettiva apre su personaggio/luogo/tempo incompatibili con lo slot dichiarato.

I blocchi più stabili sono **01–24**, **46–54**, **58**, **64–66**. I blocchi più critici sono **25–45**, **50**, **55–57**, **60–63**.

## Distribuzione parole

- <1200 parole: **16**
- 1200–1999 parole: **3**
- 2000–2999 parole: **5**
- 3000–3999 parole: **20**
- 4000+ parole: **22**

Capitoli più corti: 63 Disarmo (41), 62 Tradimento (1005), 56 Insediamento (1008), 52 Sotto il pavimento (1015), 60 La mail (1021), 55 Rete (1025), 54 Io non ti conosco (1026), 53 Correre (1027)

Capitoli più lunghi: 02 Notte (9002), 23 College (7643), 01 Cortile (5998), 21 Doppio allenamento (5505), 61 Foto (5316), 50 Numero (4675), 07 Uniforme (4388), 26 FromLin (4176)

## Lessico contaminato / registro tecnico fuori voce

Capitoli con densità alta di lessico tecnico-astratto o fuori registro: 02 Notte (8), 04 Frontiera (6), 24 Stage ONU (11), 25 Assistente (8), 26 FromLin (7), 27 Soglia (6), 35 Genitori non tornano (7), 40 Prima vivi (11), 41 Server room (9), 42 Backup (10), 43 Promessa (8), 44 Buco nero (6), 50 Numero (6), 61 Foto (10).
Le ricorrenze più vistose sono: **database, protocollo, asettico, algoritmo, inerzia, geologica, kevlar, calibro**. In alcuni capitoli funzionano come colore di POV; in altri sostituiscono la voce umana e abbassano l'aderenza emotiva.

## Audit capitolo per capitolo

| Cap | Header corrente | Corpo effettivo | Stato | Priorità | Nota operativa |
|---|---|---|---|---|---|
| 01 | Cortile / Lin / Cina, villaggio rurale vicino a centro spaziale / 1987 | Cortile | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 02 | Notte / Lin / Cina, perimetro villaggio, strada di fuga notturna / 1987 | Notte | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 03 | Sedile dietro / Michael / Europa, auto in transito / 1987 | Sedile dietro | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 04 | Frontiera / Michael / Europa, posto di frontiera / 1987 | Frontiera | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 05 | Pane e lingua / Lin / Europa / primi anni USA / 1990-1992 | Pane e lingua | metadati da rifinire | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 06 | Scuola / Lin / Europa, scuola pubblica / 1996 | Scuola | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 07 | Uniforme / Lin / Europa / USA, centro di addestramento / 2000-2003 | Uniforme | metadati da rifinire | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 08 | Moglie / Lin / USA, Arlington, bar e quartiere residenziale / Primavera 2003 | Moglie | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 09 | Figli / Lin / USA, casa di Lin ed Elena nel Maryland / 2011-2013 | Figli | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 10 | Partenza / Lin / USA, casa; poi Ucraina orientale / Giugno 2014 | Partenza | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 11 | Casa in campagna / Sergej / Donbass, campagna rurale e casa civile / Giugno 2014 | Casa in campagna | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 12 | Gamba schiacciata / Artem / Donbass, interno casa colpita, macerie / Giugno 2014 | Gamba schiacciata | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 13 | Passaggio di mano / Sergej / Donbass, macerie casa, cortile, strada fangosa / Giugno 2014 | Passaggio di mano | allineato | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 14 | Flusso / Artem / Donbass / Russia, veicolo e rifugi di transito / 2014-2015 | Flusso | metadati da rifinire | Bassa | Allineato o con soli ritocchi di metadati/stile. |
| 15 | Addestramento / Sergej / Russia, alloggio militare e palestra improvvisata / 2015 | Addestramento | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 16 | YouTube / Artem / Russia, stanza di Artem, computer condiviso / 2015 | YouTube | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 17 | Femminucce / Sergej / Russia, palestra e corridoio alloggio / 2015 | Femminucce | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 18 | Lettera di Lin / Sergej / Russia, ufficio di Sergej, alloggio militare / 2015 | Lettera di Lin | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 19 | Via / Artem / Russia / Europa / USA, aeroporto e viaggio / 2016 | Via | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 20 | Casa pulita / Artem / USA, casa della famiglia di Lin, Maryland / 2016 | Casa pulita | allineato | Media | Allineato o con soli ritocchi di metadati/stile. |
| 21 | Doppio allenamento / Artem / USA, palestra e spazi esterni, Maryland / 2017 | Doppio allenamento | allineato | Media | Allineato o con soli ritocchi di metadati/stile. |
| 22 | Liceo / Artem / USA, liceo di Bethesda, Maryland / 2019 | Liceo | allineato | Media | Allineato o con soli ritocchi di metadati/stile. |
| 23 | College / Artem / USA, campus universitario / 2021-2023 | College | metadati da rifinire | Media | Allineato o con soli ritocchi di metadati/stile. |
| 24 | Stage ONU / Artem / Ginevra, sede ONU e corridoi istituzionali / 2024 | Stage ONU / Artem / Ginevra, sede ONU e corridoi istituzionali / 2024 | header interno duplicato | Media | Doppio header uguale nel corpo: non è slittato, ma va pulito il packaging. |
| 25 | Assistente / Artem / New York / Ginevra, uffici ONU / 2024-2025 | Assistente / Michael / New York / Ginevra, uffici ONU / 2024-2025 | slittamento header→corpo | Alta | Header esterno aggiornato su Artem, ma il corpo resta su Michael; correggere POV o spostare il testo. |
| 26 | FromLin / Artem / Online / New York, casella ONU / 2025 | Soglia / Omar / Kibbutz Kfar Aza, Israele meridionale / 7 ottobre 2023, ore 7:40 circa | slittamento header→corpo | Alta | File/titolo attuale 'FromLin', ma nel corpo compare l'header completo di 'Soglia' con Omar al 7 ottobre. |
| 27 | Soglia / Omar / Israele, kibbutz attaccato, casa civile / 7 ottobre 2023 | No / Omar / Israele / 7 ottobre 2023 | slittamento header→corpo | Alta | Header 'Soglia', corpo già slittato sul capitolo 'No' (acqua finita, fase successiva della fuga). |
| 28 | No / Omar / Israele, kibbutz, cortile e via di fuga / 7 ottobre 2023 | Acqua / Omar / Margini del kibbutz, strada sterrata, rifugio provvisorio, tratto verso il deserto / 7 ottobre 2023, pomeriggio-sera | slittamento header→corpo | Alta | Header 'No', corpo contiene 'Acqua': sequenza 27–30 ancora disallineata a catena. |
| 29 | Acqua / Omar / Cisgiordania, strade e rifugio provvisorio / Ottobre 2023 | Notte in due / Liah / Rifugio improvvisato (capanno agrumi) / Notte fra 7 e 8 ottobre 2023 | slittamento header→corpo | Alta | Header 'Acqua', ma il corpo è 'Notte in due' con Liah; titolo/POV/luogo slittati. |
| 30 | Notte in due / Omar/Liah / Cisgiordania, rifugio notturno improvvisato / Ottobre 2023 | Chiave / Omar/Liah / Cisgiordania / 2023 | slittamento header→corpo | Alta | Header 'Notte in due', corpo con 'Chiave'; il capitolo atteso è finito nel file successivo. |
| 31 | Chiave / Liah / Cisgiordania, insediamento e casa di Liah / Ottobre 2023 | Valle del Giordano / Omar / Strade secondarie, margini dell'insediamento, percorsi verso la Valle del Giordano / 8 ottobre 2023 | slittamento header→corpo | Alta | Header 'Chiave', corpo con 'Valle del Giordano'; Liah/Omar slittati di uno slot. |
| 32 | Valle del Giordano / Omar/Liah / Valle del Giordano, Cisgiordania / 2023 | Coloni / Liah / Insediamento radicalizzato, strada interna, spazio comune, perimetro domestico / 2024 | slittamento header→corpo | Alta | Header 'Valle del Giordano', corpo con 'Coloni'; lo slittamento continua. |
| 33 | Coloni / Liah / Valle del Giordano, insediamento radicalizzato / 2023-2024 | Sotto voce / Omar / Cisgiordania, la stanza segreta nell'insediamento / 2024 | slittamento header→corpo | Alta | Header 'Coloni', corpo con 'Sotto voce'; data interna 2024, non 2023-2024 generico. |
| 34 | Sotto voce / Omar / Valle del Giordano, casa di Liah, cucina notturna / 2023-2025 | Genitori non tornano / Yusuf / Gaza / novembre 2023 | slittamento header→corpo | Alta | Header 'Sotto voce', corpo con 'Genitori non tornano'; passaggio Omar→Yusuf ancora in slot sbagliato. |
| 35 | Genitori non tornano / Yusuf / Gaza, quartiere residenziale sotto attacco / Novembre 2023 | Disertore / Eitan / Gaza, quartiere nord, zona di operazioni attiva / novembre 2023 | slittamento header→corpo | Alta | Header 'Genitori non tornano', corpo con 'Disertore' in prima persona Eitan. |
| 36 | Disertore / Eitan / Gaza / Rafah, strade e rovine urbane / Novembre 2023 | Passare / Yusuf / Gaza / Sinai / Dicembre 2023 | slittamento header→corpo | Alta | Header 'Disertore', corpo con 'Passare' (Yusuf, checkpoint Egitto/Sinai). |
| 37 | Passare / Yusuf / Egitto / Sinai, corridoio di fuga / 2023-2024 | Passare | metadati da rifinire | Media | Corpo coerente con Yusuf/passaggio; da rifinire geografia e compressione del transito. |
| 38 | Tre anni / Vash / Cisgiordania, insediamento della famiglia di Ezra / 2023-2025 | Addestramento sotto tenda / Eitan / Sinai, campo / 2024-2025 | slittamento header→corpo | Alta | Header 'Tre anni', corpo con 'Addestramento sotto tenda' POV Eitan/Sinai; Vash non in scena come da slot. |
| 39 | Addestramento sotto tenda / Vash / Cisgiordania / soglia Sinai, 3 marzo 2026 / 3 marzo 2026 | Prima vivi / Yusuf / Sinai, campo / 2026 | slittamento header→corpo | Alta | Header 'Addestramento sotto tenda', corpo con 'Prima vivi' POV Yusuf/Sinai. |
| 40 | Prima vivi / Lin / Flashback: Cina 1987 / Donbass 2014 / Flashback 2014 | Andriy / Kyiv / febbraio 2022 | drift contenuto | Alta | Header Lin/flashback 2014, ma l'incipit è Andriy a Kyiv nel febbraio 2022: contenuto nel blocco sbagliato. |
| 41 | Server room / Andriy / Kyiv, data center bancario / Febbraio 2022 | Backup / Andriy / Kyiv, metropolitana / febbraio 2022 | slittamento header→corpo | Alta | Header 'Server room', corpo con header interno 'Backup' in metropolitana Kyiv. |
| 42 | Backup / Andriy / Kyiv, bunker tecnico e corridoi / Primavera 2022 | Promessa / Andriy / Cella di detenzione, oltre il confine / marzo 2022 | slittamento header→corpo | Alta | Header 'Backup', corpo con 'Promessa' in cella oltre confine. |
| 43 | Promessa / Andriy / Kyiv periferia, strade di fuga verso est / 2022 | Buco nero / Andriy / Struttura di massima sicurezza, Rostov sul Don / aprile 2022 | slittamento header→corpo | Alta | Header 'Promessa', corpo con 'Buco nero' a Rostov. |
| 44 | Buco nero / Andriy / Prigione di transito / trasferimento a Teheran / 2022-2025 | Numero / Andriy / In volo / Teheran / 2022 | slittamento header→corpo | Alta | Header 'Buco nero', corpo con 'Numero' durante il trasferimento verso Teheran. |
| 45 | Neda live / Neda / Teheran, appartamento, live streaming / Gennaio 2026 | La stanza / Neda / Prigione di Evin, Teheran / 2023 | slittamento header→corpo | Alta | Header 'Neda live', corpo con 'La stanza' in prigione di Evin, 2023. |
| 46 | Messaggio FromLin / Neda / Teheran, appartamento, finestra sul tetto / Gennaio 2026 | Neda | metadati da rifinire | Media | Corpo coerente; serve solo espansione e rifinitura di timeline/pressione. |
| 47 | Arresto / Neda / Teheran, scala del palazzo, strada, furgone / Gennaio 2026 | Neda | metadati da rifinire | Media | Corpo coerente; espansione breve e maggiore continuità con 46-48. |
| 48 | Cella / Neda / Teheran, carcere segreto, cella singola / Gennaio-Febbraio 2026 | Cella | metadati da rifinire | Media | Corpo coerente; rafforzare routine, paura e scansione temporale. |
| 49 | Mattone / Neda / Teheran, carcere, cella e parete danneggiata / Febbraio 2026 | Mattone | metadati da rifinire | Media | Corpo coerente; alzare concretezza e alleggerire il lessico astratto. |
| 50 | Numero / Andriy / Teheran, carcere segreto, settore maschile / Febbraio 2026 | Risveglio / Michael / Neda (Alternato) / Ospedale segreto (Israele) / Prigione di Evin (Teheran) / 2023 | slittamento header→corpo | Alta | Header 'Numero', corpo con 'Risveglio' alternato Michael/Neda: non è il capitolo atteso. |
| 51 | Porta / Neda / Teheran, carcere, corridoio e porta di servizio / Fine febbraio 2026 | Porta | metadati da rifinire | Media | Corpo coerente; aumentare immediatezza spaziale e rischio. |
| 52 | Sotto il pavimento / Andriy / Teheran, carcere in collasso, intercapedini / 3 marzo 2026 | Sotto il pavimento | metadati da rifinire | Media | Corpo coerente; più chiarezza logistica nella fuga. |
| 53 | Correre / Neda/Andriy / Teheran ovest / Giordania, fuga / 3-6 marzo 2026 | Neda | metadati da rifinire | Media | Corpo coerente; raccordare meglio Teheran→Giordania. |
| 54 | Io non ti conosco / Andriy / Giordania / Valle del Giordano, strade secondarie / 6-18 marzo 2026 | Io non ti conosco | metadati divergenti | Media | Corpo sostanzialmente coerente, ma luogo e durata vanno stretti per evitare deriva. |
| 55 | Rete / Artem / Valle del Giordano / ONU remoto / Marzo 2026 | Artem arriva nel Sinai con Neda e Andriy | drift contenuto | Alta | Header 'Rete', ma il corpo è l'arrivo operativo di Artem/Neda/Andriy nel Sinai. |
| 56 | Insediamento / Omar/Liah / Cisgiordania, insediamento, casa di Liah / 2-3 marzo 2026 | Artem prepara l'estrazione nel Sinai | drift contenuto | Alta | Header 'Insediamento' in Cisgiordania, ma il corpo è già nel Sinai con Artem che prepara l'estrazione. |
| 57 | Degenerazione / Liah / Cisgiordania, insediamento sotto pressione coloni / 3 marzo 2026 | Vash/Artem preparano l'operazione vicino al porto | drift contenuto | Alta | Header 'Degenerazione' di Liah, ma il corpo segue Vash/Artem in prep tattica vicino al porto. |
| 58 | Fuga innescata / Vash / Cisgiordania cortile / strada / soglia Sinai / 4 marzo 2026 | Vash | metadati da rifinire | Alta | Questo è uno dei riallineamenti riusciti: POV Vash corretto. Restano da rifinire densità e raccordo con 55–57. |
| 59 | Punto d'acqua / Tutti / Sinai, campo di Yusuf ed Eitan / 4 marzo 2026 | Punto d'acqua | allineato | Media | Corpo quasi coerente; raccordare arrivo al campo con i capitoli immediatamente precedenti. |
| 60 | La mail / Artem/Yusuf / ONU New York / Sinai, campo / 4 marzo 2026 | incontro operativo notturno al Molo 4 | drift contenuto | Alta | Header 'La mail', ma il corpo mostra incontro operativo notturno al Molo 4; la mail non è la scena dominante. |
| 61 | Foto / Artem / Sinai, campo e perimetro / 4 marzo 2026 | Il Crollo / Andriy / Neda / Liah / Eitan / Siberia (Russia) / Teheran (Iran) / Tel Aviv (Israele) / 2024 | slittamento header→corpo | Alta | Header 'Foto', corpo con altro capitolo ('Il Crollo') multi-POV e data 2024. |
| 62 | Tradimento / Artem / Sinai, campo sotto assalto / 4 marzo 2026 | Neda e Andriy su traversata marina | drift contenuto | Alta | Header 'Tradimento' nel Sinai, ma il corpo apre su traversata marina con Neda/Andriy, non sul tradimento di Ezra. |
| 63 | Disarmo / Artem / Sinai, campohub operativo, dune / 4 marzo 2026 | Disarmo / Artem / Sinai, campohub operativo, dune / 4 marzo 2026 | placeholder | Alta | Capitolo placeholder: contenuto mancante dichiarato esplicitamente. |
| 64 | Dopo / Artem / Sinai, campo dopo la battaglia / 5 marzo 2026 | Dopo | metadati da rifinire | Media | Coerente come aftermath; va ampliato per dare peso emotivo e logistico. |
| 65 | Primo corridoio / Artem / Internazionale, corridoi umanitari in costruzione / 2027 | Artem | metadati da rifinire | Media | Coerente come epilogo operativo in prima persona Artem; espandere impatto legale e rete. |
| 66 | Quello che resta / Artem / Tunisia/Libia, sito di Anakara; globale / 2028-2050 | Quello che resta | metadati da rifinire | Media | Coerente come epilogo 2050; da ampliare e raccordare ad Anakara Arkana. |

## Nodi sistemici da correggere prima di qualsiasi espansione

### 1) Catena di slittamento 25→45

Dal **25** in avanti il manoscritto contiene una vera catena di capitoli inseriti nel file sbagliato. Il pattern è semplice: il testo del capitolo successivo o di un blocco vicino è stato incollato nel contenitore del capitolo corrente, lasciando intatto l'header esterno aggiornato. Finché questa catena non viene rotta, ogni giudizio di ritmo o arco emotivo su quel blocco è parzialmente falsato.

### 2) Due blocchi orfani

- **cap40**: il contenuto appartiene chiaramente ad Andriy/Kyiv 2022, non a Lin/flashback 2014.
- **cap55–57 / 60 / 62**: i titoli del finale ci sono, ma le scene effettive sono già avanti o altrove nella sequenza operativa.

### 3) Placeholder nel climax

**cap63** è un buco reale nel finale. Va ricostruito prima delle rifiniture stilistiche, altrimenti il passaggio **Tradimento → Disarmo → Dopo** resta monco.
