"""Supporto condiviso per i test di `ibp/scenario/` (T4). Non è un file di
test: costanti di fixture verificate contro `data/ibp.duckdb` reale.

Tutti i test che usano questi dati mutano lo stato (`branch`/`set_cell`/
`promote` scrivono) e quindi vanno **sempre** eseguiti contro
`writable_db_copy` (una copia in `tmp_path`), mai contro il file reale —
stessa regola di `test_semantic_ac2_master_data.py`.
"""
from __future__ import annotations

# Base demand: SOP_2026_05_DEMAND_P, ha TSOP_DEMAND popolato.
DEMAND_BASE_VERSION_KEY = 353

# Cella demand nota con ESATTAMENTE 2 righe base (division_key 32 e 9),
# mix osservato non equo (28%/72%): buona per verificare la proration senza
# che uno split 50/50 nasconda un bug (proratare vs distribuire equo danno
# risultati diversi solo se il mix non è 50/50).
# TSOP_DEMAND: (product=9, division=32, region=NAM, date=202605, measure=1) = 34.475
#              (product=9, division=9,  region=EMEA, date=202605, measure=1) = 88.55
# somma = 123.025
DEMAND_PRORATION_PRODUCT_KEY = 9
DEMAND_PRORATION_DATE_KEY = 202605
DEMAND_PRORATION_MEASURE_KEY = 1  # REQ_PROD
DEMAND_PRORATION_BASE_ROWS = (
    (32, "NAM", 34.475),
    (9, "EMEA", 88.55),
)
DEMAND_PRORATION_BASE_SUM = 123.025

# Base ops: SOP_2026_05_SUPPLY_A, ha TSOP_OPS popolato.
OPS_BASE_VERSION_KEY = 355

# Cella ops nota con esattamente 2 righe base, mix non equo (~91%/9%).
# TSOP_OPS: (manufact=2047, plant=24, product=415, division=51, region=LATAM,
#            date=202610, measure=15) = 682.1536
#           (manufact=1722, plant=24, product=75,  division=53, region=LATAM,
#            date=202610, measure=15) = 66.3068
# somma = 748.4604
OPS_PRORATION_PLANT_KEY = 24
OPS_PRORATION_DATE_KEY = 202610
OPS_PRORATION_MEASURE_KEY = 15  # ASSEMBLY_HOURS_CAPACITY
OPS_PRORATION_BASE_ROWS = (
    (2047, 415, 51, "LATAM", 682.1536),
    (1722, 75, 53, "LATAM", 66.3068),
)
OPS_PRORATION_BASE_SUM = 748.4604

# Coordinate di promozione: anni/mesi lontani dal seed reale, garantiti a non
# collidere con nessuna DVERSIONS esistente (verificato: MAX(version_key)
# nel DB reale è nell'ordine delle centinaia, i cicli seedati arrivano al più
# a 2027). Ogni test usa un cycle_month diverso per restare indipendente da
# quale altro test è già girato sulla stessa copia del DB.
PROMOTION_YEAR = 2099
