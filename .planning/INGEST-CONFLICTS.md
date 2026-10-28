## Conflict Detection Report

### BLOCKERS (0)

Nessun blocker rilevato. Nessuna contraddizione fra ADR LOCKED, nessuna classificazione UNKNOWN a
bassa confidenza (tutte le 6 classificazioni sono `high`), nessun ciclo di cross-ref pericoloso (vedi
INFO sotto per il ciclo benigno rilevato e come è stato trattato).

### WARNINGS (1)

[WARNING] Modello scenari: tronco-e-rami (ADR-001 R-001) vs branch-di-versione-base (SPEC D3)
  Found: docs/ADR-001-decisioni-dominio.md R-001 richiede un tronco centrale su cui sia i piani
    salvati sia gli scenari salvati sono rami dello stesso tipo di oggetto, elencabili e navigabili
    in modo uniforme (modello Kinaxis).
  Impact: docs/02-spec-m1-corrente.md §D3 (già implementato in T4, consegnato e verde) modella uno
    scenario come ramo di una versione base e un piano salvato come istanza DVERSIONS separata
    prodotta da promote() — due nature di oggetto diverse. L'ADR stesso dichiara che questo non è
    una contraddizione ma un'estensione, e lascia esplicitamente aperte le conseguenze:
    se è un rework di T4 o un layer sopra, cosa costituisce "il tronco" (la catena DVERSIONS
    ufficiali? un'entità nuova?), come conciliarlo con la convenzione di naming DVERSIONS che le
    misure DAX leggono come stringa. Tocca direttamente T4 (già consegnato), T11 (navigazione rami)
    e T12 (demo).
  → Decidere in fase di roadmap se R-001 è un rework di T4 o un'estensione additiva, prima di
    pianificare T11/T12; non risolvibile per sola precedenza perché lo stesso ADR lo definisce
    un'estensione da pianificare, non una sostituzione immediata.

### INFO (9)

[INFO] Auto-risolto per precedenza: SPEC supersede PRD su dettaglio task/AC/backlog
  Note: docs/02-spec-m1-corrente.md (SPEC, precedence 1) dichiara nel proprio header di supersedere
    docs/01-plan-m1.md (PRD, precedence 2) per numerazione task, testo/stato degli acceptance
    criteria e backlog — entrambi i documenti concordano esplicitamente su questa supersessione
    (header di entrambi i file). docs/01-plan-m1.md resta autorevole solo per contesto di business,
    misura Gartner, programma M1/M2/M3 e architettura A1-A11 per M2/M3. Trattato come supersessione
    dichiarata, non come contraddizione da arbitrare.

[INFO] Auto-risolto per precedenza: AC6 — rimozione del condizionale sull'offset
  Note: docs/01-plan-m1.md AC6 portava un condizionale sull'offset della domanda dipendente.
    docs/02-spec-m1-corrente.md AC6 lo rimuove (F10 chiusa: offset fisso a 2 mesi, letto da
    routing.lead_offset_months). SPEC vince per precedenza dichiarata; testo SPEC riportato come
    canonico in constraints.md.

[INFO] Auto-risolto: ADR-001 D-007 chiude la open question 1 dello SPEC (Average Assembly Hours/AC3)
  Note: docs/02-spec-m1-corrente.md lasciava aperta la conferma che il dato fosse popolato davvero;
    docs/ADR-001-decisioni-dominio.md D-007 (precedence 0, LOCKED) chiude: il dato esiste, è
    popolato ma non aggiornato, si usa come input e va marcato da revisionare; i test non devono
    dipendere dal suo valore assoluto. ADR vince, SPEC aggiornato in constraints.md/decisions.md.

[INFO] Auto-risolto: ADR-001 D-008 chiude la open question 4 dello SPEC (sorgente job 3000)
  Note: docs/02-spec-m1-corrente.md raccomandava un parametro esplicito copy_from: version_ref senza
    fissare la regola. docs/ADR-001-decisioni-dominio.md D-008 (LOCKED) fissa la regola: carry-forward
    alternato (preliminary copia da requested precedente, requested copia da preliminary precedente).
    ADR vince; la raccomandazione SPEC di un parametro esplicito resta valida come dettaglio
    implementativo, il comportamento è ora vincolato da D-008.

[INFO] Auto-risolto con estensione di design: ADR-001 D-006 chiude/estende la open question 3 dello
SPEC (variant_key routing elettivo)
  Note: docs/02-spec-m1-corrente.md raccomandava di modellare variant_key come chiave opaca singola
    alimentata dall'orderbook. docs/ADR-001-decisioni-dominio.md D-006 (LOCKED) richiede che il
    routing elettivo sia modellato su un insieme di attributi di configurazione valutati insieme
    (colore, jib, altri), estendibile senza modifiche di schema. ADR vince; implicazione di design
    per T6.d da valutare esplicitamente (la colonna routing.variant_key nello schema SPEC è
    disegnata come singola chiave opzionale) — non un blocker, ma un vincolo di design da verificare
    contro il codice quando T6.d viene pianificato.

[INFO] Confermato, nessuna contraddizione: ADR-001 D-005 corrobora il design di back-allocation SPEC
  Note: docs/02-spec-m1-corrente.md §D2/AC27 tratta le regole ANA-050 §3.3 di back-allocation come
    comportamento di produzione corrente. docs/ADR-001-decisioni-dominio.md D-005 conferma
    esplicitamente che ANA-050 è live. Nessun conflitto: rafforza l'assunzione già presente nello
    SPEC.

[INFO] Ciclo di cross-reference rilevato e classificato come benigno (supersessione dichiarata)
  Note: il grafo dei cross_refs contiene un ciclo fra docs/01-plan-m1.md ↔ docs/02-spec-m1-corrente.md
    (riferimento reciproco) e un ciclo più ampio 01-plan-m1.md → 02-spec-m1-corrente.md →
    README.md → 01-plan-m1.md. Entrambi i cicli corrispondono a riferimenti "vedi anche/supersede"
    fra documenti che si dichiarano esplicitamente in relazione di supersessione parziale
    (vedi header di entrambi i file coinvolti), non a una catena di dipendenza circolare che renda
    la sintesi indeterminata: ogni documento è stato letto e sintetizzato una sola volta, in base
    alla propria classificazione di tipo, indipendentemente dagli altri. Sintesi proceduta su tutti
    e 6 i documenti, nessuno escluso per ciclo.

[INFO] ADR-001 D-003/D-004 (identità sito Southport/Rivermouth, Eastbrook SEA come plant) toccano
master data già consegnato in T1
  Note: docs/ADR-001-decisioni-dominio.md D-003 e D-004 sono chiarimenti di dominio nuovi (non
    presenti in docs/01-plan-m1.md o docs/02-spec-m1-corrente.md) su master data plant. Il task T1
    (schema+seed) risulta **done** e verificato per docs/03-consegna-t1-t4.md. Questo ingest non ha
    accesso ai file di seed (`db/seed/data/*.json`, fuori dal set di documenti classificati) e non
    può verificare se il master data già costruito rispetta queste due decisioni. Nessuna
    contraddizione rilevata nei documenti letti — segnalato per verifica a valle prima di
    ripianificare o toccare T1.

[INFO] RISOLTO 2026-09-19: D-001 confermata dal product owner come vincolo DOPPIO (slot E ore)
  Note: era il secondo WARNING di questo report. La domanda "i tre Basic Assemblies consumano slot a
    Northfield o solo ore" era un aut-aut risposto con un si', e la lettura registrata inizialmente in
    docs/ADR-001-decisioni-dominio.md era "consumano slot". Il product owner ha confermato il
    2026-09-19: consumano **sia slot sia ore**. Il vincolo di capacita' di T7 e' doppio e i due
    controlli sono indipendenti — una riga di Basic Assembly puo' essere respinta per esaurimento
    slot oppure per esaurimento ore. docs/ADR-001-decisioni-dominio.md D-001 e
    .planning/intel/decisions.md D-001 sono stati aggiornati; gli AC di T7 devono esprimere entrambi
    i limiti e i test devono coprire i due modi di esaurimento separatamente. WARNING chiuso.

[INFO] RISOLTO 2026-09-19: D-003/D-004 verificati contro il seed, nessun rework di T1
  Note: l'INFO precedente segnalava che questo ingest non poteva verificare se il master data di T1
    rispettasse D-003 (Southport e Rivermouth stesso sito) e D-004 (Eastbrook SEA e' un plant).
    Verificato direttamente su db/seed/data/plant_master.json: il seed contiene 9 plant
    (FR-WESTVALE, DE-GANDERKESEE, AT-NORTHFIELD, US-CERRITOS, CA-NIAGARA e i terzisti EXT-OEM,
    EXT-OEM-DELTA, EXT-PARTNERB-MEX, EXT-CIS-INSTALL) e **nessuno** di Southport, Rivermouth o
    Eastbrook. D-003 e D-004 non contraddicono quindi T1: sono vincoli sul master data reale, cioe'
    sull'adapter di T9 e sul go-live, non sul seed sintetico. Nessun rework di T1.
