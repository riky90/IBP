# Decisioni (ADR)

Fonte unica: `docs/ADR-001-decisioni-dominio.md` — tipo ADR, `status: accepted`, `locked: true`,
`precedence: 0` (massima autorevolezza, per-doc override rispetto al default ADR>SPEC>PRD>DOC,
comunque coerente col default). Data: 2026-09-19. Autore: il product owner (Mario).

Header del documento: "Queste decisioni vengono dal product owner ... e sono più recenti di
`docs/02-spec-m1-corrente.md`. Dove questo documento e lo SPEC divergono, vale questo documento."

Tutte le decisioni sotto sono **LOCKED**: non sovrascrivibili automaticamente da nessuna fonte
successiva (SPEC, PRD, DOC) — solo da un altro ADR che le rimpiazzi esplicitamente.

---

## D-001 — I tre Basic Assemblies consumano slot E ore a Northfield

status: locked (accepted, confermata 2026-09-19) | source: docs/ADR-001-decisioni-dominio.md | scope: capacita'/T7 allocatore

I tre Basic Assemblies consumano **sia uno slot sia ore del pool** a Northfield. Il vincolo di capacita'
e' **doppio** e i due controlli sono indipendenti: l'allocatore di T7 deve poter respingere una riga
di Basic Assembly perche' sono finiti gli slot della assembly island **oppure** perche' sono finite
le ore del pool mensile. Gli AC di T7 devono esprimere entrambi i limiti e i test devono coprire i
due modi di esaurimento separatamente.

Ambiguita' risolta: la domanda originaria era un aut-aut ("slot o solo ore"), la prima risposta non
disambiguava. Confermato dal product owner il 2026-09-19 come vincolo doppio. Il WARNING relativo
nel report conflitti e' chiuso.

## D-002 — Le convenzioni di naming sono mantenute dal product owner

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: master data / governance

Le convenzioni `_Plant` e `-BA` sono mantenute da Mario; nessun owner terzo aziendale, nessun
processo esterno di cambio senza preavviso. Il codice può trattarle come stabili, ma restano logica
applicativa portante (le misure DAX ricostruiscono i nomi come stringhe) — vanno centralizzate in un
solo punto, non replicate.

## D-003 — Southport e Rivermouth sono lo stesso sito

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: master data plant

Due nomi dello stesso sito, non due plant distinti. Seed e master data devono rappresentarli come
una sola entità con, al più, un alias. Qualunque logica che li conta come due sedi sovrastima la
capacità disponibile. **Tocca T1 (già consegnato)** — vedi nota in `constraints.md` / INFO nel
report conflitti: non verificato in questo ingest se il seed già consegnato rispetta questa regola.

## D-004 — Eastbrook SEA è un plant

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: master data plant

`Eastbrook SEA` non è uno scope di vendita: è il plant di Eastbrook dedicato al marino (SEA = segmento
marino). Va modellato come plant, con proprio scope produttivo, non come attributo commerciale.
**Tocca T1 (già consegnato)** — stessa nota di verifica di D-003.

## D-005 — ANA-050 è live

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: back-allocation (T6.d)

La specifica ANA-050 §3.3 è andata live. Le regole di back-allocation e la correzione a resto
massimo che il design D2 dello SPEC eredita da ANA-050 descrivono il comportamento di produzione
**corrente**, non una proposta. Conferma/corrobora (non contraddice) `docs/02-spec-m1-corrente.md`
§D2/AC27 — vedi INFO nel report conflitti.

## D-006 — Il routing elettivo NAM è guidato da più attributi di configurazione

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: rete produttiva (T6.d)

