---
type: ADR
status: accepted
date: 2026-09-19
---

# ADR-001 — Decisioni di dominio chiuse dal product owner

<!-- PRECEDENZA 0. Queste decisioni vengono dal product owner (Mario) il 2026-09-19 e
     sono piu' recenti di docs/02-spec-m1-corrente.md. Dove questo documento e lo SPEC
     divergono, vale questo documento. -->

## Contesto

Il piano M1 (`docs/02-spec-m1-corrente.md`) portava otto domande di dominio aperte verso
l'azienda, elencate come rischio residuo, piu' un insieme di open question tecniche. Il
2026-09-19 il product owner le ha chiuse. Questo ADR le registra come decisioni vincolanti
e aggiunge un requisito di architettura nuovo sul modello degli scenari.

## Decisioni

### D-001 — I tre Basic Assemblies consumano slot E ore a Northfield

I tre Basic Assemblies consumano **sia uno slot sia ore del pool** a Northfield. Il vincolo di
capacita' e' quindi **doppio** e i due controlli sono indipendenti: l'allocatore di T7 deve poter
respingere una riga di Basic Assembly perche' sono finiti gli slot della assembly island **oppure**
perche' sono finite le ore del pool mensile.

Confermato dal product owner il 2026-09-19. La formulazione originaria della domanda era un aut-aut
("slot o solo ore") e la prima risposta non disambiguava; la conferma chiude l'ambiguita' in favore
del vincolo doppio. Gli acceptance criteria di T7 devono esprimere **entrambi** i limiti, non uno
solo, e i test devono coprire i due modi di esaurimento separatamente.

### D-002 — Le convenzioni di naming sono mantenute dal product owner

Le convenzioni `_Plant` e `-BA` sono mantenute da Mario. Non esiste un owner terzo in
azienda da consultare e non c'e' un processo esterno che possa cambiarle senza preavviso.
Il codice puo' trattarle come stabili, ma la convenzione resta logica applicativa portante
(le misure DAX ricostruiscono i nomi come stringhe), quindi va centralizzata in un solo
punto e non replicata.

### D-003 — Southport e Rivermouth sono lo stesso sito

Sono due nomi dello stesso sito, non due plant distinti. Il seed e il master data devono
rappresentarli come una sola entita' con, al piu', un alias. Qualunque logica che li conti
come due sedi sovrastima la capacita' disponibile.

### D-004 — Eastbrook SEA e' un plant

`Eastbrook SEA` non e' uno scope di vendita: e' il plant di Eastbrook dedicato al marino
(SEA = segmento marino). Va modellato come plant, con il suo scope produttivo, non come
attributo commerciale.

### D-005 — ANA-050 e' live

La specifica ANA-050 §3.3 e' andata live. Le regole di back-allocation e la correzione a
resto massimo che il design D2 eredita da ANA-050 descrivono quindi il comportamento di
produzione corrente, non una proposta.

### D-006 — Il routing elettivo NAM e' guidato da piu' attributi di configurazione

Non e' un attributo solo. Il colore e' certamente uno dei driver, ma ci sono anche il jib
e altri attributi. Il routing elettivo va quindi modellato su un **insieme** di attributi
di configurazione valutati insieme, non su una singola colonna discriminante. L'elenco
completo degli attributi non e' ancora chiuso: il modello deve essere estendibile senza
modifiche di schema.

### D-007 — Average Assembly Hours e' presente ma non aggiornato

Il campo `Average Assembly Hours` esiste ed e' popolato, ma il dato **non e' aggiornato**.
Decisione: si usa come dato di input, il sistema lo consuma normalmente, ma va marcato come
da revisionare prima del go-live. Non va trattato come dato di riferimento affidabile nei
test di accettazione che dipendono dal suo valore assoluto; i test devono verificare la
meccanica, non la correttezza del numero.

### D-008 — Il job 3000 copia dall'istanza precedente del lato vendita

Il job `3000` copia tutto dall'istanza precedente del lato vendita, alternando i due stati:

- se si crea una istanza **preliminary**, copia dalla precedente **requested**;
- se si crea una istanza **requested**, copia dalla precedente **preliminary**.

E' un carry-forward alternato, non una copia dall'istanza omonima precedente.

## Requisito nuovo

### R-001 — Modello a tronco e rami, stile Kinaxis

Il modello degli scenari deve presentarsi come un **tronco centrale** sul quale sia i
**piani salvati** sia gli **scenari salvati** sono **rami**. E' il modello di Kinaxis, ed e'
il comportamento atteso dal product owner.

Rispetto al design D3 attuale (`edits` append-only → `overlay` → `COALESCE` sullo stack di
layer, con `promote()` che materializza una nuova istanza `DVERSIONS`) questo non e' una
contraddizione ma un'estensione, con una differenza sostanziale: oggi uno scenario e' un
ramo di una *versione base*, mentre un piano salvato e' una istanza `DVERSIONS` prodotta
dalla promozione, cioe' una cosa di natura diversa. Il requisito chiede che le due cose
siano **lo stesso tipo di oggetto**: rami dello stesso tronco, elencabili, confrontabili e
navigabili in modo uniforme.

Conseguenze da valutare in fase di pianificazione, non decise qui:

- T4 e' gia' chiuso e verde; questo requisito ne tocca la semantica di `promote()` e la
  rappresentazione dei piani salvati. Va deciso se e' un rework di T4 o un layer sopra.
- Il tronco ha bisogno di una identita' e di un ordinamento espliciti (cosa e' il tronco:
  la catena delle istanze `DVERSIONS` ufficiali? una entita' nuova?).
- La convenzione di naming `DVERSIONS` e le misure DAX che la leggono come stringa vincolano
  cosa il tronco puo' essere senza rompere il consumo a valle.
- Tocca direttamente la UI di T11 (navigazione dei rami) e la demo di T12.

## Impatto sulle open question del piano

Le open question del piano rigenerato che dipendevano da queste risposte:

- **`Average Assembly Hours` / AC3** — chiusa da D-007: si usa il dato, marcato da revisionare.
- **sorgente del job `3000`** — chiusa da D-008.
- **routing elettivo NAM** — chiusa da D-006, con l'elenco attributi tenuto aperto per estensione.

Restano aperte, non toccate da questo ADR: il pool di modelli forecast con storia corta
(T5.b), `variant_key`, e la partizione del DAG.
