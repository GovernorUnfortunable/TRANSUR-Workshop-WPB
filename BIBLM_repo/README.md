# WPB_BIBLM — Bibliometric Pipeline

Extraction, analysis, and visualization of academic literature from [OpenAlex](https://openalex.org). Three-stage pipeline to build bibliometric datasets for thematic research.

**TRANSUR Work Package B** — Academic circulation on decolonial debates (France & Germany, 1960–2026).

## Requirements

**Python 3.8+**

Install dependencies:
```bash
pip install requests pyyaml nltk pandas numpy matplotlib
python -m nltk.downloader stopwords
```

## Pipeline Stages

| Stage | Input | Output | Purpose |
|-------|-------|--------|---------|
| **S01** — Export | Keywords dictionary (CSV) | Full corpus + metadata | Query OpenAlex API, deduplicate, export |
| **S02** — Analysis | S01 CSV | Time series by keyword/country | Statistical metrics, co-authorship networks |
| **S03** — Visualizations | S02 CSVs | PNG/SVG/PDF figures | Individual trends, comparisons, top keywords |

**Execution order is mandatory:** S01 → S02 → S03

### S01: Export from OpenAlex

```bash
python3 WPB_BIBLM_S01_export.py --config WPB_BIBLM_S01_export.yaml
```

**Requires:**
- `WPB_BIBLM_S01_export.yaml` — Configuration (filters, allow lists, output paths)
- `palabras_clave_biblm.csv` — Keyword dictionary with synonyms

**Outputs:**
- `WPB_BIBLM_{iter}_v0.0.csv` — Main corpus (one row per document)
- `WPB_BIBLM_{iter}_KEYWORD_{kw}.csv` — Subcorpus by keyword
- `WPB_BIBLM_{iter}_NUCLEO_{X}.csv` — Subcorpus by theoretical core
- `WPB_BIBLM_{iter}_estadisticas_basicas.txt` — Execution report

### S02: Analysis

```bash
python3 WPB_BIBLM_S02_analisis.py --config WPB_BIBLM_S02_analisis.yaml
```

**Requires:** S01 output CSV

**Outputs:**
- `WPB_BIBLM_{iter}_STATS_<keyword>_<PAIS>.csv` — Annual metrics (input for S03)
- `WPB_BIBLM_{iter}_STATS_<keyword>_<PAIS>.txt` — Readable summary
- `WPB_BIBLM_{iter}_SOLAPAMIENTO_KEYWORDS.csv` — Documents in multiple keywords

**Metrics calculated:**
- Documents per year (annual, cumulative)
- Unique authors
- Document types distribution
- Open access presence (DOAJ, CORE, SciELO, OJS)
- Co-authorship networks: largest component, newcomers %

### S03: Visualizations

```bash
python3 WPB_BIBLM_S03_visualizaciones.py --config WPB_BIBLM_S03_visualizaciones.yaml
```

**Requires:** S02 output CSVs

**Outputs:** (PNG by default; configure `salida.formato` for SVG/PDF)
- `individual_<keyword>.png` — Per-keyword trends (4 metrics)
- `all_keywords_<PAIS>.png` — All keywords overlaid
- `top3_<PAIS>.png` — Top 3 keywords by cumulative documents
- `rest_<PAIS>.png` — Remaining keywords

## Key Conventions

- **One iteration per run:** Controlled by `metadata.iteracion` in S01 YAML. Changing it generates a new run without overwriting the previous one.
- **Configuration always travels with results:** A copy of the YAML used is saved with outputs (trazabilidad — rule D.1).
- **Keyword dictionary controls what gets retrieved:** `tipo_busqueda` declares the search mode (for future use); currently all queries use `search` with stemming. See `WPB_BIBLM_S01_README.md` for search strategy details.
- **API credentials (optional):** Add `api_key` and `mailto` to `filtros.api` in YAML to increase quota.

## Diagnostic Scripts

Three utilities to verify behavior:

| Script | Purpose |
|--------|---------|
| `WPB_BIBLM_D01_diag_refs.py` | Debug unresolved references in `referenced_works` |
| `WPB_BIBLM_D02_diag_busqueda.py` | Compare search modes and filter combinations |
| `WPB_BIBLM_D03_que_busca_realmente.py` | Show actual query parameters for each keyword |

Run without modifying the main scripts:
```bash
python3 WPB_BIBLM_D02_diag_busqueda.py --config WPB_BIBLM_S01_export.yaml
```

## Platform-Specific Instructions

### macOS / Linux

```bash
cd /path/to/project
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install requests pyyaml nltk pandas numpy matplotlib
python3 -m nltk.downloader stopwords

# Run pipeline
python3 WPB_BIBLM_S01_export.py --config WPB_BIBLM_S01_export.yaml
python3 WPB_BIBLM_S02_analisis.py --config WPB_BIBLM_S02_analisis.yaml
python3 WPB_BIBLM_S03_visualizaciones.py --config WPB_BIBLM_S03_visualizaciones.yaml
```

### Windows (PowerShell)

```powershell
cd C:\path\to\project
py -m venv .venv
.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
py -m pip install requests pyyaml nltk pandas numpy matplotlib
py -m nltk.downloader stopwords

# Run pipeline
py -X utf8 WPB_BIBLM_S01_export.py --config WPB_BIBLM_S01_export.yaml
py -X utf8 WPB_BIBLM_S02_analisis.py --config WPB_BIBLM_S02_analisis.yaml
py -X utf8 WPB_BIBLM_S03_visualizaciones.py --config WPB_BIBLM_S03_visualizaciones.yaml
```

`py -X utf8` is required on Windows; non-ASCII characters in the corpus will cause encoding errors otherwise.

### Flags

| Flag | Effect |
|------|--------|
| `--force` | Overwrite outputs without prompting. Declared per invocation, never inherited from environment. |
| `--config <path>` | Custom configuration file (default: matches script name) |

Without interactive terminal and without `--force`, scripts abort rather than wait for input that cannot be given.

## Data Sources & Versions

- **OpenAlex corpus:** Core works (default). Optionally expanded via `corpus=all` parameter.
- **Keyword search:** Full-text search with stemming on English/French abstracts and titles.
- **Allow lists verification:** DOAJ, CORE, SciELO, OJS (as of 2026-08).
- **Documentation reference:** Rule et al. (2019), *Ten Simple Rules for Writing and Sharing Computational Analyses in Jupyter Notebooks*. PLoS Comput Biol 15(7): e1007007.

## Related Documentation

- `WPB_BIBLM_S01_README.md` — Detailed guide to search strategies and keyword dictionary format
- `WPB_BIBLM_S02_analisis.yaml`, `WPB_BIBLM_S03_visualizaciones.yaml` — Fully documented configuration files

## Notes

- Relative paths resolve against the **working directory**, not the script location. The initial `cd` is not optional.
- On Windows, if the project is on another drive, change drives first: `D:` then `cd D:/path/to/project`.
- Logs accumulate in append mode with execution separators; check `WPB_BIBLM_{iter}_S0N_ejecucion.log` for details.
