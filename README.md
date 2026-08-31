# Scripts and Slides supporting TRANSUR's WPB

This repository holds three things:
1. Slides for the workshop
2. Python Script: WPB_BIBLM
3. Python Script: WPB_TESIS


# WPB-TRANSUR — Research Pipeline & Materials

**TRANSUR Work Package B** — Bibliometric and thesis analysis of decolonial academic debates.

This repository contains three components: two Python pipelines for data acquisition and analysis, plus workshop slides.

## Repository Structure

```
WPB-TRANSUR/
├── WPB_BIBLM/           Bibliometric extraction & analysis (OpenAlex)
├── WPB_TESIS/           Thesis search & network analysis (theses.fr)
└── Slides/              Workshop presentation materials
```

## Projects Overview

### WPB_BIBLM — Bibliometric Pipeline

**Extract, analyze, and visualize academic literature from OpenAlex.**

Three-stage processing: extract articles by keyword → calculate annual metrics → generate comparison graphs.

- **Scope:** France & Germany, 1960–2026
- **Source:** OpenAlex API (full-text search)
- **Output:** Time series per keyword, co-authorship networks, publication type/open access distribution

**→ See [WPB_BIBLM/README.md](./WPB_BIBLM/README.md) for usage**

### WPB_TESIS — Thesis Analysis Pipeline  

**Search French doctoral theses and analyze researcher networks.**

Two-stage processing (optional curation between): search theses.fr → exploratory analysis.

- **Scope:** France, 1985–2026
- **Source:** theses.fr API (titles, abstracts, committee metadata)
- **Output:** Time series per search term, committee co-participation network, institutional rankings

**→ See [WPB_TESIS/README.md](./WPB_TESIS/README.md) for usage**

### Slides

Workshop presentation materials.

## Python Requirements

- **Python 3.8+**
- Project-specific: see each README for `pip install` commands
- On Windows: use `py -X utf8` to avoid encoding errors with French text

## Data Sources & Attribution

| Project | Source | License | Attribution |
|---------|--------|---------|-------------|
| WPB_BIBLM | [OpenAlex](https://openalex.org) | CC0 | University of Arizona (National Science Foundation grant) |
| WPB_TESIS | [theses.fr](https://theses.fr/) | Open Licence 2.0 | Agence Bibliographique de l'Enseignement Supérieur (Abes) |

## Structure & Conventions

**One iteration per run:** Each pipeline run gets a unique identifier; outputs are never overwritten without explicit confirmation.

**Configuration travels with results:** A copy of the YAML used is saved alongside every output (trazabilidad).

**Paths are always relative:** Scripts resolve paths from the working directory, not from the script location. Always `cd` to the project folder before executing.

## Related Work

- Milia (2026). *Rewiring vs Reconfiguration in mainstream social science.* Figure 10.2 inspired the visualization framework.
- Aboucaya, W. & Jasim, D. (2026). *Doctoral theses in France (1985–2025): A linked dataset of PhDs, academic networks, and institutions.* Data in Brief, 67. — Complements WPB_TESIS with enriched metadata.
