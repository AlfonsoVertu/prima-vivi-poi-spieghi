# Cosa è stato corretto, e cosa resta

Nota di lavoro del 19-20 agosto 2026. Tutte le modifiche ai dati sono
tracciate nella tabella `canone_correzioni` del database, con il valore
precedente: nessuna è irreversibile.

## Il difetto principale: i metadati descrivevano il capitolo sbagliato

Il database e i file dei capitoli si erano scollati. Per quattordici capitoli
il database portava il titolo, il punto di vista e la data del capitolo
**precedente**: aveva perso alcuni titoli — «Acqua», il capitolo 28 del
canone, non c'era affatto — e gli altri erano scivolati a riempire il buco.

Conta più di quanto sembri, perché quei campi sono esattamente ciò che si
consegna a un modello per far riscrivere un capitolo. Con quelli sbagliati si
riscrive il capitolo giusto dalla testa della persona sbagliata.

`CANONE_DEFINITIVO.md` e i file dei capitoli concordavano fra loro: era il
database ad essersi scollato da tutti e due. Sono stati riallineati 26 titoli
e 7 punti di vista.

## Due capitoli che credevamo scritti e non lo erano

**cap48 «Cella»** aveva punto di vista «Liah» e luogo «Deserto di Giudea»,
mentre la sua stessa chiusa diceva «nel silenzio della cella Neda capisce» e
il canone lo mette nel blocco 45-54, quello di Neda in carcere. Il testo era
inoltre degenerato all'81%: frasi da oltre sessanta parole fatte di aggettivi
impilati, con lo stesso aggettivo ripetuto a otto parole di distanza. Uscita
di un modello inceppato, non prosa. Riscritto.

**cap51 «Porta»** contiene un capitolo su Sergej al fronte libanese, mentre il
canone assegna quello slot ad Andriy che in cella trova la via di fuga. Il
capitolo su Sergej non ha un posto nel canone. **Da decidere con l'autore**:
se tenerlo va collocato altrove, se no lo slot 51 va scritto da zero.

## Un personaggio che non esiste

Nei capitoli 3 e 4 il salvataggio di Lin è attribuito a un «Ispettore Chen»,
che nel canone non esiste: là c'è Michael, agente CIA sotto copertura presso
un centro di ricerca spaziale in Cina, che **rompe la copertura** per salvare
il bambino e fugge portandoselo dietro. Il nodo drammatico è il prezzo, non il
salvataggio. I due capitoli sono marcati `da_rigenerare` e il mandato è scritto
nel loro campo `background`.

Chen compare solo lì: due capitoli e due riassunti. Il resto del libro è pulito.

## Il canone non era leggibile dal programma

`CANONE_DEFINITIVO.md` fissa 66 capitoli, 800 pagine, 400.000 parole, e assegna
a ogni capitolo un obiettivo di pagine e una funzione narrativa. Stava in un
Markdown che nessuna parte del programma leggeva: ecco perché nessuno sapeva
che il romanzo è al **53%** del previsto.

Ora quei dati sono nel database, nei campi `parole_obiettivo` e
`funzione_narrativa`, e `CANONE_AGGIORNATO.md` si rigenera da lì.

## Il registro degli agenti non si accendeva mai

All'avvio l'applicazione chiamava solo `ensure_schema`, che crea le tabelle e
non ci mette dentro niente. Il popolamento esisteva ma era raggiungibile solo
da `POST /api/agents/bootstrap`, cioè da nessuno. Risultato:
`resolve_chat_model_from_registry` restituiva sempre `None` e tutto il registro
— ruoli, prompt, instradamento, catene di ripiego — restava inerte.

Corretto: gli agenti predefiniti si creano all'avvio. Quattro agenti, sette
prompt, sei endpoint.

## Come si scrive un capitolo, adesso

Il progetto aveva i due pezzi giusti e non li aveva mai uniti:
`compila_iterativo.py` costruisce un ottimo pacchetto di contesto ma si ferma a
stamparlo perché qualcuno lo copi a mano; `expand_chapters.py` chiama il
modello ma non gli passa niente del canone — e sovrascrive il file originale.
È così che nasce un Ispettore Chen: si chiede a un modello di allungare un
capitolo senza dirgli nulla del libro, e lui inventa un personaggio per
riempire lo spazio.

Gli strumenti nuovi stanno in `strumenti/`:

- **`qualita.py`** — il metro. Misura parole per frase e percentuale di inizi
  ripetuti, tarati sul capitolo 1 del romanzo (21,8 parole per frase, 4% di
  inizi ripetuti). Riconosce il capitolo buono e boccia la macchina inceppata.
- **`controlla_metadati.py`** — trova i campi che si contraddicono fra loro
  prima che qualcuno ci scriva sopra. Avrebbe preso il cap48 da solo.
- **`estrai_canone.py`** — legge i capitoli col modello locale ed estrae quello
  che il testo dice davvero, per confrontarlo con quello che il database crede.
- **`scrivi_scene.py`** — fa scrivere un capitolo una scena alla volta.
- **`rigenera_canone.py`** — rifà `CANONE_AGGIORNATO.md` dallo stato reale.

### Cosa si è imparato provandolo

In un colpo solo il modello scrive prosa buona ma rende il 28% della lunghezza
e ignora le istruzioni sepolte in un prompt lungo. A scene raggiunge la
lunghezza e rispetta tutti i vincoli, ma degenera: 1741 frasi da sei parole,
«artem guarda» ripetuto 340 volte.

Le due misure che contano non sono le parole totali — quel capitolo era al
176% dell'obiettivo — ma **parole per frase** e **inizi ripetuti**.

Le istruzioni vincolanti funzionano solo se stanno vicino al punto in cui
servono: il filo dell'aikido, messo dentro la scena in cui va chiuso, è stato
rispettato; lo stesso filo in fondo a un prompt lungo era stato ignorato.

## I fili narrativi

Tabella `fili_narrativi`: le cose piantate in un capitolo che devono tornare in
un altro, con i riscontri testuali.

- **cucchiaio** — *chiuso*. Piantato al capitolo 12, raccolto al 63: Artem posa
  sul granito di una cucina americana il cucchiaio piegato della casa
  bombardata. Cinquantun capitoli, e nessuno spiega niente. È il modello di
  come questo libro chiude un simbolo.
- **aikido** — *aperto*. Piantato nei capitoli 16-25, il canone gli assegna il
  capitolo 59, e lì la parola non compariva. Chiuso nella riscrittura.
- **spilla del Comitato** — *aperto*. Compare in un capitolo su 66, il primo.
  Da decidere se raccoglierlo o accettare che resti un dettaglio d'ambiente.

## Cosa resta

- **189.542 parole** mancanti rispetto all'obiettivo del canone
- **otto capitoli** con metà o più del testo in frasi da oltre sessanta parole,
  degenerate come il cap48: 21, 31, 37, 40, 46, 48, 51, 61
- **cap51**: decidere cosa fare del capitolo su Sergej
- **cap46**: la data 2024 dentro un blocco del 2026 — verosimilmente un
  flashback voluto, da confermare
- il titolo «Numero» compare due volte, ai capitoli 44 e 50: nel canone è così,
  quindi potrebbe essere un'eco intenzionale
