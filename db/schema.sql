-- ============================================================================
-- IBP platform — schema DuckDB (M1)
-- Mirror dello star schema Infor dEPM (nomi dei fatti preservati) con un solo
-- master di item al posto di DSALES_PRODUCT/DMANUFACT_KEY, + overlay a grafo
-- + rete produttiva + scenari + forecast/FVA + processo P/R/A/C.
--
-- Convenzioni:
--   - Nessun vincolo FOREIGN KEY applicato: è un mirror di un cubo OLAP, non un
--     OLTP; l'integrità referenziale è verificata dal seed (db/build_db.py) e
--     dai controlli post-load, non da constraint DuckDB (evita fragilità
--     sull'ordine di caricamento di righe nullable/self-referenti).
--   - PRIMARY KEY / UNIQUE sono invece dichiarati: intercettano duplicati nel
--     seed, che sarebbero altrimenti un dato sbagliato silenzioso.
--   - is_deleted, is_budget, is_frozen, is_provisional: booleani NOT NULL con
--     DEFAULT esplicito — mai NULL come sentinella (vedi A7).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Mirror star schema dEPM
-- ----------------------------------------------------------------------------

CREATE TABLE DIM_DATE (
    date_key      INTEGER PRIMARY KEY,   -- YYYYMM
    date          DATE NOT NULL,         -- primo giorno del mese
    year          INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    month_name    VARCHAR NOT NULL,
    quarter       INTEGER NOT NULL,
    year_month    VARCHAR NOT NULL       -- 'YYYY-MM'
);

-- Un solo master di item, con un ruolo. Sostituisce DSALES_PRODUCT +
-- DMANUFACT_KEY + il layer semilavorati: erano tre tabelle per la stessa
-- entità, e il legame fra loro finiva nei suffissi del nome (-BA, -BR, _Plant).
--   - `region` è un attributo: è ciò che manda in pensione -BA e -BR, dove la
--     region viveva nel nome del planning model (32 modelli con (NAM)/(LATAM)).
--   - `is_sellable` distingue ciò che ha un prezzo da ciò che esiste solo per
--     la produzione (i tre Basic Assemblies di Northfield): il semilavorato non è
--     "un planning model mancante", è un item non vendibile.
--   - Gli attributi commerciali sono NULL sui manufacturing key e viceversa:
--     una colonna nulla è dichiarata, un nome-con-convenzione no.
CREATE TABLE item (
    item_key                  BIGINT PRIMARY KEY,
    role                       VARCHAR NOT NULL
        CHECK (role IN ('planning_model', 'manufacturing_key', 'semi_finished')),
    model                       VARCHAR NOT NULL,
    region                       VARCHAR NOT NULL
        CHECK (region IN ('APAC', 'CIS', 'EMEA', 'LATAM', 'NAM', 'GLOBAL')),
    is_sellable                   BOOLEAN NOT NULL,
    -- lato commerciale (valorizzato per role = 'planning_model')
    product_division               VARCHAR,
    product_division_code           VARCHAR,
    product_line                     VARCHAR,
    product_category                  VARCHAR,
    -- lato manifatturiero (valorizzato per manufacturing_key / semi_finished)
    manufacturing_line                 VARCHAR,
    manufacturing_category              VARCHAR,   -- include Cluster 10-15,31-33,38
    manufacturing_family                 VARCHAR,
    -- AC3: seconda valuta di capacità, deve avere un consumatore reale (TSOP_OPS)
    average_assembly_hours                 DECIMAL(10, 2) NOT NULL DEFAULT 0,
    -- AC2: il "x2" hard-coded oggi diventa il caso particolare factor=2, come dato
    slot_equivalence_factor                  DECIMAL(6, 3) NOT NULL DEFAULT 1.0,
    is_active                                  BOOLEAN NOT NULL DEFAULT TRUE
);

-- L'identità di un item è una riga datata, non la sua chiave primaria.
-- Tre difetti misurati che questa tabella chiude:
--   - caption drift: su 126 planning model su 685 il demand mostra l'element
--     name e il supply il caption (riscritto con il material number SAP). Sono
--     due `id_type` dello stesso item, non due item.
--   - il caso Steyr: un attributo di identità modificato in place riscrive la
--     storia dei cicli passati. Qui la vecchia identità resta, con valid_to.
--   - il material number SAP compare quando la distinta esiste: è un terzo
--     identificatore che nasce dopo, non un rinomino.
CREATE TABLE item_identifier (
    identifier_id     BIGINT PRIMARY KEY,
    item_key            BIGINT NOT NULL,     -- FK logica -> item.item_key
    id_type                VARCHAR NOT NULL
        CHECK (id_type IN ('element_name', 'caption', 'sap_material', 'legacy')),
    value                     VARCHAR NOT NULL,
    valid_from                   DATE NOT NULL,
    valid_to                        DATE,
    UNIQUE (item_key, id_type, valid_from)
);

CREATE TABLE DPLANT (
    plant_key                 BIGINT PRIMARY KEY,
    plant_code                 VARCHAR NOT NULL UNIQUE,
    plant_name                 VARCHAR NOT NULL,
    plant_activity              VARCHAR NOT NULL,
    plant_region                 VARCHAR NOT NULL
        CHECK (plant_region IN ('APAC', 'CIS', 'EMEA', 'LATAM', 'NAM')),
    -- I terzisti (OEM, OEM-Delta, Partner-B, CIS External Installation) sono
    -- plant a tutti gli effetti e hanno una capacità propria: senza di essa il
    -- piano non sa se il conto lavoro regge. Ma sono esterni, e la colonna lo
    -- dice — non si deduce dal nome. Un terzista si satura e si vincola come
    -- un plant interno; le decisioni che ci si prendono sopra sono diverse.
    plant_type                    VARCHAR NOT NULL DEFAULT 'internal'
        CHECK (plant_type IN ('internal', 'subcontractor')),
    -- AC2: regole di capacità come master data, non literal in codice
    layout_type                   VARCHAR NOT NULL
        CHECK (layout_type IN ('flow_line', 'assembly_island')),
    max_slots                     INTEGER NOT NULL,
    slot_granularity_factor       DECIMAL(6, 3) NOT NULL DEFAULT 4.0
);

CREATE TABLE DSALES_DIVISION (
    division_key     BIGINT PRIMARY KEY,
    division_code     VARCHAR NOT NULL UNIQUE,
    division_name     VARCHAR NOT NULL,
    region             VARCHAR NOT NULL
        CHECK (region IN ('APAC', 'CIS', 'EMEA', 'LATAM', 'NAM'))
);

CREATE TABLE DVERSIONS (
    version_key             BIGINT PRIMARY KEY,
    version_name             VARCHAR NOT NULL UNIQUE,
    cycle_year               INTEGER NOT NULL,
    cycle_month               INTEGER NOT NULL,
    side                       VARCHAR
        CHECK (side IS NULL OR side IN ('DEMAND', 'SUPPLY')),
    status                     VARCHAR
        CHECK (status IS NULL OR status IN ('P', 'R', 'A', 'C')),
    is_budget                   BOOLEAN NOT NULL DEFAULT FALSE,
    is_frozen                   BOOLEAN NOT NULL DEFAULT FALSE,
    first_planning_year         INTEGER NOT NULL,
    first_planning_month         INTEGER NOT NULL,
    valid_budget_version           VARCHAR   -- riferimento (per nome) al SOP_BP_YYYY applicabile
);

CREATE TABLE DMEASURE_DEMAND (
    measure_key   BIGINT PRIMARY KEY,
    measure_code   VARCHAR NOT NULL UNIQUE,
    measure_name   VARCHAR NOT NULL,
    uom             VARCHAR NOT NULL,
    agg_method       VARCHAR NOT NULL
        CHECK (agg_method IN ('sum', 'count', 'min', 'max', 'avg', 'ratio'))
);

CREATE TABLE DMEASURE_OPS (
    measure_key   BIGINT PRIMARY KEY,
    measure_code   VARCHAR NOT NULL UNIQUE,
    measure_name   VARCHAR NOT NULL,
    uom             VARCHAR NOT NULL,
    agg_method       VARCHAR NOT NULL
        CHECK (agg_method IN ('sum', 'count', 'min', 'max', 'avg', 'ratio'))
);

-- Grana: (version_key, product_key, division_key, date_key, measure_key) -> value
-- `region` è ridondante rispetto a DSALES_DIVISION ed è tenuta comunque, come
-- nell'export reale: è la coordinata su cui il piano viene letto.
CREATE TABLE TSOP_DEMAND (
    version_key    BIGINT NOT NULL,
    product_key     BIGINT NOT NULL,      -- FK logica -> item.item_key (role='planning_model')
    division_key     BIGINT NOT NULL,
    region             VARCHAR NOT NULL
        CHECK (region IN ('APAC', 'CIS', 'EMEA', 'LATAM', 'NAM')),
    date_key             INTEGER NOT NULL,
    measure_key           BIGINT NOT NULL,
    value                   DOUBLE NOT NULL,
    PRIMARY KEY (version_key, product_key, division_key, date_key, measure_key)
);

-- Grana piena: il supply plan porta anche le coordinate di vendita.
-- È la correzione del difetto misurato sull'export: `Confirmed production units`
-- arriva scritto a manufacturing key x plant, il planning model non è una
-- coordinata che la conferma ha, e tutte le 1.080 righe finiscono sul modello
-- `Dummy`. Le coordinate di vendita venivano poi ricostruite a posteriori,
-- pro-rata, dopo il fatto. Qui product_key è NOT NULL: una conferma senza
-- planning item non è scrivibile, quindi non c'è niente da ricostruire.
CREATE TABLE TSOP_OPS (
    version_key    BIGINT NOT NULL,
    manufact_key    BIGINT NOT NULL,      -- FK logica -> item.item_key (role='manufacturing_key'|'semi_finished')
    plant_key         BIGINT NOT NULL,
    product_key         BIGINT NOT NULL,    -- FK logica -> item.item_key (role='planning_model')
    division_key          BIGINT NOT NULL,
    region                  VARCHAR NOT NULL
        CHECK (region IN ('APAC', 'CIS', 'EMEA', 'LATAM', 'NAM')),
    date_key                  INTEGER NOT NULL,
    measure_key                BIGINT NOT NULL,
    value                        DOUBLE NOT NULL,
    PRIMARY KEY (version_key, manufact_key, plant_key, product_key, division_key, date_key, measure_key)
);

-- Parametro settimanale (Weeks Production / CIT_PUTTHROUGHTIME) alla base dello
-- spread a due mesi. calweek_date = lunedì della settimana ISO.
CREATE TABLE TWSC_PAR_CALWEEK (
    version_key    BIGINT NOT NULL,
    manufact_key    BIGINT NOT NULL,
    plant_key         BIGINT NOT NULL,
    calweek_date       DATE NOT NULL,
    measure_key         BIGINT NOT NULL,
    value                 DOUBLE NOT NULL,
    PRIMARY KEY (version_key, manufact_key, plant_key, calweek_date, measure_key)
);

-- ----------------------------------------------------------------------------
-- 2. Overlay a grafo (A4) — un'unica tabella di archi tipizzati.
--    Nodi di M1: plant, region, product, manufact_key, project, resource, measure.
--    M2/M3 aggiungono dealer, importer, installer, supplier senza migrazione:
--    from_type/to_type sono VARCHAR liberi, non un CHECK enumerato chiuso.
-- ----------------------------------------------------------------------------

CREATE TABLE edge (
    edge_id       BIGINT PRIMARY KEY,
    from_type      VARCHAR NOT NULL,
    from_key        VARCHAR NOT NULL,
    rel_type          VARCHAR NOT NULL,
    to_type            VARCHAR NOT NULL,
    to_key              VARCHAR NOT NULL,
    valid_from            DATE NOT NULL,
    valid_to                DATE,
    attrs_json                VARCHAR NOT NULL DEFAULT '{}'
);

-- ----------------------------------------------------------------------------
-- 3. Rete produttiva (A2) — il cuore di M1.
-- ----------------------------------------------------------------------------

-- F7: una sola tabella di legami fra item, tipizzata e datata. Sostituisce
-- `product_mapping`, che sapeva esprimere solo planning model -> manufacturing
-- key con una percentuale.
--
-- Gli otto casi misurati sull'export entrano tutti qui, come dato:
--   'produces'          1:1 diretto (462 modelli) e caption drift (126, che
--                       però è una riga di item_identifier, non un legame)
--   'aggregates'        N:1, i sette YCRANE_* (24 modelli)
--   'splits'            1:N, i due casi reali (Timber & Recycling, PFD 79/99)
--   'dependent_demand'  il semilavorato: -BA/-BR e i Basic Assemblies di
--                       Northfield, con offset_months = 2. Oggi è un file Excel
--                       che scrive sul database.
--
-- `quota_source` dice da dove viene la quota, ed è la decisione del 2026-09-10
-- sullo split oltre l'orizzonte dell'orderbook: 'observed_history' significa
-- che la quota è il mix osservato a consuntivo sugli ultimi
-- `quota_window_months`, ricalcolato ad ogni ciclo. Una percentuale mantenuta
-- a mano invecchia in silenzio; un mix osservato no, e quando l'orderbook non
-- copre più l'orizzonte è l'unica base che resta ancorata ai fatti.
CREATE TABLE item_link (
    link_id             BIGINT PRIMARY KEY,
    from_item             BIGINT NOT NULL,     -- FK logica -> item.item_key (lato domanda)
    to_item                 BIGINT NOT NULL,    -- FK logica -> item.item_key (lato produzione)
    link_type                  VARCHAR NOT NULL
        CHECK (link_type IN ('produces', 'aggregates', 'splits', 'dependent_demand')),
    period                       DATE NOT NULL,
    quota_pct                      DECIMAL(6, 3) NOT NULL CHECK (quota_pct > 0 AND quota_pct <= 100),
    quota_source                     VARCHAR NOT NULL
        CHECK (quota_source IN ('rule', 'observed_history', 'manual_override')),
    quota_window_months                INTEGER,   -- valorizzato solo per 'observed_history'
    offset_months                        INTEGER NOT NULL DEFAULT 0,
    override_by                            VARCHAR,
    override_at                              TIMESTAMP,
    valid_from                                 DATE NOT NULL,
    valid_to                                     DATE,
    UNIQUE (from_item, to_item, link_type, period)
);

-- F8: quali plant POSSONO produrre una manufacturing key, per quale region.
CREATE TABLE production_eligibility (
    eligibility_id     BIGINT PRIMARY KEY,
    manufacturing_key    BIGINT NOT NULL,      -- FK logica -> item.item_key
    plant                  BIGINT NOT NULL,      -- FK logica -> DPLANT.plant_key
    region_scope              VARCHAR NOT NULL
        CHECK (region_scope IN ('APAC', 'CIS', 'EMEA', 'LATAM', 'NAM', 'GLOBAL')),
    priority                     INTEGER NOT NULL,
    valid_from                     DATE NOT NULL,
    valid_to                         DATE
);

-- F9/F10: percorsi produttivi multi-step. mandatory=true -> guidato dal modello
-- (es. ILK/ILT Ganderkesee->Cerritos); mandatory=false -> guidato dalla
-- configurazione venduta, discriminato da variant_key (es. NAM Northfield/Niagara).
CREATE TABLE routing (
    routing_id          BIGINT PRIMARY KEY,
    manufacturing_key      BIGINT NOT NULL,
    variant_key                VARCHAR,      -- NULL quando mandatory=true (nessuna scelta)
    step_no                       INTEGER NOT NULL,
    plant                            BIGINT NOT NULL,   -- FK logica -> DPLANT.plant_key
    operation_type                     VARCHAR NOT NULL,
    lead_offset_months                    INTEGER NOT NULL DEFAULT 0,
    mandatory                                BOOLEAN NOT NULL,
    UNIQUE (manufacturing_key, variant_key, step_no)
);

-- Fabbisogno di risorsa per step di routing, con offset e profilo di spread.
CREATE TABLE bill_of_resource (
    bor_id                BIGINT PRIMARY KEY,
    manufacturing_key       BIGINT NOT NULL,
    variant_key                 VARCHAR,
    resource_id                    VARCHAR NOT NULL,   -- FK logica -> resource.resource_id
    qty_per_unit                      DECIMAL(12, 4) NOT NULL,
    offset_periods                       INTEGER NOT NULL DEFAULT 0,
    spread_profile_json                     VARCHAR NOT NULL DEFAULT '{}'
);

CREATE TABLE resource (
    resource_id     VARCHAR PRIMARY KEY,
    node_type         VARCHAR NOT NULL,     -- es. 'plant_slot_pool', 'plant_hour_pool'
    node_key            VARCHAR NOT NULL,     -- es. plant_key come stringa
    uom                    VARCHAR NOT NULL,     -- 'slot' | 'hour'
    bucket                    VARCHAR NOT NULL DEFAULT 'month',
    capacity_source              VARCHAR NOT NULL  -- es. 'DPLANT.max_slots'
);

CREATE TABLE resource_capacity (
    resource_id       VARCHAR NOT NULL,
    period               DATE NOT NULL,
    available_qty           DECIMAL(14, 4) NOT NULL,
    calendar_id                 VARCHAR NOT NULL DEFAULT 'STD',
    utilisation_target             DECIMAL(6, 3) NOT NULL DEFAULT 0.85,
    PRIMARY KEY (resource_id, period)
);

-- ----------------------------------------------------------------------------
-- 4. Scenari (A7) — event log append-only -> overlay (cache) -> layer stack.
-- ----------------------------------------------------------------------------

CREATE TABLE scenario (
    scenario_id          VARCHAR PRIMARY KEY,
    name                    VARCHAR NOT NULL,
    base_version_key           BIGINT NOT NULL,      -- FK logica -> DVERSIONS.version_key
    base_snapshot_id              VARCHAR NOT NULL,   -- riferimento opaco alla base al momento del branch (per three-way merge, AC16)
    parent_scenario_id               VARCHAR,          -- NULL se non annidato
    owner                               VARCHAR NOT NULL,
    state                                 VARCHAR NOT NULL
        CHECK (state IN ('Draft', 'Evaluated', 'Promoted', 'Discarded')),
    created_at                              TIMESTAMP NOT NULL
);

-- Append-only: nessun UPDATE/DELETE previsto sopra questa tabella.
CREATE TABLE edits (
    edit_id           BIGINT PRIMARY KEY,
    scenario_id         VARCHAR NOT NULL,
    ts                     TIMESTAMP NOT NULL,
    "user"                    VARCHAR NOT NULL,
    cell_key_json                VARCHAR NOT NULL,
    measure_key                     BIGINT NOT NULL,
    old_value                          DOUBLE,
    new_value                             DOUBLE,
    op                                       VARCHAR NOT NULL CHECK (op IN ('set', 'increment', 'delete'))
);

-- Cache derivata dal log; is_deleted è il tombstone esplicito (mai NULL come sentinella).
-- PK surrogata: product_key/plant_key sono nullable (demand vs ops), e SQL non
-- ammette NULL in colonne PRIMARY KEY; l'unicità logica della cella è comunque
-- garantita da UNIQUE, che tratta i NULL come distinti (semantica standard).
CREATE TABLE overlay (
    overlay_id        BIGINT PRIMARY KEY,
    scenario_id          VARCHAR NOT NULL,
    version_key             BIGINT NOT NULL,
    product_key                BIGINT,      -- valorizzato lato demand
    plant_key                     BIGINT,      -- valorizzato lato ops
    date_key                         INTEGER NOT NULL,
    measure_key                         BIGINT NOT NULL,
    value                                   DOUBLE,       -- NULL ammesso solo se is_deleted=TRUE
    is_deleted                                BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (scenario_id, version_key, date_key, measure_key, product_key, plant_key)
);

-- ----------------------------------------------------------------------------
-- 5. Forecast e FVA (A8) — a lag costante, o l'FVA è irricostruibile dopo.
-- ----------------------------------------------------------------------------

CREATE TABLE forecast_snapshot (
    snapshot_id      BIGINT PRIMARY KEY,
    series_id           VARCHAR NOT NULL,
    target_period          DATE NOT NULL,
    created_period            DATE NOT NULL,
    lag                          INTEGER NOT NULL,   -- target_period - created_period, in mesi
    process_step                    VARCHAR NOT NULL
        CHECK (process_step IN ('naive', 'statistical', 'planner_adjusted', 'consensus')),
    value                               DOUBLE NOT NULL,
    model_name                            VARCHAR,
    UNIQUE (series_id, target_period, created_period, process_step)
);

CREATE TABLE forecast_override (
    override_id      BIGINT PRIMARY KEY,
    series_id            VARCHAR NOT NULL,
    target_period            DATE NOT NULL,
    created_period               DATE NOT NULL,
    "user"                          VARCHAR NOT NULL,
    reason_code                       VARCHAR NOT NULL,
    delta                                DOUBLE NOT NULL
);

CREATE TABLE actual_restatement (
    restatement_id     BIGINT PRIMARY KEY,
    series_id              VARCHAR NOT NULL,
    period                    DATE NOT NULL,
    value                        DOUBLE NOT NULL,
    restated_at                     TIMESTAMP NOT NULL
);

-- ----------------------------------------------------------------------------
-- 6. Processo e i due review mancanti (A9)
-- ----------------------------------------------------------------------------

CREATE TABLE cycle (
    cycle_id         BIGINT PRIMARY KEY,
    cycle_year          INTEGER NOT NULL,
    cycle_month            INTEGER NOT NULL,
    name                      VARCHAR NOT NULL UNIQUE,
    opened_at                    TIMESTAMP NOT NULL,
    closed_at                        TIMESTAMP,
    current_phase                       VARCHAR NOT NULL
);

CREATE TABLE cycle_phase (
    phase_id        BIGINT PRIMARY KEY,
    cycle_id           BIGINT NOT NULL,
    phase_no              INTEGER NOT NULL,
    name                     VARCHAR NOT NULL,
    day_start                  INTEGER NOT NULL,
    day_end                       INTEGER NOT NULL,
    stat_state                       VARCHAR NOT NULL
        CHECK (stat_state IN ('STAT_01', 'STAT_02', 'STAT_03')),
    gate                                VARCHAR
);

CREATE TABLE review_instance (
    review_id        BIGINT PRIMARY KEY,
    cycle_id            BIGINT NOT NULL,
    review_type            VARCHAR NOT NULL
        CHECK (review_type IN ('Portfolio', 'Demand', 'GlobalDemandValidation',
                                'Supply', 'IntegratedReconciliation', 'MBR')),
    day_start                 INTEGER NOT NULL,
    day_end                      INTEGER NOT NULL,
    status                          VARCHAR NOT NULL,
    gate                               VARCHAR
);

CREATE TABLE task (
    task_id       BIGINT PRIMARY KEY,
    review_id        BIGINT NOT NULL,
    name                VARCHAR NOT NULL,
    owner                  VARCHAR NOT NULL,
    due_day                   INTEGER NOT NULL,
    status                       VARCHAR NOT NULL
);

CREATE TABLE raci (
    raci_id      BIGINT PRIMARY KEY,
    task_id         BIGINT NOT NULL,
    role               VARCHAR NOT NULL CHECK (role IN ('R', 'A', 'C', 'I')),
    party                 VARCHAR NOT NULL
);

CREATE TABLE portfolio_item (
    item_id         BIGINT PRIMARY KEY,
    product_key         BIGINT,     -- FK logica -> item.item_key, NULL se pre-lancio
    name                   VARCHAR NOT NULL,
    lifecycle_state           VARCHAR NOT NULL
        CHECK (lifecycle_state IN ('Concept', 'Development', 'Launch', 'Mature', 'Decline', 'Retired'))
);

CREATE TABLE project (
    project_id      BIGINT PRIMARY KEY,
    portfolio_item_id   BIGINT NOT NULL,
    name                   VARCHAR NOT NULL,
    state                     VARCHAR NOT NULL
        CHECK (state IN ('Proposed', 'Assessed', 'Resourced', 'Approved', 'InExecution', 'Closed')),
    target_launch_date          DATE
);

CREATE TABLE project_resource_demand (
    demand_id      BIGINT PRIMARY KEY,
    project_id        BIGINT NOT NULL,
    plant                BIGINT NOT NULL,    -- FK logica -> DPLANT.plant_key
    period                  DATE NOT NULL,
    slot_qty                   DECIMAL(12, 3) NOT NULL DEFAULT 0,
    hours_qty                     DECIMAL(12, 3) NOT NULL DEFAULT 0
);

CREATE TABLE portfolio_decision (
    decision_id      BIGINT PRIMARY KEY,
    project_id          BIGINT NOT NULL,
    cycle_id                BIGINT NOT NULL,
    decision_type              VARCHAR NOT NULL
        CHECK (decision_type IN ('Introduce', 'Retire', 'Reposition', 'Defer')),
    effective_date                  DATE NOT NULL,
    decided_by                         VARCHAR NOT NULL
);

CREATE TABLE gap (
    gap_id          BIGINT PRIMARY KEY,
    cycle_id            BIGINT NOT NULL,
    scope                  VARCHAR NOT NULL,
    dimension_slice_json      VARCHAR NOT NULL,
    measure_key                  BIGINT,
    plan_value                      DOUBLE NOT NULL,
    target_value                       DOUBLE NOT NULL,
    delta_units                           DOUBLE NOT NULL,
    delta_value                              DOUBLE NOT NULL,
    owner                                       VARCHAR NOT NULL,
    category                                       VARCHAR NOT NULL,
    status                                            VARCHAR NOT NULL
        CHECK (status IN ('Open', 'Proposed', 'Filtered', 'Escalated', 'Closed'))
);

CREATE TABLE reconciliation_session (
    session_id       BIGINT PRIMARY KEY,
    cycle_id             BIGINT NOT NULL,
    held_at                  TIMESTAMP NOT NULL,
    agenda_json                  VARCHAR NOT NULL,   -- generata dai gap sopra soglia
    status                          VARCHAR NOT NULL
);

CREATE TABLE decision (
    decision_id      BIGINT PRIMARY KEY,
    session_id           BIGINT NOT NULL,
    gap_id                   BIGINT,
    description                  VARCHAR NOT NULL,
    decided_by                       VARCHAR NOT NULL,
    decided_at                          TIMESTAMP NOT NULL
);

CREATE TABLE escalation (
    escalation_id     BIGINT PRIMARY KEY,
    gap_id                BIGINT NOT NULL,
    session_id                BIGINT,
    level                         VARCHAR NOT NULL
        CHECK (level IN ('minor', 'intermediate', 'maximum')),
    escalated_to                     VARCHAR NOT NULL,
    escalated_at                        TIMESTAMP NOT NULL,
    status                                  VARCHAR NOT NULL
);

CREATE TABLE rate_card (
    rate_card_id      BIGINT PRIMARY KEY,
    manufacturing_category  VARCHAR,
    product_division            VARCHAR,
    period                          DATE NOT NULL,
    avg_revenue_per_unit                DECIMAL(14, 2) NOT NULL,
    avg_margin_pct                          DECIMAL(6, 3) NOT NULL,
    owner                                       VARCHAR NOT NULL
);

CREATE TABLE assumption (
    assumption_id     BIGINT PRIMARY KEY,
    cycle_id              BIGINT NOT NULL,
    name                      VARCHAR NOT NULL,
    description                   VARCHAR NOT NULL,
    owner                             VARCHAR NOT NULL,
    measure_key                          BIGINT,
    valid_from                              DATE NOT NULL,
    valid_to                                   DATE
);

-- F3: soglie come dato, marcate provvisorie NEL DATO (is_provisional), non nel commento.
CREATE TABLE exception_rule (
    rule_id         BIGINT PRIMARY KEY,
    name                VARCHAR NOT NULL,
    measure_key             BIGINT,
    threshold_pct               DECIMAL(6, 3) NOT NULL,
    comparison                     VARCHAR NOT NULL,   -- es. 'w/w'
    severity_level                    VARCHAR NOT NULL
        CHECK (severity_level IN ('minor', 'intermediate', 'maximum')),
    is_provisional                       BOOLEAN NOT NULL DEFAULT TRUE,
    source                                   VARCHAR NOT NULL   -- es. 'Gartner literature (F3)'
);

CREATE TABLE exception_instance (
    instance_id      BIGINT PRIMARY KEY,
    rule_id              BIGINT NOT NULL,
    cycle_id                 BIGINT NOT NULL,
    dimension_slice_json         VARCHAR NOT NULL,
    observed_value                  DOUBLE NOT NULL,
    threshold_value                    DOUBLE NOT NULL,
    severity_level                        VARCHAR NOT NULL
        CHECK (severity_level IN ('minor', 'intermediate', 'maximum')),
    status                                    VARCHAR NOT NULL
        CHECK (status IN ('Open', 'Acknowledged', 'Resolved')),
    raised_at                                    TIMESTAMP NOT NULL
);
