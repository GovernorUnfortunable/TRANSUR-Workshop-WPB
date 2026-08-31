# WPB_TESIS — French Theses Analysis Pipeline

Search and exploratory analysis of doctoral theses from [theses.fr](https://theses.fr/) API. Two-stage pipeline (optional curation between stages) to build datasets of French theses and analyze temporal trends, institutional patterns, and collaboration networks.

**TRANSUR Work Package B** — Doctoral research on decolonial debates (France, 1985–2026).

## Requirements

**Python 3.8+**

Install dependencies:
```bash
pip install pandas matplotlib pyyaml requests networkx
```

`networkx` is optional; co-participation network analysis is skipped with a warning if not installed. All other analyses run normally.

## Pipeline Stages

| Stage | Input | Output | Purpose |
|-------|-------|--------|---------|
| **S01** — Search | Keywords dictionary (CSV) | Thesis candidates CSV | Query theses.fr API, export metadata |
| *(S02)* | *Manual curation* | *Validated/enriched CSV* | *(Optional: validate, link to external sources)* |
| **S03** — Analysis | S01 or S02 CSV | Tables, figures, reports | Time series, rankings, co-participation network |

**S02 is optional.** S03 automatically detects which columns are present and omits analyses for missing data.

### S01: Search in theses.fr

```bash
python3 WPB_TESIS_S01_busqueda.py --config WPB_TESIS_S01_busqueda.yaml
```

**Requires:**
- `WPB_TESIS_S01_busqueda.yaml` — Configuration (search terms, filters, output paths)
- Keyword dictionary in `entrada.diccionario` (default: internal dictionary, configurable)

**Outputs:**
- `WPB_TESIS_{iter}_candidatos.csv` — All results from API (validation state: raw)
- `WPB_TESIS_{iter}_estadisticas_basicas.txt` — Query report and statistics
- `WPB_TESIS_{iter}_S01_config_usado.yaml` — Configuration copy (trazabilidad)

**What S01 retrieves:**
- Defense date, title, abstract, subjects (keywords)
- Committee members, advisor, institution
- Jury roles: directeur, rapporteur, examinateur, président

### S03: Analysis

```bash
python3 WPB_TESIS_S03_analisis.py --config WPB_TESIS_S03_analisis.yaml
```

**Requires:** S01 or S02 CSV

**Mode control** (`entrada.modo`):
- `candidatos` — Analyze raw S01 output without validation
- `curado` — Analyze S02 output (after manual curation)

**Outputs:**
- `_informe.txt` — Full report: corpus size, rankings, network stats, data completeness
- `_serie_<concepto>.csv` — Annual time series per search term
- `_descripcion_corpus.csv` — Per-term: thesis count, year range, data status
- `_solapamiento.csv` — Cross-tabulation: theses appearing in multiple search terms
- `_concepto_<x>.png` — Individual term: theses/year (bars) + cumulative (line) + tribunal persistence
- `_comparativa.png` — All terms overlaid
- `_solapamiento.png` — Heatmap of term overlap
- `_red.png` — Co-participation network (colored by community)
- `_red.gexf` — Network in GEXF format (load in [Retina](https://retina.cortext.net/) for exploration)
- `_config_usado.yaml` — Configuration copy

**Analyses include:**
- Temporal trends: theses per year, cumulative, newcomer %
- Tribunal persistence: what fraction of committee members repeat year-to-year
- Rankings: top persons, institutions, disciplines, per-term
- Collaboration networks: co-participation in committees (Louvain communities)
- Data completeness: coverage of jury IDs, abstract availability, date formats
- Comparison vs. index: corpus representativeness in theses.fr full database

## Key Data Structures

### PPN (Pica Production Number)

Three distinct types (verify which one when reading fields):

| Where | Identifies | Example |
|-------|-----------|---------|
| `directeurs`, `rapporteurs`, `examinateurs`, `president`, `auteurs` | **Person** in IdRef authority file | `ppn=166827649` → `idref.fr/166827649` |
| `etabSoutenancePpn`, institution fields | **Institution** in IdRef | Same scheme, different registry |
| *Not in this API* | SUDOC manuscript record | Only in Aboucaya & Jasim (2026) dataset |

All metrics use **person PPNs**. This provides robust deduplication: same person, different name spellings = same PPN.

### Known Data Limits

1. **Tribunal composition missing from old records** — systematic before ~1995. Biases all jury persistence metrics toward recent years. Measured in `completitud.cobertura_ppn` per year.

2. **Name/surname reversed in records** — Not corrected in this pipeline (Aboucaya & Jasim 2026 do correct them). Always match on PPN, never on name.

3. **Defense date format: DD/MM/YYYY** — Not ISO. Script detects and reports format mismatches.

4. **Artificial peak on Jan 1** — Printed theses with only year recorded get `AAAA-01-01`. Measured in `temporal.reportar_sesgo_1_enero`; not corrected, only flagged.

5. **Abstract field has no metadata** — Not queryable via API search endpoint. Retrieved per-thesis if `entrada.recuperar_resumenes: true` (default), adds one API call per thesis.

See `WPB_TESIS_limites_campos.md` for detailed verification of every searchable field.

## Platform-Specific Instructions

### macOS / Linux

```bash
cd /path/to/project
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install pandas matplotlib pyyaml requests networkx

# Run pipeline
python3 WPB_TESIS_S01_busqueda.py --config WPB_TESIS_S01_busqueda.yaml
python3 WPB_TESIS_S03_analisis.py --config WPB_TESIS_S03_analisis.yaml
```

### Windows (PowerShell)

```powershell
cd C:\path\to\project
py -m venv .venv
.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
py -m pip install pandas matplotlib pyyaml requests networkx

# Run pipeline
py -X utf8 WPB_TESIS_S01_busqueda.py --config WPB_TESIS_S01_busqueda.yaml
py -X utf8 WPB_TESIS_S03_analisis.py --config WPB_TESIS_S03_analisis.yaml
```

`py -X utf8` required on Windows for French diacriticals.

### Flags

| Flag | Effect |
|------|--------|
| `--force` | Overwrite outputs without prompting. Declared per invocation. |
| `--config <path>` | Custom configuration file (default: matches script name) |
| `--csv <path>` | Override entry CSV. Logged and archived (rule A.5) |

Without interactive terminal and without `--force`, scripts abort rather than wait for input.

## Configuration Highlights

### S01 Search

- **Campo** — API search field: `titres.\*` (titles), `resumes.\*` (abstracts), `sujetsLibelle` (keywords), etc.
- **tipo_busqueda** — `search` (with stemming) or `search.exact` (literal phrase)
- **Filtros** — Date range, defense status, language restrictions

### S03 Analysis

- **entrada.modo** — `candidatos` (raw) or `curado` (validated)
- **colores.paleta** — Custom color scheme or auto-select from matplotlib
- **salida.formato** — PNG (default), SVG, PDF
- **Métricas** — Enable/disable specific analyses in `metricas` section
- **Red** — Co-participation network: on by default, can be disabled

## Data Source & Licensing

- **Source:** theses.fr API (Agence Bibliographique de l'Enseignement Supérieur / Abes)
- **License:** Open Licence 2.0 (Etalab) — Attribution required: *Agence bibliographique de l'enseignement supérieur*
- **Verification date:** 2026-08-29 for API field behavior
- **Contact:** S03 logs will indicate if API response format has changed since last verification

## Related Documentation

- `WPB_TESIS_S03_README.md` — Detailed metrics definitions, data limit explanations, network theory
- `WPB_TESIS_limites_campos.md` — Empirical verification of each API field's behavior (stemming, accents, phrase search)
- `WPB_TESIS_S01_busqueda.yaml`, `WPB_TESIS_S03_analisis.yaml` — Fully documented configuration files

## Notes

- Relative paths resolve against the **working directory**, not script location. Initial `cd` is not optional.
- On Windows, if project is on another drive: `D:` then `cd D:/path/to/project`.
- S03 does **not delete orphan files** from previous runs with different keyword dictionaries. Clean manually if keyword list changes.
- Network analysis (`red_total`) is slowest step; disable in `metricas` if not needed.