Non è un attributo solo: colore è uno dei driver, ma ci sono anche jib e altri. Il routing elettivo
va modellato su un **insieme** di attributi di configurazione valutati insieme, non su una singola
colonna discriminante. L'elenco completo non è chiuso: il modello deve essere estendibile senza
modifiche di schema. **Chiude la open question 3 di `docs/02-spec-m1-corrente.md`** (che raccomandava
una chiave opaca singola alimentata dall'orderbook) — estende quella raccomandazione a un insieme di
attributi. Vedi INFO nel report conflitti per l'implicazione sul design di `routing.variant_key`.

## D-007 — Average Assembly Hours è presente ma non aggiornato

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: capacità (T7, AC3)

Il campo esiste ed è popolato, ma il dato **non è aggiornato**. Si usa come dato di input (il
sistema lo consuma normalmente) ma va marcato come da revisionare prima del go-live. Non va trattato
come dato di riferimento affidabile nei test di accettazione che dipendono dal suo valore assoluto:
i test verificano la meccanica, non la correttezza del numero. **Chiude la open question 1 di
`docs/02-spec-m1-corrente.md` (AC3)** — vedi INFO nel report conflitti.

## D-008 — Il job 3000 copia dall'istanza precedente del lato vendita (carry-forward alternato)

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: processo (T8)

Il job `3000` copia dall'istanza precedente del lato vendita, alternando i due stati: creando una
istanza **preliminary**, copia dalla precedente **requested**; creando una istanza **requested**,
copia dalla precedente **preliminary**. È un carry-forward alternato, non una copia dall'istanza
omonima precedente. **Chiude la open question 4 di `docs/02-spec-m1-corrente.md`** (che raccomandava
solo un parametro esplicito `copy_from: version_ref` senza fissare la regola) — vedi INFO nel report
conflitti.

---

## R-001 — Modello a tronco e rami, stile Kinaxis (requisito nuovo)

status: locked (accepted) | source: docs/ADR-001-decisioni-dominio.md | scope: scenari (T4 già
consegnato, T11, T12)

Il modello degli scenari deve presentarsi come un **tronco centrale** sul quale sia i **piani
salvati** sia gli **scenari salvati** sono **rami** — il modello Kinaxis, comportamento atteso dal
product owner.

**Non è dichiarata una contraddizione col design D3 esistente** (`edits` append-only → `overlay` →
`COALESCE` sullo stack di layer, con `promote()` che materializza una nuova istanza `DVERSIONS`), ma
**un'estensione con una differenza sostanziale**: oggi uno scenario è un ramo di una versione base,
mentre un piano salvato è un'istanza `DVERSIONS` prodotta dalla promozione — cioè una cosa di natura
diversa. Il requisito chiede che le due cose siano **lo stesso tipo di oggetto**: rami dello stesso
tronco, elencabili, confrontabili e navigabili in modo uniforme.

Conseguenze esplicitamente lasciate alla fase di pianificazione dal documento stesso (non decise
qui):
- T4 è già chiuso e verde; questo requisito ne tocca la semantica di `promote()` e la
  rappresentazione dei piani salvati — va deciso se è un rework di T4 o un layer sopra.
- Il tronco ha bisogno di identità e ordinamento espliciti (cosa è il tronco: la catena delle
  istanze `DVERSIONS` ufficiali? un'entità nuova?).
- La convenzione di naming `DVERSIONS` e le misure DAX che la leggono come stringa vincolano cosa il
  tronco può essere senza rompere il consumo a valle.
- Tocca direttamente la UI di T11 (navigazione dei rami) e la demo di T12.

**Questa è la tensione genuina segnalata come WARNING nel report conflitti — non auto-risolta.**
Vedi anche `constraints.md` (D3) per il design attuale che il requisito estende.

## Impatto complessivo sulle open question del piano (dichiarato nella fonte)

- `Average Assembly Hours` / AC3 → chiusa da D-007.
- Sorgente del job `3000` → chiusa da D-008.
- Routing elettivo NAM → chiusa da D-006 (elenco attributi tenuto aperto per estensione).
- Restano aperte, non toccate da questo ADR: il pool di modelli forecast con storia corta (T5.b),
  `variant_key` come dettaglio implementativo residuo, e la partizione del DAG.
