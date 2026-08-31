# WPB_BIBLM_S01 — Recuperación bibliométrica desde OpenAlex

Script de extracción del pipeline WPB_BIBLM (Worlding Political Boundaries / Bibliometría). Consulta la API de [OpenAlex](https://openalex.org) a partir de un diccionario de palabras clave y exporta el corpus resultante en CSV.

## Archivos

| Archivo | Descripción |
|---|---|
| `WPB_BIBLM_S01_export.py` | Script principal (v0.91) |
| `WPB_BIBLM_S01_export.yaml` | Configuración: filtros, allow lists, campos opcionales |
| `palabras_clave_biblm.csv` | Diccionario de palabras clave con sinónimos y tipo de búsqueda |

## Requisitos

Python 3.8+ y las siguientes dependencias:

```bash
pip install requests pyyaml nltk
python -m nltk.downloader stopwords
```

## Ejecución

**macOS / Linux**
```bash
python3 WPB_BIBLM_S01_export.py --config WPB_BIBLM_S01_export.yaml
```

**Windows**
```bash
py -X utf8 WPB_BIBLM_S01_export.py --config WPB_BIBLM_S01_export.yaml
```

Agregar `--force` para sobrescribir sin confirmación (ejecución no atendida).

## Diccionario de palabras clave

El archivo `palabras_clave_biblm.csv` define qué se busca. Columnas obligatorias:

| Columna | Descripción |
|---|---|
| `keyword` | Término principal |
| `tipo_busqueda` | `search` o `search.exact` (ver abajo) |
| `nucleo` | Núcleo teórico al que pertenece (A, B, C…) |
| `sinonimo_1` … `sinonimo_10` | Términos equivalentes, opcionales |

### Cómo elegir `tipo_busqueda`

OpenAlex ofrece distintos modos de búsqueda que producen corpus de tamaños muy distintos. La elección correcta depende de la naturaleza del término.

**`search`** — búsqueda con stemming. OpenAlex reduce las palabras a su raíz para capturar variantes morfológicas: una búsqueda de "decolonial" puede devolver documentos que usan "decoloniality" o "decolonization". Internamente, los términos se encierran entre comillas para tratarlos como frases, no como palabras sueltas.

**`search.exact`** — sin stemming. Solo devuelve documentos que contengan la cadena exacta. Más restrictivo.

> Referencia: [OpenAlex — Searching](https://developers.openalex.org/guides/searching)

#### Criterios verificados (corpus FR|DE, 1960-2026)

Los resultados a continuación se obtuvieron con `WPB_BIBLM_D02_diag_busqueda.py` (2026-08-26) sobre el corpus de Francia y Alemania, período 1960-2026, tipos article/book/book-chapter/preprint.

**Términos con prefijos o sufijos críticos** — *decolonial*

El debate decolonial usa el prefijo "de-" como distanciamiento epistemológico de "colonial". Sin restricción, el stemming conecta con "colonial", "colonialism" y "colonization", que tienen una literatura masiva anterior y distinta al debate que buscamos.

| Modo | FR\|DE |
|---|---:|
| `search` sin comillas | 47.465 |
| `search` con comillas | 11.386 |
| `search.exact` | 9.891 |

→ Usar `search`. Las comillas ya delimitan el campo; el stemming moderado que queda dentro de ese campo es aceptable.

**Términos novedosos de baja frecuencia** — *conviviality*, *pluriverso*

Expresiones con poco uso fuera del debate que buscamos. El stemming no introduce ruido porque la palabra no comparte raíz con términos de otros campos.

| Modo | FR\|DE |
|---|---:|
| `search` sin comillas | 3.701 / 702 |
| `search` con comillas | 3.701 / 702 |
| `search.exact` | 1.366 / 652 |

→ Cualquier modo es válido; usar `search` por consistencia.

**Palabras con usos en otras lenguas** — *quilombo*

En portugués coloquial "quilombo" significa "lío" o "caos", uso sin relación con el debate quilombola. El stemming conecta con ese uso.

| Modo | FR\|DE |
|---|---:|
| `search` sin comillas | 129.524 |
| `search` con comillas | 1.041 |
| `search.exact` | 711 |

→ Usar `search.exact` para aislar el debate quilombola.

**Frases técnicas multipalabra** — *teoría de la dependencia*

Sin comillas, cada término ("teoría", "dependencia") compite por separado contra su alta frecuencia de uso aislada. La frase es el concepto; sus partes no lo son.

| Modo | FR\|DE |
|---|---:|
| `search` sin comillas | 38 |
| `search` con comillas | 782 |
| `search.exact` | 728 |

→ Usar `search.exact` o `search`; ambos dan resultados similares.

> **Nota sobre `search.semantic`**: OpenAlex ofrece un tercer modo que busca por similitud de embedding. En la verificación del 2026-08-26 el endpoint devolvió errores sistemáticos (504/429) y no está implementado en este pipeline. Si se declara en el CSV, el script registra un aviso y usa `search`.

## Outputs

El script escribe en el directorio configurado en `output.directorio` del YAML:

| Archivo | Contenido |
|---|---|
| `WPB_BIBLM_{iter}_v0.0.csv` | Corpus completo, un registro por documento |
| `WPB_BIBLM_{iter}_KEYWORD_{kw}.csv` | Subcorpus por palabra clave |
| `WPB_BIBLM_{iter}_NUCLEO_{X}.csv` | Subcorpus por núcleo teórico |
| `WPB_BIBLM_{iter}_CANDIDATOS_sintetizado.csv` | Términos emergentes con TF-IDF |
| `WPB_BIBLM_{iter}_ESTRATIFICACION_*.csv` | Cobertura en allow lists |
| `WPB_BIBLM_{iter}_estadisticas_basicas.txt` | Reporte de la corrida |
| `WPB_BIBLM_{iter}_S01_config_usado.yaml` | Copia de la configuración efectiva |

## Scripts de diagnóstico

| Script | Propósito |
|---|---|
| `WPB_BIBLM_D01_diag_refs.py` | Diagnostica las referencias no resueltas en la columna `referenced_works` |
| `WPB_BIBLM_D02_diag_busqueda.py` | Compara los modos de búsqueda de OpenAlex con los filtros reales del pipeline |
| `WPB_BIBLM_D03_que_busca_realmente.py` | Muestra qué parámetro de búsqueda usa S01 por cada keyword |
| `WPB_BIBLM_S01b_completar_refs.py` | Completa referencias no resueltas en un CSV existente usando `corpus=all` |

## Convenciones

- Los nombres de archivo usan guion bajo como único separador (D.5).
- Cada corrida deja una copia del YAML efectivo junto a los outputs (D.1).
- La iteración la define `metadata.iteracion` en el YAML; cambiarla genera una nueva corrida sin pisar la anterior.
- En Windows se recomienda `py -X utf8` o `set PYTHONUTF8=1` para evitar errores de codificación.
