"""
WPB_BIBLM_S01_export.py v0.91

Módulo: WPB_BIBLM — Recuperación y Análisis Bibliométrico Iterativo
Fuente: OpenAlex API
Período: 1960–2026 (editable en .YAML)
Dominios: Social Sciences (filtrado en local)

CAMBIOS v0.91
=============
Implementa tipo_busqueda (regla A.1). En todas las versiones anteriores la
columna tipo_busqueda del diccionario CSV se leía y se pasaba a
fetch_openalex(), pero la función la ignoraba: siempre usaba el parámetro
'search' con los términos entre comillas, independientemente del valor
declarado.

La nueva función preparar_busqueda() traduce el valor al parámetro y valor
que la API de OpenAlex espera:

  search       -> search=("término" OR "sinónimo 1" OR ...)
                  Con comillas: OpenAlex trata cada término como frase.
                  El stemming aplica después de las comillas.

  search.exact -> search.exact=(término OR sinónimo 1 OR ...)
                  Sin comillas ni stemming: solo coincidencias literales.

  search.semantic -> NO IMPLEMENTADO. El endpoint devolvió errores 504/429
                  sistemáticos en la verificación del 2026-08-26 con D02.
                  Se registra un WARNING y se cae a 'search'.

El log ahora indica qué parámetro se usó por keyword:
  [DEBUG] Buscando (search.exact): teoría de la dependencia (+ 6 sinonimos)

FUNDAMENTO (verificado con WPB_BIBLM_D02_diag_busqueda.py, 2026-08-26,
corpus FR|DE 1960-2026, tipos article/book/book-chapter/preprint):

  La diferencia entre modos puede ser de órdenes de magnitud. La elección
  depende de la naturaleza del término:

  - Términos que codifican su carga crítica en prefijos/sufijos ("decolonial"):
    search con comillas (11.386 FR|DE) recorta variantes morfológicas de
    "colonial" que comparten raíz pero no sentido con el debate decolonial.
    search sin comillas: 47.465.

  - Términos novedosos de baja frecuencia fuera del debate ("conviviality",
    "pluriverso"): sin comillas == con comillas. El stemming no introduce
    ruido; cualquier modo es válido.

  - Palabras con usos en otras lenguas ("quilombo" en portugués coloquial
    significa "lío"): search.exact recomendado. search sin comillas: 129.524;
    search con comillas: 1.041; search.exact: 711.

  - Frases técnicas multipalabra ("teoría de la dependencia"): search con
    comillas o search.exact. Sin comillas, cada término compite por separado:
    38 resultados vs. 782 con comillas.

  Documentación de referencia: developers.openalex.org/guides/searching.

EFECTO SOBRE DATOS YA EXPORTADOS
---------------------------------
Los CSV generados con v0.9 y anteriores usaron siempre 'search' con comillas.
Si algún keyword tiene tipo_busqueda=search.exact, el corpus para ese keyword
puede diferir al re-correr con v0.91. Hay que regenerar con la misma iteración
o una nueva para que los datos reflejen el tipo de búsqueda correcto.

CAMBIOS v0.9
============
Los cuatro salen de la corrida del 2026-08-26 con v0.8 (corpus de 5.549
documentos, 160.778 works referenciados) y del diagnóstico posterior con
WPB_BIBLM_D01_diag_refs.py.

1. EXPORTAR ANTES DE ENRIQUECER. En v0.8 la resolución de referencias corría
   antes de escribir cualquier CSV: 40 minutos de consultas con el corpus
   entero solo en memoria. Un fallo ahí —red, cuota diaria agotada, terminal
   cerrada— se llevaba también la descarga, que es la parte cara e
   irrepetible. Ahora se exporta, se resuelve, y se reexportan los tres CSV
   que contienen la columna. Escribir dos veces cuesta segundos.
   Si la resolución no devuelve nada, los CSV ya están en disco con los
   identificadores sin autor ni año, y se pueden completar después con
   WPB_BIBLM_S01b_completar_refs.py.

2. SEGUNDA PASADA CON corpus=all. OpenAlex excluye por defecto el expansion
   corpus (~190M registros de la actualización Walden, sobre todo datasets y
   registros de un solo repositorio). Las referencias que viven ahí no se
   resolvían. Ahora los pendientes de la primera pasada se reconsultan con
   corpus=all y los recuperados llevan un cuarto componente '~xpac'.
   En la corrida de referencia: 13.159 pendientes, 2.095 recuperados,
   2.047 de ellos con is_xpac=true.
   Se marcan porque OpenAlex declara menor calidad de metadatos en ese
   corpus; sin marca, las dos poblaciones quedan indistinguibles en el CSV y
   el origen no se puede reconstruir sin volver a consultar (corolario B.5).
   La marca afecta SOLO a las obras citadas: el corpus de documentos que
   recupera S01 usa el corpus por defecto y sigue siendo íntegramente core.

3. REINTENTO DE 5xx. v0.8 reintentaba ante error de red y ante 429; cualquier
   otro código caía en una rama que registraba y abandonaba el lote al primer
   intento. Un único 504 —timeout transitorio del servidor— costó 50 works.
   Ahora todo código >= 500 se reintenta con el mismo backoff exponencial.
   Regla F.1: el bloque debe capturar la condición que de hecho ocurre.

4. REFERENCIAS COLGADAS, documentadas. Tras las dos pasadas quedaron 11.064
   works (6,9%) sin resolver. Consultados de a uno responden 404: son IDs que
   ya no existen en OpenAlex. El campo referenced_works del citante no se
   actualiza cuando el citado se elimina del índice, de modo que el grafo de
   citas apunta a nodos ausentes. NO es un fallo del pipeline y no hay
   estrategia de consulta que los recupere. Conservan su ID, que sigue
   sirviendo como identificador para acoplamiento bibliográfico y cocitación.

FORMATO DE referenced_works (modo ids_author_year)
--------------------------------------------------
    W123~Smith~2019|W456~Nowak~2020~xpac|W789

    3 componentes  resuelta en el corpus core
    4 componentes  resuelta en el expansion corpus
    1 componente   ID inexistente en OpenAlex

EFECTO SOBRE DATOS YA EXPORTADOS
--------------------------------
El CSV de la corrida v0.8 no está mal: le falta el 8% de referencias que la
segunda pasada recupera, y no distingue las del expansion corpus. Caso D.6,
dato ausente y no dato incorrecto. Se completa sin re-extraer con
WPB_BIBLM_S01b_completar_refs.py, que hace la pasada de corpus=all sobre un
CSV existente y reescribe la columna en su lugar.

HISTORIAL DE VERSIONES
----------------------
Al final de este archivo, tras el bloque de ejecución.
"""

import os
import sys
import csv
import json
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
import time
import re
import math
from collections import defaultdict, Counter

import requests
import yaml

# ─────────────────────────────────────────────────────────────────────────────
# STOPWORDS — NLTK es una dependencia OBLIGATORIA (v0.5)
# ─────────────────────────────────────────────────────────────────────────────
# El diccionario de respaldo previo tenía entre 6 y 8 palabras por idioma,
# contra 157-313 del corpus NLTK. Operar con el respaldo no producía una
# degradación menor sino candidatos y TF-IDF no comparables con los de una
# corrida normal, sin que nada en los archivos de salida lo indicara.
# Se eliminó: es preferible un fallo limpio a un resultado silenciosamente
# distinto.
# ─────────────────────────────────────────────────────────────────────────────

_INSTRUCCIONES_NLTK = """
────────────────────────────────────────────────────────────────────────
ERROR: falta la dependencia NLTK, que es obligatoria.

{problema}

Para resolverlo:

  macOS / Linux:
    python3 -m pip install nltk
    python3 -m nltk.downloader stopwords

  Windows:
    py -m pip install nltk
    py -m nltk.downloader stopwords

El script no continúa sin el corpus de stopwords: sin él, la extracción de
candidatos y el TF-IDF producen resultados no comparables con los de una
corrida normal.
────────────────────────────────────────────────────────────────────────
"""

try:
    from nltk.corpus import stopwords
    STOPWORDS = {
        'es': set(stopwords.words('spanish')),
        'pt': set(stopwords.words('portuguese')),
        'en': set(stopwords.words('english')),
        'fr': set(stopwords.words('french')),
        'de': set(stopwords.words('german')),
    }
except ImportError:
    print(_INSTRUCCIONES_NLTK.format(
        problema="El paquete 'nltk' no está instalado en este entorno."
    ), file=sys.stderr)
    sys.exit(1)
except LookupError:
    print(_INSTRUCCIONES_NLTK.format(
        problema="NLTK está instalado, pero falta el corpus 'stopwords'."
    ), file=sys.stderr)
    sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════════
# MAPEO DE ALLOW LISTS
# ═════════════════════════════════════════════════════════════════════════════
# Traduce el nombre de lista usado en el YAML al nombre real del campo booleano
# dentro de primary_location.source de un Work de OpenAlex.
#
# DOCUMENTADOS (docs.openalex.org, location object):
#   is_in_doaj, is_core
# NO DOCUMENTADOS (presentes en el objeto Source; verificados empíricamente
# como presentes también en el source embebido de /works):
#   is_high_oa_rate, is_in_scielo, is_ojs
# ═════════════════════════════════════════════════════════════════════════════

ALLOW_LIST_FIELDS = {
    'doaj': 'is_in_doaj',
    'core': 'is_core',
    'high_oa_rate': 'is_high_oa_rate',
    'scielo': 'is_in_scielo',
    'ojs': 'is_ojs',
}


# ═════════════════════════════════════════════════════════════════════════════
# SETUP Y VALIDACIÓN
# ═════════════════════════════════════════════════════════════════════════════

def setup_logging(output_dir: str, iteration: int) -> logging.Logger:
    """Configura logging a consola y archivo."""
    logger = logging.getLogger('WPB_BIBLM')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    log_file = Path(output_dir) / f"WPB_BIBLM_{iteration:03d}_ejecucion.log"

    # v0.5: El FileHandler abre en modo append, de modo que corridas sucesivas
    # con la misma iteración se acumulan en el mismo archivo. Este separador
    # permite distinguir dónde empieza cada ejecución.
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, 'a', encoding='utf-8') as _f:
        _f.write("\n" + "=" * 80 + "\n")
        _f.write(f"EJECUCIÓN {ts}\n")
        _f.write("=" * 80 + "\n")

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger


def load_config(yaml_path: str) -> Dict:
    """Carga configuración desde YAML."""
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        raise FileNotFoundError(f"YAML no encontrado: {yaml_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"YAML inválido: {e}")


def validate_config(config: Dict, logger: logging.Logger) -> bool:
    """Valida parámetros YAML."""
    errors = []
    
    try:
        inicio = int(config['filtros']['periodo_inicio'])
        fin = int(config['filtros']['periodo_fin'])
        if inicio < 1960 or fin > 2026 or inicio >= fin:
            errors.append(f"Período inválido: {inicio}-{fin}")
    except (KeyError, ValueError) as e:
        errors.append(f"Período: {e}")
    
    try:
        paises = config['filtros']['paises_afiliacion']
        for p in paises:
            if len(p) != 2 or not p.isupper():
                errors.append(f"País inválido: {p}")
    except KeyError:
        errors.append("Falta paises_afiliacion")
    
    try:
        csv_path = config['diccionario_palabras_clave']
        if not Path(csv_path).exists():
            errors.append(f"CSV no encontrado: {csv_path}")
    except KeyError:
        errors.append("Falta diccionario_palabras_clave")
    
    if errors:
        for err in errors:
            logger.error(f"Validación: {err}")
        return False
    
    logger.info("Configuración YAML válida")
    return True


def detectar_separador(csv_path: str, logger: logging.Logger) -> str:
    """NUEVO v0.6: detecta el separador del CSV de palabras clave.

    Origen: un archivo con extensión .csv exportado desde una hoja de cálculo
    puede venir separado por tabulaciones o punto y coma. csv.DictReader asume
    coma y lee todo el encabezado como una sola columna, produciendo un
    KeyError opaco al pedir row['keyword'].

    La detección se registra en el log: no es una degradación silenciosa.
    """
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        primera = f.readline()

    candidatos = {',': 'coma', '\t': 'tabulación', ';': 'punto y coma'}
    conteos = {sep: primera.count(sep) for sep in candidatos}
    sep = max(conteos, key=conteos.get)

    if conteos[sep] == 0:
        logger.warning(f"No se detectó separador en {csv_path}; se asume coma")
        return ','

    if sep != ',':
        logger.warning(
            f"El archivo {csv_path} está separado por {candidatos[sep]}, no por coma. "
            f"Se procesa igual, pero conviene reexportarlo como CSV delimitado por comas."
        )
    else:
        logger.debug(f"Separador detectado en {csv_path}: coma")

    return sep


def load_keywords_csv(csv_path: str, logger: logging.Logger) -> List[Dict]:
    """Carga diccionario de palabras clave."""
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"CSV no encontrado: {csv_path}")

    sep = detectar_separador(csv_path, logger)

    keywords = []
    # utf-8-sig absorbe el BOM que agregan Excel y Numbers; con archivos sin
    # BOM se comporta igual que utf-8
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=sep)

        # Verificación explícita de columnas obligatorias
        columnas = reader.fieldnames or []
        obligatorias = ['keyword', 'tipo_busqueda', 'nucleo']
        faltantes = [c for c in obligatorias if c not in columnas]
        if faltantes:
            raise ValueError(
                f"Al archivo {csv_path} le faltan columnas obligatorias: {faltantes}\n"
                f"  Columnas encontradas: {columnas}\n"
                f"  Columnas obligatorias: {obligatorias}\n"
                f"  Opcionales: seleccionado, sinonimo_1 ... sinonimo_10\n"
                f"  Si los nombres parecen correctos, revisar que el separador "
                f"sea coma y que el archivo no tenga caracteres invisibles al inicio."
            )

        for n_fila, row in enumerate(reader, start=2):  # 2 = primera fila de datos
            if row.get('seleccionado', '1') == '0':
                continue

            if not (row.get('keyword') or '').strip():
                logger.warning(f"{csv_path} fila {n_fila}: 'keyword' vacío, se omite")
                continue

            sinonimos = [row[f'sinonimo_{i}'] for i in range(1, 11)
                        if row.get(f'sinonimo_{i}', '').strip()]
            
            keywords.append({
                'keyword': row['keyword'],
                'sinonimos': sinonimos,
                'tipo_busqueda': row['tipo_busqueda'],
                'nucleo': row['nucleo'],
            })
    
    logger.info(f"Cargados {len(keywords)} keywords")
    return keywords


# ═════════════════════════════════════════════════════════════════════════════
# VALIDACIÓN Y NORMALIZACIÓN DE RECORDS
# ═════════════════════════════════════════════════════════════════════════════

def validate_record_has_domain(raw_work: Dict) -> bool:
    """Valida que tenga primary_topic.domain."""
    try:
        domain = raw_work.get('primary_topic', {}).get('domain', {}).get('display_name')
        return domain is not None
    except (TypeError, AttributeError):
        return False


def should_include_by_domain(raw_work: Dict) -> bool:
    """Retorna True si es Social Sciences."""
    try:
        domain = raw_work.get('primary_topic', {}).get('domain', {}).get('display_name')
        return domain == 'Social Sciences'
    except (TypeError, AttributeError):
        return False


def extract_topics_with_scores(raw_work: Dict) -> str:
    """Extrae hasta 3 topics con scores."""
    topics = []
    for t in (raw_work.get('topics') or [])[:3]:
        display_name = t.get('display_name')
        score = t.get('score')
        if display_name and score is not None:
            topics.append(f"{display_name} ({score:.2f})")
    return ' | '.join(topics) if topics else ''


def extract_author_ids(raw_work: Dict) -> str:
    """Extrae OpenAlex IDs de autores."""
    ids = []
    for authorship in (raw_work.get('authorships') or []):
        author_id = authorship.get('author', {}).get('id')
        if author_id:
            ids.append(author_id)
    return '|'.join(ids) if ids else ''


def extract_author_orcids(raw_work: Dict) -> str:
    """Extrae ORCIDs de autores."""
    orcids = []
    for authorship in (raw_work.get('authorships') or []):
        orcid = authorship.get('author', {}).get('orcid')
        if orcid:
            orcids.append(orcid)
    return '|'.join(orcids) if orcids else ''


def _sanear_componente(texto: str) -> str:
    """Quita los caracteres que se usan como separadores en author_affiliations.

    Separadores: | entre autores, ; entre afiliaciones de un mismo autor,
    ~ entre autor, institucion y pais. Si alguno apareciera dentro de un nombre
    propio rompería el parseo aguas abajo, asi que se sustituye por espacio.
    """
    return str(texto or '').replace('|', ' ').replace(';', ' ').replace('~', ' ').strip()


def serializar_afiliaciones(afiliaciones: List[Dict]) -> str:
    """Serializa la anidacion autor -> instituciones a un solo campo CSV.

    Formato:  Autor~Institucion~PAIS;Autor~Institucion2~PAIS2|Autor2~Inst~PAIS
      |  separa AUTORES (un authorship de OpenAlex)
      ;  separa las AFILIACIONES de un mismo autor
      ~  une autor, institucion y country_code

    Un autor sin institucion se emite como "Autor~~" (dos campos vacios), de
    modo que el numero de bloques separados por | siempre iguala el numero de
    authorships del work.

    POR QUE ESTE CAMPO EXISTE
    -------------------------
    `authors` y `author_institutions` son dos listas planas construidas
    recorriendo todos los authorships: pierden qué institucion corresponde a
    qué autor. Con ellas no se puede distinguir "tres autores del CNRS" de "un
    autor con tres afiliaciones", que son casos distintos al contar la
    participacion institucional. Este campo conserva esa estructura.
    """
    bloques = []
    for a in afiliaciones:
        autor = _sanear_componente(a.get('author', ''))
        insts = a.get('institutions') or []
        if not insts:
            bloques.append(f"{autor}~~")
            continue
        bloques.append(';'.join(
            f"{autor}~{_sanear_componente(i.get('display_name', ''))}"
            f"~{_sanear_componente(i.get('country_code', ''))}"
            for i in insts
        ))
    return '|'.join(bloques)


def extract_institution_rors(raw_work: Dict) -> str:
    """Extrae ROR IDs de instituciones."""
    rors = set()
    for authorship in (raw_work.get('authorships') or []):
        for inst in (authorship.get('institutions') or []):
            ror = inst.get('ror')
            if ror:
                rors.add(ror)
    return '|'.join(sorted(rors)) if rors else ''


# ═════════════════════════════════════════════════════════════════════════════
# CAMPOS OPCIONALES (v0.8+)
# ═════════════════════════════════════════════════════════════════════════════

MODOS_REFERENCED_WORKS = ('ids_only', 'ids_author_year', 'count_only', 'none')
MODOS_FUNDERS = ('ids_only', 'ids_and_names', 'count_only', 'none')

# Valores por defecto de campos_opcionales: todos apagados. Un bloque ausente
# en el YAML no debe cambiar el corpus respecto de las versiones previas.
CAMPOS_OPCIONALES_DEFECTO = {
    'referenced_works': 'none',
    'funders': 'none',
    'has_content': False,
    'has_fulltext': False,
    'indexed_in': False,
}


def leer_campos_opcionales(config: Dict,
                           logger: Optional[logging.Logger] = None) -> Dict:
    """Lee y valida el bloque campos_opcionales del YAML.

    Devuelve siempre las cinco claves resueltas: los dos campos de modo como
    string, los tres booleanos como bool.

    Un valor no reconocido ABORTA (regla F.4). La versión anterior lo dejaba
    caer a un `else` que devolvía un dict vacío: pedir un modo mal escrito, o
    uno no implementado, no producía la columna ni ningún aviso.

    El logger es opcional porque normalize_record() llama a esta función una
    vez por registro y no debe emitir nada. La validación con log se hace una
    sola vez desde main(), antes de recuperar.
    """
    bloque = config.get('campos_opcionales')
    if bloque is None:
        if logger:
            logger.info("campos_opcionales no está declarado en el YAML. "
                        "Los cinco campos quedan desactivados.")
        return dict(CAMPOS_OPCIONALES_DEFECTO)
    if not isinstance(bloque, dict):
        print(f"\nERROR: campos_opcionales debe ser un mapeo, no "
              f"{type(bloque).__name__}.\n", file=sys.stderr)
        sys.exit(1)

    resuelto = {}

    for clave, validos in (('referenced_works', MODOS_REFERENCED_WORKS),
                           ('funders', MODOS_FUNDERS)):
        sub = bloque.get(clave)
        if sub is None:
            resuelto[clave] = CAMPOS_OPCIONALES_DEFECTO[clave]
            if logger:
                logger.info(f"campos_opcionales.{clave} ausente: "
                            f"se usa '{resuelto[clave]}'.")
            continue
        if not isinstance(sub, dict) or 'incluir' not in sub:
            print(f"\nERROR: campos_opcionales.{clave} debe contener una clave "
                  f"'incluir'.\n  Valores válidos: {', '.join(validos)}\n",
                  file=sys.stderr)
            sys.exit(1)
        valor = str(sub.get('incluir')).strip()
        if valor not in validos:
            print(f"\nERROR: valor no reconocido en "
                  f"campos_opcionales.{clave}.incluir\n"
                  f"  Recibido: {sub.get('incluir')!r}\n"
                  f"  Válidos:  {', '.join(validos)}\n", file=sys.stderr)
            sys.exit(1)
        resuelto[clave] = valor

    for clave in ('has_content', 'has_fulltext', 'indexed_in'):
        sub = bloque.get(clave)
        if sub is None:
            resuelto[clave] = CAMPOS_OPCIONALES_DEFECTO[clave]
            if logger:
                logger.info(f"campos_opcionales.{clave} ausente: "
                            f"se usa {resuelto[clave]}.")
            continue
        if not isinstance(sub, dict) or 'incluir' not in sub:
            print(f"\nERROR: campos_opcionales.{clave} debe contener una clave "
                  f"'incluir' con valor true o false.\n", file=sys.stderr)
            sys.exit(1)
        valor = sub.get('incluir')
        if not isinstance(valor, bool):
            print(f"\nERROR: campos_opcionales.{clave}.incluir debe ser true o "
                  f"false.\n  Recibido: {valor!r}\n", file=sys.stderr)
            sys.exit(1)
        resuelto[clave] = valor

    return resuelto

# Tope de IDs por consulta en un filtro OR de OpenAlex. La documentación da
# dos cifras según la página: 50 (blog OurResearch 2022-12-21 y tutoriales
# oficiales) y 100 (help.openalex.org, "API recipes", consultado 2026-08-26).
# Se usa 50, que es válido bajo ambas y deja la URL muy por debajo del límite
# de 4096 caracteres que documenta pyalex.
LOTE_REFS = 50

# Clave del filtro para recuperar works por su OpenAlex ID. La documentación
# NO es unívoca (regla B.2: campo documentado pero con dos formas en curso):
#   'openalex'     -> help.openalex.org, "API recipes" (2026-08-26) y
#                     docs.ropensci.org/openalexR
#   'openalex_id'  -> ropensci.github.io/openalexR, misma viñeta, otra edición
# No se pudo verificar contra la API en el entorno de desarrollo (sin salida a
# api.openalex.org). Por eso se prueban las dos en orden y se registra en el
# log cuál respondió, en lugar de asumir una (regla B.3).
CLAVES_FILTRO_ID = ('openalex', 'openalex_id')

# Cuarto componente que marca las referencias del expansion corpus (is_xpac).
# Solo afecta a las obras CITADAS: el corpus de documentos que recupera S01
# usa el corpus por defecto y es íntegramente core.
MARCA_XPAC = 'xpac'


def extract_referenced_works(raw_work: Dict, modo: str) -> Dict:
    """Extrae works referenciados según modo.

    Retorna:
        - modo='ids_only':        {'referenced_works': 'W123|W456'}
        - modo='ids_author_year': {'referenced_works': 'W123|W456'}  <- provisional
        - modo='count_only':      {'n_referenced_works': 2}
        - modo='none':            {}

    ATENCIÓN al modo ids_author_year: aquí se emiten los IDs igual que en
    ids_only. OpenAlex solo devuelve identificadores en referenced_works; el
    autor y el año no viajan en el objeto Work y hay que resolverlos con
    consultas adicionales. Esa resolución la hace resolver_referencias() en
    una pasada posterior, sobre el corpus ya filtrado, para no pagar créditos
    por registros que después se descartan.
    """
    if modo == 'none':
        return {}

    ids = [i for i in (raw_work.get('referenced_works') or []) if i]

    if modo == 'count_only':
        return {'n_referenced_works': len(ids)}
    if modo in ('ids_only', 'ids_author_year'):
        return {'referenced_works': '|'.join(ids)}
    return {}


def _id_corto(openalex_id: str) -> str:
    """https://openalex.org/W123 -> W123. Devuelve la entrada si no matchea."""
    if not isinstance(openalex_id, str):
        return ''
    m = re.search(r'(W\d+)\s*$', openalex_id.strip())
    return m.group(1) if m else openalex_id.strip()


def _resolver_lotes(lista: List[str], config: Dict, logger: logging.Logger,
                    corpus: Optional[str] = None,
                    etiqueta: str = '') -> Tuple[Dict[str, str], int]:
    """Resuelve una lista de IDs en lotes. Devuelve (cache, lotes_fallidos).

    El cache mapea id -> 'Autor~AÑO', con un cuarto componente '~xpac' cuando
    el work pertenece al expansion corpus (is_xpac).

    `corpus` es el parámetro homónimo de la API: None usa el default (core),
    'all' incluye el expansion corpus.

    v0.9: los códigos 5xx se reintentan con backoff, igual que el 429. En
    v0.8 caían en la rama genérica que registraba y abandonaba el lote al
    primer intento; la corrida del 2026-08-26 perdió así 50 works por un
    único 504, que es un timeout transitorio del servidor.
    """
    url = f"{config['api']['base_url']}/works"
    max_intentos = config['api']['reintentos']['max_intentos']
    backoff_base = config['api']['reintentos']['backoff_base']
    demora = config['api']['rate_limit_delay']

    n_consultas = -(-len(lista) // LOTE_REFS)
    cache: Dict[str, str] = {}
    lotes_fallidos = 0
    clave_filtro = None
    pref = f"[{etiqueta}] " if etiqueta else ""

    for n, inicio in enumerate(range(0, len(lista), LOTE_REFS), start=1):
        lote = lista[inicio:inicio + LOTE_REFS]

        def armar(clave: str) -> Dict:
            p = {'filter': f"{clave}:{'|'.join(lote)}",
                 'per_page': LOTE_REFS,
                 'select': 'id,publication_year,authorships,is_xpac'}
            if corpus:
                p['corpus'] = corpus
            if config['api'].get('api_key'):
                p['api_key'] = config['api']['api_key']
            if config['api'].get('mailto'):
                p['mailto'] = config['api']['mailto']
            return p

        # Primer lote: se prueban las dos claves documentadas y se fija la que
        # responda 200. Un 400 aquí significa "clave equivocada", no "fallo".
        candidatas = [clave_filtro] if clave_filtro else list(CLAVES_FILTRO_ID)

        data = None
        for clave in candidatas:
            for intento in range(max_intentos):
                try:
                    resp = requests.get(url, params=armar(clave), timeout=60)
                except requests.exceptions.RequestException as e:
                    logger.warning(f"{pref}Lote {n}/{n_consultas}, intento "
                                   f"{intento+1} falló (red): {e}")
                    time.sleep(backoff_base ** intento)
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    if clave_filtro is None:
                        clave_filtro = clave
                        logger.info(f"{pref}Clave de filtro por ID aceptada "
                                    f"por la API: '{clave}'.")
                    break

                # v0.9: 429 y 5xx son transitorios y se reintentan.
                if resp.status_code == 429 or resp.status_code >= 500:
                    espera = backoff_base ** intento
                    logger.warning(
                        f"{pref}HTTP {resp.status_code} en lote "
                        f"{n}/{n_consultas}. Esperando {espera}s "
                        f"(intento {intento+1}/{max_intentos})."
                    )
                    time.sleep(espera)
                    continue

                if resp.status_code == 400 and clave_filtro is None:
                    logger.debug(f"{pref}La API rechazó el filtro '{clave}' "
                                 f"(400). Se prueba la variante siguiente.")
                    break

                logger.error(f"{pref}Error {resp.status_code} resolviendo el "
                             f"lote {n}/{n_consultas}: {resp.text[:200]}")
                break
            if data is not None:
                break

        if data is None and clave_filtro is None and n == 1:
            logger.error(
                f"{pref}Ninguna de las claves de filtro por ID "
                f"({', '.join(CLAVES_FILTRO_ID)}) fue aceptada por la API."
            )
            return {}, n_consultas

        if data is None:
            lotes_fallidos += 1
            logger.warning(f"{pref}Lote {n}/{n_consultas} descartado tras "
                           f"agotar los reintentos ({len(lote)} works).")
            continue

        for w in (data.get('results') or []):
            corto = _id_corto(w.get('id', ''))
            if not corto:
                continue
            autorias = w.get('authorships') or []
            autor = ''
            if autorias:
                autor = (autorias[0].get('author') or {}).get('display_name') or ''
            anio = w.get('publication_year')
            valor = (f"{_sanear_componente(autor) or 's.a.'}"
                     f"~{anio if anio else 's.f.'}")
            if w.get('is_xpac') is True:
                valor += f"~{MARCA_XPAC}"
            cache[corto] = valor

        if n % 20 == 0 or n == n_consultas:
            logger.info(f"{pref}Lote {n}/{n_consultas}: "
                        f"{len(cache)}/{len(lista)} works resueltos")

        time.sleep(demora)

    return cache, lotes_fallidos


def resolver_referencias(records: List[Dict], config: Dict,
                         logger: logging.Logger) -> Dict[str, str]:
    """Resuelve autor y año de cada work referenciado en el corpus.

    Devuelve un cache {id_corto: 'Autor~AÑO'} —o 'Autor~AÑO~xpac'— que
    enriquecer_referencias() usa para reescribir la columna referenced_works.

    DOS PASADAS (v0.9)
    ------------------
    1. Corpus por defecto (core). Resuelve la enorme mayoría.
    2. Los que quedaron sin resolver, con corpus=all, que incluye el
       expansion corpus: los ~190M registros incorporados en la
       actualización Walden, sobre todo datasets y registros de un solo
       repositorio, que la API excluye por defecto.
       Los recuperados en esta pasada llevan un cuarto componente '~xpac'.
       OpenAlex declara menor calidad de metadatos en ese corpus, así que
       la marca permite separarlos al analizar en vez de enterrar la
       decisión en la extracción (corolario de B.5).

    Verificado el 2026-08-26 con WPB_BIBLM_D01_diag_refs.py: de 13.159 works
    no resueltos en la primera pasada, la segunda recuperó 2.095, de los
    cuales 2.047 con is_xpac=true.

    REFERENCIAS COLGADAS. Los 11.064 restantes de esa corrida no los devuelve
    ninguna de las dos vías, y consultados de a uno responden 404: son IDs
    que ya no existen en OpenAlex. El campo referenced_works del work citante
    no se actualiza cuando el citado se elimina del índice, así que el grafo
    de citas apunta a nodos ausentes. No hay estrategia de consulta que los
    recupere; conservan su ID sin autor ni año, que sigue sirviendo como
    identificador para acoplamiento bibliográfico y cocitación.

    COSTO. Es la única parte del pipeline que consulta OpenAlex fuera de la
    recuperación por palabra clave. Se aplican tres reducciones:
      1. Corre sobre el corpus ya filtrado, no sobre lo recuperado en bruto.
      2. Los IDs se deduplican globalmente: un work citado por cincuenta
         documentos se resuelve una sola vez.
      3. Se consultan en lotes de LOTE_REFS con el filtro OR de OpenAlex,
         no uno por uno.
    Aun así, un corpus de pocos miles de documentos puede referenciar cientos
    de miles de works distintos. El log informa el número de consultas antes
    de empezar. Las cuentas gratuitas de OpenAlex disponen de 1 USD/día.
    """
    ids_unicos = set()
    for rec in records:
        for i in str(rec.get('referenced_works') or '').split('|'):
            corto = _id_corto(i)
            if corto:
                ids_unicos.add(corto)

    if not ids_unicos:
        logger.warning(
            "referenced_works.incluir = ids_author_year, pero ningún registro "
            "del corpus tiene referencias. No se consulta la API."
        )
        return {}

    lista = sorted(ids_unicos)
    n_consultas = -(-len(lista) // LOTE_REFS)
    logger.warning(
        f"referenced_works en modo ids_author_year: {len(lista)} works "
        f"distintos por resolver en {n_consultas} consultas adicionales a "
        f"OpenAlex (lotes de {LOTE_REFS}). Consume créditos; las cuentas "
        f"gratuitas disponen de 1 USD/día."
    )

    # PASADA 1 — corpus por defecto
    cache, fallidos = _resolver_lotes(lista, config, logger,
                                      corpus=None, etiqueta='core')
    if fallidos:
        logger.warning(f"[core] {fallidos} lote(s) fallaron tras agotar los "
                       f"reintentos.")

    # PASADA 2 — los pendientes, con corpus=all
    pendientes = [i for i in lista if i not in cache]
    if pendientes:
        n2 = -(-len(pendientes) // LOTE_REFS)
        logger.info(
            f"{len(pendientes)} works sin resolver con el corpus por defecto. "
            f"Segunda pasada con corpus=all ({n2} consultas), que incluye el "
            f"expansion corpus."
        )
        cache2, fallidos2 = _resolver_lotes(pendientes, config, logger,
                                            corpus='all', etiqueta='all')
        if fallidos2:
            logger.warning(f"[all] {fallidos2} lote(s) fallaron tras agotar "
                           f"los reintentos.")
        n_xpac = sum(1 for v in cache2.values()
                     if v.endswith(f"~{MARCA_XPAC}"))
        logger.info(f"Segunda pasada: {len(cache2)} recuperados, "
                    f"{n_xpac} del expansion corpus (marcados '~{MARCA_XPAC}').")
        cache.update(cache2)

    no_resueltos = len(lista) - len(cache)
    if no_resueltos:
        logger.warning(
            f"{no_resueltos} de {len(lista)} works referenciados no se "
            f"resolvieron por ninguna de las dos vías "
            f"({100*no_resueltos/len(lista):.1f}%). Son identificadores que "
            f"ya no existen en OpenAlex (referencias colgadas: el citante no "
            f"se actualiza cuando el citado se elimina del índice). "
            f"Conservan su ID en la columna, sin autor ni año."
        )
    logger.info(f"Referencias resueltas: {len(cache)}/{len(lista)} "
                f"({100*len(cache)/len(lista):.1f}%)")
    return cache



def enriquecer_referencias(records: List[Dict], cache: Dict[str, str],
                           logger: logging.Logger) -> None:
    """Reescribe referenced_works como ID~Autor~AÑO, in place.

    Formato de salida, coherente con author_affiliations (regla B.5):
        W123~Smith~2019|W456~Nowak~2020~xpac|W789
        |  separa referencias
        ~  une id, primer autor y año

    Tres formas posibles por referencia, distinguibles por el número de
    componentes:
        3 componentes  resuelta en el corpus core
        4 componentes  resuelta en el expansion corpus (sufijo ~xpac)
        1 componente   no resuelta: el ID ya no existe en OpenAlex

    Se conserva el ID en los tres casos: sin él la referencia no es vinculable
    con nada, y sigue sirviendo como identificador para acoplamiento
    bibliográfico y cocitación aunque el nodo citado no exista.
    """
    if not cache:
        return
    resueltas = 0
    total = 0
    for rec in records:
        crudo = str(rec.get('referenced_works') or '')
        if not crudo:
            continue
        salida = []
        for i in crudo.split('|'):
            corto = _id_corto(i)
            if not corto:
                continue
            total += 1
            if corto in cache:
                salida.append(f"{corto}~{cache[corto]}")
                resueltas += 1
            else:
                salida.append(corto)
        rec['referenced_works'] = '|'.join(salida)
    logger.info(f"referenced_works enriquecido: {resueltas}/{total} menciones "
                f"con autor y año.")


def extract_funders(raw_work: Dict, modo: str) -> Dict:
    """Extrae financiadores según modo.
    
    Retorna:
        - modo='ids_only': {'funders': 'S123|S456'}
        - modo='ids_and_names': {'funders': 'S123~"NSF"|S456~"EC"'}
        - modo='count_only': {'n_funders': 2}
        - modo='none': {}
    """
    if modo == 'none':
        return {}
    
    awards = raw_work.get('awards') or []
    
    if not awards:
        if modo == 'count_only':
            return {'n_funders': 0}
        else:
            return {'funders': ''} if modo in ('ids_only', 'ids_and_names') else {}
    
    if modo == 'count_only':
        return {'n_funders': len(awards)}
    elif modo == 'ids_only':
        funder_ids = [a.get('funder_id', '') for a in awards if a.get('funder_id')]
        return {'funders': '|'.join(funder_ids) if funder_ids else ''}
    elif modo == 'ids_and_names':
        pares = []
        for award in awards:
            fid = award.get('funder_id', '')
            fname = award.get('funder_display_name', '')
            if fid and fname:
                pares.append(f'{fid}~"{fname}"')
        return {'funders': '|'.join(pares) if pares else ''}
    else:
        return {}


def extract_has_content(raw_work: Dict) -> Dict:
    """Extrae formatos de contenido disponible.
    
    Retorna: {'has_content': 'pdf|grobid_xml'} o vacío si ninguno.
    """
    has_content = raw_work.get('has_content') or {}
    formatos = []
    if has_content.get('pdf'):
        formatos.append('pdf')
    if has_content.get('grobid_xml'):
        formatos.append('grobid_xml')
    return {'has_content': '|'.join(formatos) if formatos else ''}


def extract_has_fulltext(raw_work: Dict) -> Dict:
    """Extrae booleano de fulltext disponible."""
    return {'has_fulltext': bool(raw_work.get('has_fulltext', False))}


def extract_indexed_in(raw_work: Dict) -> Dict:
    """Extrae presencia en índices como cinco booleanos.
    
    Retorna: {
        'is_indexed_in_arxiv': bool,
        'is_indexed_in_crossref': bool,
        'is_indexed_in_doaj': bool,
        'is_indexed_in_pubmed': bool,
    }
    """
    indexed = raw_work.get('indexed_in') or []
    return {
        'is_indexed_in_arxiv': 'arxiv' in indexed,
        'is_indexed_in_crossref': 'crossref' in indexed,
        'is_indexed_in_doaj': 'doaj' in indexed,
        'is_indexed_in_pubmed': 'pubmed' in indexed,
    }


def check_not_in_any_allow_list(raw_work: Dict, allow_list_fields: List[str]) -> bool:
    """Retorna True si el registro no está en NINGUNA de las allow lists dadas.

    FIX v0.5: la versión anterior recibía nombres de lista del YAML
    ('doaj', 'core') y los usaba directamente como claves del objeto source.
    Esas claves no existen en OpenAlex (los campos reales son 'is_in_doaj',
    'is_core', etc.), por lo que la función retornaba True para todo registro.
    Ahora recibe nombres de campo ya traducidos vía ALLOW_LIST_FIELDS.
    """
    source = (raw_work.get('primary_location') or {}).get('source') or {}
    for field in allow_list_fields:
        if source.get(field, False) is True:
            return False
    return True


def record_in_allow_lists(record: Dict, listas_activas: List[str]) -> bool:
    """NUEVO v0.5: True si el registro normalizado pertenece a AL MENOS UNA
    de las listas activas (OR lógico), según la Opción 3/4 del YAML.

    Si no hay listas activas, retorna True (no hay criterio que aplicar).
    """
    if not listas_activas:
        return True
    for lista in listas_activas:
        campo = ALLOW_LIST_FIELDS.get(lista)
        if campo and record.get(campo, False) is True:
            return True
    return False


def normalize_record(raw_work: Dict, allow_list_fields: List[str], 
                    keyword_origen: str = '', config: Dict = None) -> Dict:
    """Normaliza Work de OpenAlex, agregando keyword_origen y campos opcionales.

    v0.6: keyword_origen se almacena como LISTA. Un mismo documento puede ser
    recuperado por varias palabras clave; la deduplicación fusiona las listas
    en lugar de conservar solo la primera (ver deduplicate_records).
    
    v0.8: Campos opcionales parametrizables desde el YAML:
      - referenced_works (ids_only | ids_author_year | count_only | none)
      - funders (ids_only | ids_and_names | count_only | none)
      - has_content, has_fulltext, indexed_in (bool)
    """
    if config is None:
        config = {}
    authorships = raw_work.get('authorships') or []
    autores = []
    instituciones = []
    paises = []
    afiliaciones = []  # v0.7: anidacion autor -> instituciones, sin aplanar
    
    for a in authorships:
        autor = (a.get('author') or {}).get('display_name')
        if autor:
            autores.append({'display_name': autor})

        # v0.7: un authorship = UN autor con sus N instituciones. Se conserva
        # esa anidacion tal como viene de la API, sin deduplicar: la decision
        # de si un par (autor, institucion) repetido cuenta una o dos veces es
        # analitica y corresponde a S03, no a la extraccion.
        afiliaciones.append({
            'author': autor or '',
            'institutions': [
                {'display_name': inst.get('display_name', ''),
                 'country_code': inst.get('country_code') or ''}
                for inst in (a.get('institutions') or [])
                if inst.get('display_name')
            ],
        })

        for inst in (a.get('institutions') or []):
            if inst.get('display_name'):
                # v0.7: se conserva country_code EN EL MISMO dict que el nombre.
                # Antes solo se guardaba display_name y el pais se volcaba a la
                # lista plana `paises` de abajo, que en el return pasa por
                # sorted(set(...)): eso deduplica y reordena, destruyendo toda
                # correspondencia institucion<->pais. De ahi que un registro con
                # 4 instituciones exportara 3 paises.
                instituciones.append({
                    'display_name': inst['display_name'],
                    'country_code': inst.get('country_code') or '',
                })
            if inst.get('country_code'):
                paises.append(inst['country_code'])
        for c in (a.get('countries') or []):
            paises.append(c)

    ploc = raw_work.get('primary_location') or {}
    source = ploc.get('source') or {}
    
    # v0.8: Construir registro base
    record = {
        'id': raw_work.get('id', ''),
        'keyword_origen': [keyword_origen] if keyword_origen else [],  # v0.6: lista
        'title': raw_work.get('title') or raw_work.get('display_name') or '',
        'publication_year': raw_work.get('publication_year'),
        'doi': raw_work.get('doi'),
        'type': raw_work.get('type', ''),
        'language': raw_work.get('language'),
        'authors': autores,
        'author_institutions': instituciones,
        'author_affiliations': afiliaciones,  # v0.7
        'author_countries': sorted(set(paises)),
        'cited_by_count': raw_work.get('cited_by_count', 0),
        'is_open_access': (raw_work.get('open_access') or {}).get('is_oa', False),
        'primary_location_country': (sorted(set(paises)) or [''])[0],
        'disciplines': [t.get('display_name', '') for t in (raw_work.get('topics') or [])[:3]],
        'abstract': '',
        'publication_venue': source.get('display_name', 'unknown') or 'unknown',
        'canonical_url': ploc.get('landing_page_url') or raw_work.get('id', ''),
        'topics': extract_topics_with_scores(raw_work),
        'author_ids': extract_author_ids(raw_work),
        'author_orcids': extract_author_orcids(raw_work),
        'institution_rors': extract_institution_rors(raw_work),
        'not_in_any_allow_list': check_not_in_any_allow_list(raw_work, allow_list_fields),
        'is_in_doaj': bool(source.get('is_in_doaj', False)),
        'is_core': bool(source.get('is_core', False)),
        'is_high_oa_rate': bool(source.get('is_high_oa_rate', False)),
        'is_in_scielo': bool(source.get('is_in_scielo', False)),
        'is_ojs': bool(source.get('is_ojs', False)),
    }
    
    # v0.8: campos opcionales. La lectura del YAML está centralizada en
    # leer_campos_opcionales(); aquí solo se despacha.
    campos_cfg = leer_campos_opcionales(config)

    record.update(extract_referenced_works(raw_work, campos_cfg['referenced_works']))
    record.update(extract_funders(raw_work, campos_cfg['funders']))
    if campos_cfg['has_content']:
        record.update(extract_has_content(raw_work))
    if campos_cfg['has_fulltext']:
        record.update(extract_has_fulltext(raw_work))
    if campos_cfg['indexed_in']:
        record.update(extract_indexed_in(raw_work))

    return record


# ═════════════════════════════════════════════════════════════════════════════
# FETCH DE OPENALEX
# ═════════════════════════════════════════════════════════════════════════════

def preparar_busqueda(tipo_busqueda: str, terminos: List[str],
                      logger: logging.Logger) -> Tuple[str, str]:
    """Mapea tipo_busqueda a (parametro_api, valor).

    Traduce el valor de la columna tipo_busqueda del diccionario CSV al
    parámetro y valor que la API de OpenAlex espera recibir.

    VALORES VÁLIDOS
    ---------------
    search
        Búsqueda con stemming y sin stopwords. Las frases se encierran entre
        comillas para que OpenAlex las trate como expresión, no como palabras
        sueltas. El stemming aplica DESPUÉS de las comillas: "decolonial" puede
        devolver "decoloniality" y "decolonization".

        Cuándo usarlo: términos de una sola palabra o frases cuyas variantes
        morfológicas son relevantes (ej. "conviviality", "pluriverso").

    search.exact
        Búsqueda sin stemming: solo devuelve documentos que contengan la cadena
        exacta. Más restrictivo que search.

        Cuándo usarlo: frases técnicas donde cada palabra importa, o términos
        que comparten raíz con palabras de otro campo semántico. Verificado con
        D02: "teoría de la dependencia" y "buen vivir" con search.exact dan
        resultados más precisos que con search.
        También recomendado para "quilombo": sin comillas, search trae 129.524
        resultados porque la raíz matchea términos ajenos en otras lenguas;
        con search.exact el corpus baja a 711, mucho más controlado.

    VALORES NO IMPLEMENTADOS
    ------------------------
    search.semantic
        Búsqueda por similitud de embedding (GTE Large EN, 1.024 dimensiones).
        Verificado el 2026-08-26 con D02: la API devolvió errores 504 y 429
        sistemáticos, lo que indica que el endpoint está bajo carga o tiene
        cuotas distintas de los otros modos. No es implementable de forma
        confiable. Marcado como pendiente hasta que la API sea estable.
        Documentación: help.openalex.org/api/semantic-search/ (2026-08-26).

    SOBRE LA ELECCIÓN DE tipo_busqueda
    ------------------------------------
    Los resultados de D02 (2026-08-26) sobre el corpus FR|DE 1960-2026
    muestran que la diferencia entre modos puede ser de órdenes de magnitud:

      decolonial:  search sin comillas 47.465 | search con comillas 11.386
        Las comillas delimitan el debate decolonial y excluyen variantes
        morfológicas de "colonial" con las que comparte raíz pero no sentido.

      conviviality/pluriverso:  sin comillas == con comillas
        Términos novedosos con baja frecuencia fuera del debate que buscamos;
        el stemming no introduce ruido.

      quilombo:  sin comillas 129.524 | con comillas 1.041
        Palabra con usos coloquiales en otras lenguas (en portugués coloquial
        significa "lío"). El stemming conecta con ese uso. search.exact es
        el modo recomendado.

      teoría de la dependencia:  sin comillas 38 | con comillas 782
        Sin comillas, cada término compite por separado. La frase es el
        concepto; sus partes no lo son.

    Fuente: developers.openalex.org/guides/searching (2026-08-26).
    """
    VALIDOS = ('search', 'search.exact')
    NO_IMPLEMENTADOS = {'search.semantic': (
        'search.semantic no está implementado: el endpoint devolvió errores '
        '504/429 sistemáticos en la verificación del 2026-08-26. '
        'Se usa search como alternativa.'
    )}

    if tipo_busqueda in NO_IMPLEMENTADOS:
        logger.warning(
            f"tipo_busqueda='{tipo_busqueda}': {NO_IMPLEMENTADOS[tipo_busqueda]}"
        )
        tipo_busqueda = 'search'

    if tipo_busqueda not in VALIDOS:
        logger.warning(
            f"tipo_busqueda='{tipo_busqueda}' no reconocido. "
            f"Válidos: {', '.join(VALIDOS)}. Se usa 'search'."
        )
        tipo_busqueda = 'search'

    if tipo_busqueda == 'search.exact':
        # Sin comillas: search.exact busca la cadena literal sin stemming.
        valor = '(' + ' OR '.join(terminos) + ')'
    else:
        # Con comillas: OpenAlex trata cada término como frase.
        valor = '(' + ' OR '.join(f'"{t}"' for t in terminos) + ')'

    return tipo_busqueda, valor


def fetch_openalex(keyword: str, sinonimos: List[str], tipo_busqueda: str,
                   filtros: Dict, config: Dict, logger: logging.Logger) -> List[Dict]:
    """Consulta OpenAlex y retorna records con keyword_origen agregado."""
    terminos = [keyword] + sinonimos

    # v0.91: lee tipo_busqueda del diccionario CSV (regla A.1).
    # En v0.9 y anteriores se ignoraba: siempre se usaba 'search' con
    # comillas. preparar_busqueda() traduce el valor al parámetro y valor
    # que la API espera.
    param_busqueda, search_terms = preparar_busqueda(tipo_busqueda, terminos, logger)

    partes = [f"publication_year:{filtros['periodo_inicio']}-{filtros['periodo_fin']}"]

    paises = [p.strip().lower() for p in filtros.get('paises_afiliacion', []) if p.strip()]
    if paises:
        partes.append(f"institutions.country_code:{'|'.join(paises)}")

    tipos = filtros.get('tipos_documento', [])
    if tipos:
        partes.append(f"type:{'|'.join(tipos)}")

    filter_expr = ','.join(partes)

    url = f"{config['api']['base_url']}/works"
    base_params = {'per_page': config['api']['per_page']}

    base_params['filter'] = filter_expr
    base_params[param_busqueda] = search_terms
    
    if config['api'].get('api_key'):
        base_params['api_key'] = config['api']['api_key']
    if config['api'].get('mailto'):
        base_params['mailto'] = config['api']['mailto']

    logger.debug(f"Filter: {base_params['filter']}")
    logger.debug(f"Buscando ({param_busqueda}): {keyword} (+ {len(sinonimos)} sinonimos)")

    all_results = []
    cursor = '*'
    max_reg = config['api']['max_resultados_por_keyword']
    max_intentos = config['api']['reintentos']['max_intentos']
    backoff_base = config['api']['reintentos']['backoff_base']

    # v0.5: progreso por página. La paginación puede requerir hasta
    # max_resultados_por_keyword / per_page llamadas; sin estas líneas el
    # script parece congelado durante minutos.
    pagina = 0
    total_disponible = None
    intervalo_log = 5  # páginas entre cada línea de progreso

    while cursor and len(all_results) < max_reg:
        params = dict(base_params, cursor=cursor)

        for intento in range(max_intentos):
            try:
                resp = requests.get(url, params=params, timeout=60)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Intento {intento+1} falló (red): {e}")
                time.sleep(backoff_base ** intento)
                continue

            if resp.status_code == 200:
                data = resp.json()
                break
            if resp.status_code == 429:
                espera = backoff_base ** intento
                logger.warning(f"Rate limit (429). Esperando {espera}s...")
                time.sleep(espera)
                continue
            
            logger.error(f"Error {resp.status_code}: {resp.text[:400]}")
            return all_results

        if data is None:
            logger.error(f"'{keyword}': agotados los reintentos")
            break

        resultados = data.get('results', [])
        all_results.extend(resultados)
        cursor = (data.get('meta') or {}).get('next_cursor')
        pagina += 1

        # Primera página: informar cuánto hay disponible y cuántas páginas faltan
        if total_disponible is None:
            total_disponible = (data.get('meta') or {}).get('count', 0)
            a_recuperar = min(total_disponible, max_reg)
            paginas_est = max(1, -(-a_recuperar // config['api']['per_page']))
            logger.info(
                f"'{keyword}': {total_disponible} disponibles en OpenAlex, "
                f"se recuperarán {a_recuperar} (~{paginas_est} páginas)"
            )
            if total_disponible > max_reg:
                logger.warning(
                    f"'{keyword}': el techo max_resultados_por_keyword ({max_reg}) "
                    f"deja fuera {total_disponible - max_reg} registros"
                )

        # Progreso periódico
        if pagina % intervalo_log == 0:
            logger.info(f"'{keyword}': página {pagina}, "
                        f"{len(all_results)}/{min(total_disponible, max_reg)} recuperados")

        if not resultados:
            break
        time.sleep(config['api']['rate_limit_delay'])

    total = (data or {}).get('meta', {}).get('count', len(all_results))
    logger.info(f"'{keyword}': {len(all_results)} recuperados (total: {total})")
    return all_results[:max_reg]


# ═════════════════════════════════════════════════════════════════════════════
# FILTRADO, DEDUPLICACIÓN, MÉTRICAS
# ═════════════════════════════════════════════════════════════════════════════

def filter_and_normalize_records(all_raw_records: List[Dict], config: Dict,
                                 logger: logging.Logger) -> Tuple[List[Dict], int, int]:
    """Filtra por domain (Social Sciences) y normaliza.
    CRÍTICO: Ambas validaciones ANTES de normalizar.

    v0.5: NO aplica el filtro de allow lists. Ese filtro se aplica después de
    la deduplicación (ver filter_by_allow_lists), para que la estratificación
    pueda calcularse sobre el corpus completo post-dominio.
    """
    # FIX v0.5: allow_lists es un dict de dicts en el YAML; no existe una clave
    # 'incluir' a ese nivel, de modo que la versión anterior siempre caía al
    # default. La columna not_in_any_allow_list se evalúa contra las cinco listas.
    allow_list_fields = list(ALLOW_LIST_FIELDS.values())
    
    excluidos_domain = 0
    normalizados = []
    
    for raw in all_raw_records:
        # AMBAS validaciones ANTES de normalizar
        if not validate_record_has_domain(raw) or not should_include_by_domain(raw):
            excluidos_domain += 1
            continue
        
        try:
            # keyword_origen ya viene en raw desde fetch_openalex
            keyword = raw.get('_keyword_origen', '')
            normalized = normalize_record(raw, allow_list_fields, keyword, config)
            normalizados.append(normalized)
        except Exception as e:
            logger.warning(f"Error normalizando {raw.get('id', 'unknown')}: {e}")
            continue
    
    logger.info(f"Filtrados por domain: -{excluidos_domain} "
                f"({100*excluidos_domain/len(all_raw_records):.1f}% excluido)" 
                if all_raw_records else "0 registros")
    
    return normalizados, excluidos_domain, len(all_raw_records)


def deduplicate_records(records: List[Dict], logger: logging.Logger) -> Tuple[List[Dict], int]:
    """Deduplica por OpenAlex ID, FUSIONANDO keyword_origen.

    FIX v0.6: la versión anterior conservaba el primer registro y descartaba
    la copia, perdiendo con ella la palabra clave que la había recuperado.
    Un documento hallado por 'decolonial' y por 'indígena' quedaba contabilizado
    solo bajo la primera, de modo que los conteos por palabra clave estaban
    subestimados para todos los términos que comparten documentos, y el sesgo
    dependía del orden de procesamiento.

    Ahora keyword_origen acumula todas las palabras clave que recuperaron el
    documento. Los conteos por palabra clave dejan de ser mutuamente excluyentes:
    la suma de los subcorpus puede superar el tamaño del corpus.
    """
    seen = {}
    duplicates = 0
    multi_keyword = 0

    for record in records:
        oa_id = record.get('id', '')
        nuevas = record.get('keyword_origen') or []

        if oa_id in seen:
            duplicates += 1
            existentes = seen[oa_id]['keyword_origen']
            for kw in nuevas:
                if kw not in existentes:
                    existentes.append(kw)
        else:
            seen[oa_id] = record

    for rec in seen.values():
        rec['keyword_origen'] = sorted(rec.get('keyword_origen') or [])
        if len(rec['keyword_origen']) > 1:
            multi_keyword += 1

    logger.info(f"Deduplicación: {len(records)} --> {len(seen)} (eliminados {duplicates})")
    logger.info(f"Documentos recuperados por más de una palabra clave: {multi_keyword} "
                f"({100*multi_keyword/len(seen):.1f}% del corpus)" if seen else
                "Corpus vacío tras deduplicar")
    return list(seen.values()), duplicates


# ═════════════════════════════════════════════════════════════════════════════
# ALLOW LISTS: FILTRO Y ESTRATIFICACIÓN (v0.5)
# ═════════════════════════════════════════════════════════════════════════════

def get_listas_activas(config: Dict, logger: logging.Logger) -> List[str]:
    """Devuelve las allow lists marcadas incluir: true en el YAML."""
    allow_lists = config.get('allow_lists') or {}
    activas = []
    for nombre, cfg in allow_lists.items():
        if nombre not in ALLOW_LIST_FIELDS:
            logger.warning(f"Allow list desconocida en YAML, ignorada: '{nombre}'")
            continue
        if isinstance(cfg, dict) and cfg.get('incluir', False) is True:
            activas.append(nombre)
    return activas


def filter_by_allow_lists(records: List[Dict], config: Dict,
                          logger: logging.Logger) -> Tuple[List[Dict], int]:
    """NUEVO v0.5: aplica el filtro de allow lists (OR lógico, local post-fetch).

    Controlado por filtrar_por_allow_lists en el YAML:
      - false → no filtra, retorna el corpus completo
      - true  → conserva sólo registros presentes en AL MENOS UNA lista activa

    ALCANCE: el corpus resultante alimenta TODO el pipeline posterior
    (candidatos, TF-IDF, criterios A-E, exports). No es una vista de exportación.
    """
    if not config.get('filtrar_por_allow_lists', False):
        logger.info("Filtro allow lists: DESACTIVADO (se conserva el corpus completo)")
        return records, 0

    activas = get_listas_activas(config, logger)

    if not activas:
        logger.warning(
            "filtrar_por_allow_lists=true pero ninguna lista tiene incluir: true. "
            "No se aplica filtro alguno."
        )
        return records, 0

    logger.info(f"Filtro allow lists: ACTIVO — OR entre {activas}")

    # v0.7: conteo por criterio. El filtro combina las listas con OR, de modo que
    # un criterio que nunca coincide no excluye nada y pasa inadvertido: el corpus
    # queda igual que si no estuviera declarado. Registrarlo hace visible desde la
    # primera corrida cuáles criterios están operando de verdad.
    coincidencias = {
        lista: sum(1 for r in records if r.get(ALLOW_LIST_FIELDS[lista], False) is True)
        for lista in activas
    }
    detalle = ' | '.join(f"{l} {n:,}" for l, n in coincidencias.items())
    logger.info(f"Coincidencias por allow list (sobre {len(records):,} registros): {detalle}")

    en_cero = [l for l, n in coincidencias.items() if n == 0]
    if en_cero:
        logger.warning(
            f"{len(en_cero)} de {len(activas)} criterios activos no produjeron NINGUNA "
            f"coincidencia: {', '.join(en_cero)}. El corpus resultante es el mismo que "
            f"se habría obtenido sin declararlos. Puede deberse a que el campo de "
            f"OpenAlex esté vacío, o a que no viaje en el objeto source embebido en "
            f"/works, que es de donde se lee. Sin verificar contra /sources no se "
            f"puede distinguir un caso del otro."
        )

    conservados = [r for r in records if record_in_allow_lists(r, activas)]
    excluidos = len(records) - len(conservados)

    pct = 100 * excluidos / len(records) if records else 0
    logger.info(f"Filtrados por allow lists: -{excluidos} ({pct:.1f}% excluido)")

    if not conservados:
        logger.warning(
            "El filtro de allow lists dejó el corpus VACÍO. "
            "Revisar qué listas están activas en el YAML."
        )

    return conservados, excluidos


def compute_estratificacion(records: List[Dict], config: Dict,
                            logger: logging.Logger) -> Dict:
    """NUEVO v0.5: calcula la estratificación de fuentes.

    IMPORTANTE: se calcula sobre el corpus PRE-filtro de allow lists, tal como
    especifica el YAML ("las métricas SIEMPRE reportan % en TODAS las listas,
    sin importar" si el filtro está activo). Calcularla post-filtro daría 100%
    por construcción en las listas activas.
    """
    cfg = config.get('estratificacion_fuentes') or {}

    if not cfg.get('habilitado', False):
        logger.info("Estratificación de fuentes: DESACTIVADA")
        return {}

    listas = [l for l in cfg.get('incluir', []) if l in ALLOW_LIST_FIELDS]
    desconocidas = [l for l in cfg.get('incluir', []) if l not in ALLOW_LIST_FIELDS]
    for l in desconocidas:
        logger.warning(f"Estratificación: lista desconocida ignorada: '{l}'")

    if not listas:
        logger.warning("Estratificación habilitada pero sin listas válidas en 'incluir'")
        return {}

    total = len(records)

    # Nivel agregado
    agregado = {}
    for lista in listas:
        campo = ALLOW_LIST_FIELDS[lista]
        n = sum(1 for r in records if r.get(campo, False) is True)
        agregado[lista] = {'n': n, 'pct': (100 * n / total) if total else 0.0}

    # Nivel temporal (año por año)
    por_anio = defaultdict(lambda: {'total': 0, **{l: 0 for l in listas}})
    for r in records:
        anio = r.get('publication_year')
        if not anio:
            continue
        por_anio[anio]['total'] += 1
        for lista in listas:
            if r.get(ALLOW_LIST_FIELDS[lista], False) is True:
                por_anio[anio][lista] += 1

    logger.info(f"Estratificación calculada sobre {total} registros (pre-filtro), "
                f"listas: {listas}")

    return {
        'listas': listas,
        'total': total,
        'agregado': agregado,
        'temporal': dict(por_anio),
        'reportar_por': cfg.get('reportar_por', ['agregado', 'temporal']),
    }


def export_estratificacion(estrat: Dict, config: Dict, iteration: int,
                           logger: logging.Logger) -> None:
    """NUEVO v0.5: exporta la estratificación a CSV (agregado y/o temporal)."""
    if not estrat:
        return

    output_dir = Path(config['output']['directorio'])
    listas = estrat['listas']
    reportar = estrat.get('reportar_por', [])

    if 'agregado' in reportar:
        path = output_dir / f"WPB_BIBLM_{iteration:03d}_ESTRATIFICACION_agregado.csv"
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['allow_list', 'campo_openalex',
                                                   'n_registros', 'total_corpus', 'pct'])
            writer.writeheader()
            for lista in listas:
                d = estrat['agregado'][lista]
                writer.writerow({
                    'allow_list': lista,
                    'campo_openalex': ALLOW_LIST_FIELDS[lista],
                    'n_registros': d['n'],
                    'total_corpus': estrat['total'],
                    'pct': f"{d['pct']:.2f}",
                })
        logger.info(f"CSV estratificación (agregado): {path}")

    if 'temporal' in reportar:
        path = output_dir / f"WPB_BIBLM_{iteration:03d}_ESTRATIFICACION_temporal.csv"
        fieldnames = ['publication_year', 'total']
        for lista in listas:
            fieldnames += [f"n_{lista}", f"pct_{lista}"]

        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for anio in sorted(estrat['temporal'].keys()):
                d = estrat['temporal'][anio]
                fila = {'publication_year': anio, 'total': d['total']}
                for lista in listas:
                    n = d[lista]
                    fila[f"n_{lista}"] = n
                    fila[f"pct_{lista}"] = f"{100 * n / d['total']:.2f}" if d['total'] else "0.00"
                writer.writerow(fila)
        logger.info(f"CSV estratificación (temporal): {path}")


def extract_candidates(records: List[Dict], config: Dict, 
                      logger: logging.Logger) -> Dict:
    """Extrae candidatos con tracking de allow lists."""
    candidates = defaultdict(lambda: {
        'freq_total': 0,
        'freq_autor': defaultdict(int),
        'freq_fuente': defaultdict(int),
        'freq_institucion': defaultdict(int),
        'freq_anual': defaultdict(int),
        'anos_activos': set(),
        'menciones_doaj': 0,
        'menciones_core': 0,
        'menciones_scielo': 0,
        'menciones_ojs': 0,
        'menciones_high_oa': 0,
    })
    
    stopwords_all = set()
    for lang_stops in STOPWORDS.values():
        stopwords_all.update(lang_stops)
    
    for record in records:
        titulo = record.get('title', '').lower()
        texto = re.sub(r'[^\w\s]', ' ', titulo)
        tokens = [t for t in texto.split() if t and t not in stopwords_all]
        
        if not tokens:
            continue
        
        autores = record.get('authors', [])
        author = autores[0].get('display_name', 'unknown') if autores else 'unknown'
        fuente = record.get('publication_venue', 'unknown')
        insts = record.get('author_institutions', [])
        institucion = insts[0].get('display_name', 'unknown') if insts else 'unknown'
        year = record.get('publication_year')
        
        # Allow lists
        doaj = record.get('is_in_doaj', False)
        core = record.get('is_core', False)
        scielo = record.get('is_in_scielo', False)
        ojs = record.get('is_ojs', False)
        high_oa = record.get('is_high_oa_rate', False)
        
        for token in tokens:
            candidates[token]['freq_total'] += 1
            candidates[token]['freq_autor'][author] += 1
            candidates[token]['freq_fuente'][fuente] += 1
            candidates[token]['freq_institucion'][institucion] += 1
            if year:
                candidates[token]['freq_anual'][year] += 1
                candidates[token]['anos_activos'].add(year)
            
            # Allow lists (conteo múltiple permitido)
            if doaj:
                candidates[token]['menciones_doaj'] += 1
            if core:
                candidates[token]['menciones_core'] += 1
            if scielo:
                candidates[token]['menciones_scielo'] += 1
            if ojs:
                candidates[token]['menciones_ojs'] += 1
            if high_oa:
                candidates[token]['menciones_high_oa'] += 1
        
        if config['extraccion_candidatos']['bigramas']['incluir']:
            for i in range(len(tokens) - 1):
                bigrama = f"{tokens[i]} {tokens[i+1]}"
                candidates[bigrama]['freq_total'] += 1
                candidates[bigrama]['freq_autor'][author] += 1
                candidates[bigrama]['freq_fuente'][fuente] += 1
                candidates[bigrama]['freq_institucion'][institucion] += 1
                if year:
                    candidates[bigrama]['freq_anual'][year] += 1
                    candidates[bigrama]['anos_activos'].add(year)
                
                if doaj:
                    candidates[bigrama]['menciones_doaj'] += 1
                if core:
                    candidates[bigrama]['menciones_core'] += 1
                if scielo:
                    candidates[bigrama]['menciones_scielo'] += 1
                if ojs:
                    candidates[bigrama]['menciones_ojs'] += 1
                if high_oa:
                    candidates[bigrama]['menciones_high_oa'] += 1
    
    logger.info(f"Candidatos extraídos: {len(candidates)}")
    return candidates


def evaluate_criteria(candidates: Dict, config: Dict, 
                     logger: logging.Logger) -> Dict:
    """Evalúa candidatos contra criterios."""
    criteria_config = config['criterios_candidatos']
    evaluated = {}
    
    for term, freq_data in candidates.items():
        criterios = []
        
        if criteria_config['criterio_a_autor']['habilitado']:
            max_author = max(freq_data['freq_autor'].values()) if freq_data['freq_autor'] else 0
            if max_author >= criteria_config['criterio_a_autor']['umbral']:
                criterios.append('A')
        
        if criteria_config['criterio_b_fuente']['habilitado']:
            max_source = max(freq_data['freq_fuente'].values()) if freq_data['freq_fuente'] else 0
            if max_source >= criteria_config['criterio_b_fuente']['umbral']:
                criterios.append('B')
        
        if criteria_config['criterio_c_institucion']['habilitado']:
            max_inst = max(freq_data['freq_institucion'].values()) if freq_data['freq_institucion'] else 0
            if max_inst >= criteria_config['criterio_c_institucion']['umbral']:
                criterios.append('C')
        
        if criteria_config['criterio_d_anual']['habilitado']:
            max_year = max(freq_data['freq_anual'].values()) if freq_data['freq_anual'] else 0
            if max_year >= criteria_config['criterio_d_anual']['umbral']:
                criterios.append('D')
        
        if criteria_config['criterio_e_pais_temporal']['habilitado']:
            anos = sorted(freq_data['anos_activos'])
            if len(anos) >= criteria_config['criterio_e_pais_temporal']['umbral']:
                criterios.append('E')
        
        if criterios:
            total_menciones = freq_data['freq_total']
            evaluated[term] = {
                'freq_total': total_menciones,
                'max_author_freq': max(freq_data['freq_autor'].values()) if freq_data['freq_autor'] else 0,
                'max_source_freq': max(freq_data['freq_fuente'].values()) if freq_data['freq_fuente'] else 0,
                'max_inst_freq': max(freq_data['freq_institucion'].values()) if freq_data['freq_institucion'] else 0,
                'max_year_freq': max(freq_data['freq_anual'].values()) if freq_data['freq_anual'] else 0,
                'periodo_uso': f"{min(freq_data['anos_activos'])}-{max(freq_data['anos_activos'])}" 
                    if freq_data['anos_activos'] else 'unknown',
                'criterios_cumplidos': '|'.join(sorted(criterios)),
                # NUEVO v0.4: Allow lists
                'pct_en_doaj': f"{100*freq_data['menciones_doaj']/total_menciones:.1f}%" if total_menciones else "0%",
                'pct_en_core': f"{100*freq_data['menciones_core']/total_menciones:.1f}%" if total_menciones else "0%",
                'pct_en_scielo': f"{100*freq_data['menciones_scielo']/total_menciones:.1f}%" if total_menciones else "0%",
                'pct_en_ojs': f"{100*freq_data['menciones_ojs']/total_menciones:.1f}%" if total_menciones else "0%",
                'pct_high_oa': f"{100*freq_data['menciones_high_oa']/total_menciones:.1f}%" if total_menciones else "0%",
            }
    
    logger.info(f"Candidatos evaluados: {len(evaluated)}")
    return evaluated


def calculate_tfidf(records: List[Dict], candidates_eval: Dict,
                   logger: logging.Logger) -> Dict:
    """Calcula TF-IDF para cada candidato.
    
    TF = frecuencia del término en el documento / total de términos
    IDF = log(total documentos / documentos contienen término)
    TF-IDF = TF × IDF
    """
    tfidf_scores = {}
    total_docs = len(records)
    
    if total_docs == 0:
        return tfidf_scores
    
    # Para cada término, contar documentos que lo mencionan
    docs_with_term = defaultdict(int)
    doc_tokens = {}
    
    for doc in records:
        titulo = doc.get('title', '').lower()
        texto = re.sub(r'[^\w\s]', ' ', titulo)
        tokens = [t for t in texto.split() if t]
        
        unique_tokens = set(tokens)
        for token in unique_tokens:
            if token in candidates_eval:
                docs_with_term[token] += 1
        
        doc_tokens[doc['id']] = tokens
    
    # Calcular TF-IDF para cada candidato
    for term in candidates_eval.keys():
        if term not in docs_with_term:
            tfidf_scores[term] = 0.0
            continue
        
        # IDF
        idf = math.log(total_docs / (docs_with_term[term] + 1))
        
        # Promediar TF-IDF sobre todos los documentos que contienen el término
        tf_idf_sum = 0.0
        count = 0
        
        for doc in records:
            tokens = doc_tokens.get(doc['id'], [])
            if term not in tokens:
                continue
            
            # TF para este documento
            tf = tokens.count(term) / len(tokens) if len(tokens) > 0 else 0
            tf_idf = tf * idf
            tf_idf_sum += tf_idf
            count += 1
        
        tfidf_scores[term] = tf_idf_sum / count if count > 0 else 0.0
    
    logger.info(f"TF-IDF calculado para {len(tfidf_scores)} términos")
    return tfidf_scores


# ═════════════════════════════════════════════════════════════════════════════
# EXPORTACIÓN
# ═════════════════════════════════════════════════════════════════════════════

def columnas_opcionales(campos_opt: Dict) -> List[str]:
    """Nombres de las columnas opcionales activas, en orden fijo.

    v0.8. Las listas de fieldnames de los exportadores son literales; sin esta
    función, activar un campo en el YAML lo agregaría al registro normalizado
    pero nunca al CSV (regla A.1: parámetro leído sin efecto observable).
    Los tres exportadores de corpus usan la misma lista, para que la misma
    información no se exporte distinto según el archivo (regla G.4).
    """
    cols = []
    modo_refs = campos_opt.get('referenced_works', 'none')
    if modo_refs == 'count_only':
        cols.append('n_referenced_works')
    elif modo_refs in ('ids_only', 'ids_author_year'):
        cols.append('referenced_works')

    modo_fund = campos_opt.get('funders', 'none')
    if modo_fund == 'count_only':
        cols.append('n_funders')
    elif modo_fund in ('ids_only', 'ids_and_names'):
        cols.append('funders')

    if campos_opt.get('has_content'):
        cols.append('has_content')
    if campos_opt.get('has_fulltext'):
        cols.append('has_fulltext')
    if campos_opt.get('indexed_in'):
        cols += ['is_indexed_in_arxiv', 'is_indexed_in_crossref',
                 'is_indexed_in_doaj', 'is_indexed_in_pubmed']
    return cols


def valores_opcionales(rec: Dict, cols: List[str]) -> Dict:
    """Valores de las columnas opcionales para un registro.

    Los campos opcionales ya vienen serializados desde normalize_record(); aquí
    solo se seleccionan. El default '' cubre el registro que no pasó por
    normalize_record() con la misma configuración.
    """
    return {c: rec.get(c, '') for c in cols}


def export_csv_principal(records: List[Dict], config: Dict, iteration: int,
                        logger: logging.Logger) -> Path:
    """Exporta CSV principal con todas las columnas."""
    output_dir = Path(config['output']['directorio'])
    output_dir.mkdir(parents=True, exist_ok=True)
    
    version = f"{config['metadata'].get('iteracion', 0)}.0"
    csv_path = output_dir / f"WPB_BIBLM_{iteration:03d}_v{version}.csv"
    
    fieldnames = [
        'openalex_id', 'keyword_origen',  # NUEVO: keyword_origen
        'title', 'publication_year', 'doi', 'type',
        'authors', 'author_institutions', 'author_affiliations', 'author_countries',
        'cited_by_count', 'is_open_access',
        'primary_location_country', 'disciplines',
        'publication_venue', 'url',
        'topics', 'author_ids', 'author_orcids', 'institution_rors',
        'not_in_any_allow_list',
        'is_in_doaj', 'is_core', 'is_high_oa_rate', 'is_in_scielo', 'is_ojs'
    ]

    # v0.8: columnas opcionales, al final para no alterar el orden previo
    cols_opt = columnas_opcionales(leer_campos_opcionales(config))
    fieldnames = fieldnames + cols_opt

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            try:
                writer.writerow({
                    'openalex_id': rec.get('id', ''),
                    'keyword_origen': '|'.join(rec.get('keyword_origen') or []),
                    'title': rec.get('title', ''),
                    'publication_year': rec.get('publication_year', ''),
                    'doi': rec.get('doi', ''),
                    'type': rec.get('type', ''),
                    'authors': '|'.join([a.get('display_name', '') for a in rec.get('authors', [])]),
                    # v0.7: formato "Nombre~XX", donde XX es el country_code de
                    # ESA institucion. El par viaja junto y no puede desalinearse.
                    # Si OpenAlex no da country_code, queda "Nombre~" (vacio).
                    # Separador entre instituciones: |  ; entre nombre y pais: ~
                    'author_institutions': '|'.join([
                        f"{i.get('display_name', '')}~{i.get('country_code', '')}"
                        for i in rec.get('author_institutions', [])
                    ]),
                    'author_affiliations': serializar_afiliaciones(rec.get('author_affiliations', [])),
                    'author_countries': '|'.join(rec.get('author_countries', [])),
                    'cited_by_count': rec.get('cited_by_count', ''),
                    'is_open_access': rec.get('is_open_access', ''),
                    'primary_location_country': rec.get('primary_location_country', ''),
                    'disciplines': '|'.join(rec.get('disciplines', [])),
                    'publication_venue': rec.get('publication_venue', ''),
                    'url': rec.get('canonical_url', ''),
                    'topics': rec.get('topics', ''),
                    'author_ids': rec.get('author_ids', ''),
                    'author_orcids': rec.get('author_orcids', ''),
                    'institution_rors': rec.get('institution_rors', ''),
                    'not_in_any_allow_list': rec.get('not_in_any_allow_list', ''),
                    'is_in_doaj': rec.get('is_in_doaj', False),
                    'is_core': rec.get('is_core', False),
                    'is_high_oa_rate': rec.get('is_high_oa_rate', False),
                    'is_in_scielo': rec.get('is_in_scielo', False),
                    'is_ojs': rec.get('is_ojs', False),
                    **valores_opcionales(rec, cols_opt),
                })
            except Exception as e:
                logger.warning(f"Error escribiendo {rec.get('id', 'unknown')}: {e}")
    
    logger.info(f"CSV principal: {csv_path}")
    if cols_opt:
        logger.info(f"Columnas opcionales exportadas: {', '.join(cols_opt)}")
    return csv_path


def export_by_keyword(records: List[Dict], keywords: List[Dict], config: Dict, 
                     iteration: int, logger: logging.Logger) -> None:
    """NUEVO v0.4: Exporta CSV y listado de IDs POR CADA KEYWORD."""
    output_dir = Path(config['output']['directorio'])
    version = f"{config['metadata'].get('iteracion', 0)}.0"
    cols_opt = columnas_opcionales(leer_campos_opcionales(config))  # v0.8
    
    # Agrupar registros por keyword_origen
    # v0.6: keyword_origen es una lista. Un documento recuperado por varias
    # palabras clave entra en el CSV de CADA una. Los subcorpus dejan de ser
    # mutuamente excluyentes: su suma puede superar el tamaño del corpus.
    by_keyword = defaultdict(list)
    for rec in records:
        for kw in (rec.get('keyword_origen') or ['unknown']):
            by_keyword[kw].append(rec)
    
    for kw_data in keywords:
        keyword = kw_data['keyword']
        if keyword not in by_keyword:
            continue
        
        records_for_kw = by_keyword[keyword]
        
        # CSV por keyword
        csv_path = output_dir / f"WPB_BIBLM_{iteration:03d}_KEYWORD_{keyword.replace(' ', '_').lower()}.csv"
        # v0.5: agregadas is_high_oa_rate, is_in_scielo, is_ojs para igualar
        # la información de allow lists del CSV principal
        fieldnames = ['openalex_id', 'title', 'publication_year', 'type', 'authors', 
                     'publication_venue', 'is_in_doaj', 'is_core',
                     'is_high_oa_rate', 'is_in_scielo', 'is_ojs'] + cols_opt

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in records_for_kw:
                writer.writerow({
                    'openalex_id': rec.get('id', ''),
                    'title': rec.get('title', ''),
                    'publication_year': rec.get('publication_year', ''),
                    'type': rec.get('type', ''),
                    'authors': '|'.join([a.get('display_name', '') for a in rec.get('authors', [])]),
                    'publication_venue': rec.get('publication_venue', ''),
                    'is_in_doaj': rec.get('is_in_doaj', False),
                    'is_core': rec.get('is_core', False),
                    'is_high_oa_rate': rec.get('is_high_oa_rate', False),
                    'is_in_scielo': rec.get('is_in_scielo', False),
                    'is_ojs': rec.get('is_ojs', False),
                    **valores_opcionales(rec, cols_opt),
                })
        
        # Listado de IDs por keyword
        ids_path = output_dir / f"WPB_BIBLM_{iteration:03d}_IDS_KEYWORD_{keyword.replace(' ', '_').lower()}.txt"
        with open(ids_path, 'w', encoding='utf-8') as f:
            for rec in records_for_kw:
                f.write(f"{rec.get('id', '')}\n")
        
        logger.info(f"Keyword '{keyword}': {len(records_for_kw)} registros")


def export_by_nucleo(records: List[Dict], keywords: List[Dict], config: Dict,
                    iteration: int, logger: logging.Logger) -> None:
    """NUEVO v0.4: Exporta CSV y IDs POR NÚCLEO TEÓRICO (A, B, C)."""
    output_dir = Path(config['output']['directorio'])
    version = f"{config['metadata'].get('iteracion', 0)}.0"
    cols_opt = columnas_opcionales(leer_campos_opcionales(config))  # v0.8

    # Mapeo keyword → núcleo
    keyword_to_nucleo = {kw['keyword']: kw['nucleo'] for kw in keywords}
    
    # Agrupar por núcleo
    # v0.6: un documento puede provenir de palabras clave de núcleos distintos;
    # entra en cada núcleo involucrado, pero una sola vez por núcleo.
    by_nucleo = defaultdict(list)
    for rec in records:
        nucleos = {keyword_to_nucleo.get(kw, 'unknown')
                   for kw in (rec.get('keyword_origen') or ['unknown'])}
        for nucleo in nucleos:
            by_nucleo[nucleo].append(rec)
    
    for nucleo in sorted(by_nucleo.keys()):
        records_for_nucleo = by_nucleo[nucleo]
        
        # CSV por núcleo
        csv_path = output_dir / f"WPB_BIBLM_{iteration:03d}_NUCLEO_{nucleo}.csv"
        fieldnames = ['openalex_id', 'keyword_origen', 'title',
                      'publication_year', 'type'] + cols_opt

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in records_for_nucleo:
                writer.writerow({
                    'openalex_id': rec.get('id', ''),
                    'keyword_origen': '|'.join(rec.get('keyword_origen') or []),
                    'title': rec.get('title', ''),
                    'publication_year': rec.get('publication_year', ''),
                    'type': rec.get('type', ''),
                    **valores_opcionales(rec, cols_opt),
                })
        
        logger.info(f"Núcleo '{nucleo}': {len(records_for_nucleo)} registros")


def export_candidates_csv(candidates_eval: Dict, tfidf_scores: Dict, 
                         config: Dict, iteration: int,
                         logger: logging.Logger) -> Path:
    """NUEVO v0.4: Exporta candidatos CON TF-IDF y % allow lists."""
    output_dir = Path(config['output']['directorio'])
    version = f"{config['metadata'].get('iteracion', 0)}.0"
    csv_path = output_dir / f"WPB_BIBLM_{iteration:03d}_CANDIDATOS_sintetizado.csv"
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['termino', 'tipo', 'freq_total', 'tfidf', 'periodo_uso', 
                     'pct_doaj', 'pct_core', 'pct_scielo', 'pct_ojs', 'pct_high_oa',
                     'criterios_cumplidos', 'seleccionar']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for term, data in sorted(candidates_eval.items(), key=lambda x: x[1]['freq_total'], reverse=True):
            writer.writerow({
                'termino': term,
                'tipo': 'unigrama' if ' ' not in term else 'bigrama',
                'freq_total': data['freq_total'],
                'tfidf': f"{tfidf_scores.get(term, 0.0):.4f}",
                'periodo_uso': data['periodo_uso'],
                'pct_doaj': data['pct_en_doaj'],
                'pct_core': data['pct_en_core'],
                'pct_scielo': data['pct_en_scielo'],
                'pct_ojs': data['pct_en_ojs'],
                'pct_high_oa': data['pct_high_oa'],
                'criterios_cumplidos': data['criterios_cumplidos'],
                'seleccionar': '',
            })
    
    logger.info(f"CSV candidatos: {csv_path}")
    return csv_path


def generate_report(records: List[Dict], iteration: int, duplicates: int, 
                   excluidos_domain: int, total_input: int, config: Dict,
                   logger: logging.Logger,
                   excluidos_allow_lists: int = 0,
                   listas_activas: Optional[List[str]] = None) -> Path:
    """Genera reporte de ejecución."""
    output_dir = Path(config['output']['directorio'])
    version = f"{config['metadata'].get('iteracion', 0)}.0"
    report_path = output_dir / f"WPB_BIBLM_{iteration:03d}_estadisticas_basicas.txt"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"ESTADÍSTICAS WPB_BIBLM v{version}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Total recuperados: {total_input}\n")
        f.write(f"Excluidos domain: {excluidos_domain}\n")
        f.write(f"Duplicados eliminados: {duplicates}\n")

        # v0.5: trazabilidad del filtro de allow lists
        if config.get('filtrar_por_allow_lists', False):
            activas = listas_activas or []
            f.write(f"Filtro allow lists: ACTIVO (OR entre {activas})\n")
            f.write(f"Excluidos por allow lists: {excluidos_allow_lists}\n")
        else:
            f.write("Filtro allow lists: DESACTIVADO\n")

        f.write(f"Registros en corpus final: {len(records)}\n\n")
        
        f.write("DISTRIBUCIÓN GEOGRÁFICA:\n")
        countries = defaultdict(int)
        for rec in records:
            c = rec.get('primary_location_country', 'unknown')
            countries[c] += 1
        
        for country, count in sorted(countries.items(), key=lambda x: x[1], reverse=True):
            pct = 100 * count / len(records) if len(records) > 0 else 0
            f.write(f"  {country}: {count} ({pct:.1f}%)\n")
    
    logger.info(f"Reporte: {report_path}")
    return report_path


# ═════════════════════════════════════════════════════════════════════════════
# PROTECCIÓN CONTRA SOBRESCRITURA (v0.5)
# ═════════════════════════════════════════════════════════════════════════════

def confirmar_sobrescritura(output_dir: str, iteration: int, force: bool) -> None:
    """NUEVO v0.5: pide confirmación si ya existen exports de esta iteración.

    Los nombres de archivo derivan de metadata.iteracion y se abren en modo 'w',
    de modo que reejecutar con la misma iteración PISA los resultados previos.

    Se ejecuta ANTES de setup_logging para que el propio archivo de log no
    dispare el aviso. Por eso usa print() y no el logger.
    """
    directorio = Path(output_dir)
    if not directorio.exists():
        return

    prefijo = f"WPB_BIBLM_{iteration:03d}_"
    existentes = sorted(p.name for p in directorio.glob(prefijo + "*"))

    if not existentes:
        return

    print("\n" + "=" * 78)
    print(f"AVISO: ya existen exportaciones de la iteración {iteration} en '{output_dir}/'")
    print("=" * 78)
    for nombre in existentes:
        print(f"  - {nombre}")
    print("=" * 78)
    print("Continuar SOBRESCRIBE estos archivos. Los datos anteriores se pierden")
    print("y no se pueden recuperar.")
    print("Para conservarlos, abortar y subir 'metadata.iteracion' en el YAML.")
    print("=" * 78)

    if force:
        print("--force activo: se sobrescribe sin confirmación.\n")
        return

    if not sys.stdin.isatty():
        print("\nERROR: no hay terminal interactiva para confirmar (notebook, cron,")
        print("pipeline). Ejecución abortada; no se modificó ningún archivo.")
        print("Usar --force para sobrescribir de forma no atendida.\n")
        sys.exit(1)

    respuesta = input("¿Sobrescribir? [s/N]: ").strip().lower()
    if respuesta not in ('s', 'si', 'sí'):
        print("Ejecución abortada. No se modificó ningún archivo.\n")
        sys.exit(0)
    print()


def volcar_config_usado(yaml_path: str, output_dir: str, iteration: int,
                        logger: logging.Logger) -> None:
    """NUEVO v0.5: copia el YAML efectivo junto a los outputs (trazabilidad).

    Permite reconstruir con qué parámetros se generó cada corrida, aunque el
    YAML original se edite después.
    """
    destino = Path(output_dir) / f"WPB_BIBLM_{iteration:03d}_config_usado.yaml"
    try:
        shutil.copy(yaml_path, destino)
        logger.info(f"Config usado: {destino}")
    except Exception as e:
        logger.warning(f"No se pudo copiar el YAML usado: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    """Función principal."""
    parser = argparse.ArgumentParser(description='WPB_BIBLM S01 v0.7')
    parser.add_argument('--config', required=True, help='Ruta a YAML')
    parser.add_argument('--force', action='store_true',
                        help='Sobrescribe exportaciones previas sin pedir '
                             'confirmación (ejecución no atendida)')
    args = parser.parse_args()
    
    config = load_config(args.config)
    iteration = config['metadata'].get('iteracion', 0)

    # v0.5: confirmación ANTES de crear el log, para que el propio archivo de
    # log no dispare el aviso de sobrescritura
    confirmar_sobrescritura(config['output']['directorio'], iteration, args.force)
    
    logger = setup_logging(config['output']['directorio'], iteration)
    logger.info("=" * 80)
    logger.info(f"WPB_BIBLM S01 v0.91 iniciado (iteración {iteration})")
    logger.info("=" * 80)

    volcar_config_usado(args.config, config['output']['directorio'], iteration, logger)
    
    if not validate_config(config, logger):
        logger.error("Configuración inválida.")
        sys.exit(1)

    # v0.8: se valida ANTES de recuperar. Un modo mal escrito debe abortar en
    # el segundo cero, no después de descargar el corpus completo.
    campos_opt = leer_campos_opcionales(config, logger)
    activos = [f"{k}={v}" for k, v in campos_opt.items()
               if v not in (False, 'none')]
    logger.info("Campos opcionales activos: "
                + (', '.join(activos) if activos else "ninguno"))
    
    try:
        keywords = load_keywords_csv(config['diccionario_palabras_clave'], logger)
    except Exception as e:
        logger.error(f"Error cargando keywords: {e}")
        sys.exit(1)
    
    # RECUPERACIÓN CON TRACKING
    all_raw_records = []
    for kw_data in keywords:
        records = fetch_openalex(
            kw_data['keyword'],
            kw_data['sinonimos'],
            kw_data['tipo_busqueda'],
            config['filtros'],
            config,
            logger
        )
        # Agregar keyword_origen a cada record
        for rec in records:
            rec['_keyword_origen'] = kw_data['keyword']
        all_raw_records.extend(records)
    
    logger.info(f"Total recuperados (sin filtro): {len(all_raw_records)}")
    
    # FILTRADO Y NORMALIZACIÓN
    normalized_records, excluidos_domain, total_input = filter_and_normalize_records(
        all_raw_records, config, logger
    )
    
    # DEDUPLICACIÓN
    unique_records, duplicates = deduplicate_records(normalized_records, logger)

    # ESTRATIFICACIÓN (v0.5) — sobre el corpus PRE-filtro de allow lists
    estrat = compute_estratificacion(unique_records, config, logger)

    # FILTRO POR ALLOW LISTS (v0.5) — redefine el corpus de análisis
    corpus, excluidos_allow_lists = filter_by_allow_lists(unique_records, config, logger)
    listas_activas = get_listas_activas(config, logger) \
        if config.get('filtrar_por_allow_lists', False) else []

    if not corpus:
        logger.error("Corpus vacío tras el filtrado. No hay nada que exportar.")
        sys.exit(1)

    # EXTRACCIÓN Y EVALUACIÓN
    candidates = extract_candidates(corpus, config, logger)
    candidates_eval = evaluate_criteria(candidates, config, logger)

    # TF-IDF
    tfidf_scores = calculate_tfidf(corpus, candidates_eval, logger)

    # EXPORTACIÓN
    # v0.9: se exporta ANTES de resolver referencias. En v0.8 la resolución
    # corría antes de escribir nada: 40 minutos de consultas con el corpus
    # entero solo en memoria, de modo que cualquier fallo ahí —red, cuota
    # diaria agotada, terminal cerrada— se llevaba también la descarga, que
    # es la parte cara e irrepetible. Escribir dos veces cuesta segundos.
    export_csv_principal(corpus, config, iteration, logger)
    export_by_keyword(corpus, keywords, config, iteration, logger)
    export_by_nucleo(corpus, keywords, config, iteration, logger)
    export_candidates_csv(candidates_eval, tfidf_scores, config, iteration, logger)
    export_estratificacion(estrat, config, iteration, logger)
    generate_report(corpus, iteration, duplicates, excluidos_domain, total_input,
                    config, logger, excluidos_allow_lists, listas_activas)

    # RESOLUCIÓN DE REFERENCIAS (v0.8) — solo en modo ids_author_year.
    # Va después del filtro de allow lists a propósito: resolver antes
    # gastaría créditos en referencias de documentos que el filtro descarta.
    modo_refs = leer_campos_opcionales(config)['referenced_works']
    if modo_refs == 'ids_author_year':
        cache_refs = resolver_referencias(corpus, config, logger)
        if cache_refs:
            enriquecer_referencias(corpus, cache_refs, logger)
            # Solo se reescriben los exports que contienen la columna.
            logger.info("Reexportando con las referencias enriquecidas...")
            export_csv_principal(corpus, config, iteration, logger)
            export_by_keyword(corpus, keywords, config, iteration, logger)
            export_by_nucleo(corpus, keywords, config, iteration, logger)
        else:
            logger.warning(
                "No se resolvió ninguna referencia. Los CSV ya exportados "
                "conservan los identificadores sin autor ni año; se pueden "
                "completar después con WPB_BIBLM_S01b_completar_refs.py."
            )

    logger.info("=" * 80)
    logger.info(f"WPB_BIBLM completado. Resultados en: {config['output']['directorio']}/")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()

# ============================================================================
# HISTORIAL DE VERSIONES
# ============================================================================
# Registro de cambios de las versiones anteriores. La versión vigente se
# documenta en el docstring de cabecera.
#
# --------------------------------------------------------------------------
# CAMBIOS v0.8
# --------------------------------------------------------------------------
#
#     - CAMPOS OPCIONALES parametrizables desde el YAML (bloque campos_opcionales).
#       Los cinco vienen APAGADOS por defecto: un YAML sin el bloque produce el
#       mismo corpus que v0.7.
#
#       * referenced_works — works citados por el documento
#         Modos: ids_only | ids_author_year | count_only | none
#           ids_only         W123|W456
#           ids_author_year  W123~Smith~2019|W456~Müller~2021
#           count_only       columna n_referenced_works (entero)
#
#       * funders — financiadores, leídos de awards
#         Modos: ids_only | ids_and_names | count_only | none
#           ids_and_names    F123~"National Science Foundation"|F456~"..."
#
#       * has_content — una columna con los formatos disponibles: "pdf",
#         "grobid_xml", "pdf|grobid_xml", o vacío.
#
#       * has_fulltext — booleano.
#
#       * indexed_in — cuatro columnas booleanas: is_indexed_in_arxiv,
#         _crossref, _doaj, _pubmed. Los valores posibles del campo son esos
#         cuatro (documentación de OpenAlex, 2026-08-12).
#
#     - RESOLUCIÓN DE REFERENCIAS (modo ids_author_year). OpenAlex devuelve en
#       referenced_works únicamente identificadores: el autor y el año no viajan
#       en el objeto Work. resolver_referencias() los consulta en una pasada
#       aparte, con tres reducciones de costo:
#         1. corre sobre el corpus YA filtrado por allow lists, no sobre el bruto;
#         2. deduplica los IDs globalmente (un work citado 50 veces se resuelve 1);
#         3. consulta en lotes de 50 con el filtro OR de OpenAlex, no uno por uno.
#       Aun así son consultas adicionales y consumen créditos: las cuentas
#       gratuitas disponen de 1 USD/día. El log informa cuántas consultas hará
#       antes de empezar, y cuántos works no se pudieron resolver.
#
#     - Un valor no reconocido en campos_opcionales ABORTA con el listado de
#       valores válidos (regla F.4).
#
# --------------------------------------------------------------------------
# CAMBIOS v0.7
# --------------------------------------------------------------------------
#
#     - NUEVA COLUMNA author_affiliations. Conserva la anidación autor ->
#       instituciones -> país en un solo campo:
#           Autor~Institución~PAÍS;Autor~Inst2~PAÍS2|Autor2~Inst~PAÍS
#           |  separa autores    ;  separa afiliaciones del mismo autor
#           ~  une autor, institución y country_code
#       Motivo: `authors`, `author_institutions` y `author_countries` eran tres
#       listas planas construidas recorriendo todos los authorships, con
#       longitudes distintas entre sí (autor->instituciones es 1:N) y con la de
#       países pasando por sorted(set(...)), que deduplica y reordena. En el
#       corpus recuperado, el número de instituciones y el de países coincidían
#       solo en el 46,2% de las filas. Con esas columnas era imposible saber el
#       país de cada institución, y también distinguir "tres autores de la misma
#       institución" de "un autor con tres afiliaciones", casos distintos al
#       medir participación institucional.
#       El campo se emite SIN deduplicar, tal como viene de la API: si un par
#       (autor, institución) repetido debe contar una o dos veces es una decisión
#       analítica y corresponde al script que consume, no al que extrae.
#
#     - EFECTO SOBRE DATOS YA EXPORTADOS: los CSV anteriores a v0.7 no contienen
#       author_affiliations. No están mal —el dato faltaba, no era incorrecto—,
#       pero no permiten las métricas por institución. Hay que re-extraer.
#       S03 detecta la ausencia de la columna, avisa por log y omite el reporte
#       de instituciones en lugar de emitir números plausibles.
#
#     - author_institutions ahora incluye el country_code de cada institución
#       dentro del propio registro (antes se descartaba en la extracción).
#
#     - Los valores que se escriben en author_affiliations se sanean: |, ; y ~
#       se sustituyen por espacio, o romperían el parseo aguas abajo.
#       PENDIENTE: contar en el log cuántas veces se interviene.
#
#     - El filtro de allow lists registra las coincidencias de CADA criterio
#       activo sobre el corpus completo, antes de filtrar, y avisa de los que no
#       producen ninguna. Al combinarse con OR, un criterio que nunca coincide no
#       excluye nada y pasaba inadvertido.
#
# --------------------------------------------------------------------------
# CAMBIOS v0.6
# --------------------------------------------------------------------------
#
#     - FIX ANALÍTICO: la deduplicación descartaba la palabra clave de las copias
#       eliminadas. Un documento recuperado por 'decolonial' e 'indígena' quedaba
#       contabilizado solo bajo la primera. Los conteos por palabra clave estaban
#       subestimados y el sesgo dependía del orden de procesamiento.
#       keyword_origen pasa a ser una lista que acumula todas las palabras clave;
#       en los CSV se exporta separada por '|'.
#       CONSECUENCIA: los subcorpus por palabra clave y por núcleo dejan de ser
#       mutuamente excluyentes. Su suma puede superar el tamaño del corpus.
#       Todo análisis previo apoyado en conteos por palabra clave debe rehacerse.
#     - Renombrado a guion bajo por coherencia con S02 y S03
#       (antes: WPB_BIBLM_S01-export.py / WPB_BIBLM_v03.yaml)
#     - El diccionario de palabras clave detecta el separador (coma, tabulación o
#       punto y coma) y lo registra en el log; se lee con utf-8-sig para absorber
#       el BOM de Excel/Numbers. Antes, un archivo .csv separado por tabulaciones
#       producía un KeyError opaco ("Error cargando keywords: 'keyword'")
#     - Verificación explícita de columnas obligatorias del diccionario, con
#       listado de las encontradas frente a las esperadas
#     - Las filas con 'keyword' vacío se omiten con WARNING y número de fila
#
# --------------------------------------------------------------------------
# CAMBIOS v0.5
# --------------------------------------------------------------------------
#
#     - filtrar_por_allow_lists: parámetro YAML ahora efectivo. Filtro LOCAL
#       post-fetch, OR lógico entre las listas marcadas incluir: true
#     - estratificacion_fuentes: parámetro YAML ahora efectivo. Reporta sobre el
#       corpus PRE-filtro de allow lists (agregado y/o temporal)
#     - FIX: check_not_in_any_allow_list leía nombres de campo inexistentes
#       ('doaj', 'core') en lugar de los reales ('is_in_doaj', 'is_core'),
#       por lo que la columna not_in_any_allow_list era siempre True
#     - Confirmación interactiva antes de sobrescribir exportaciones previas
#       (flag --force para ejecución no atendida)
#     - Copia del YAML efectivo junto a los outputs (trazabilidad)
#     - Separador con timestamp al inicio de cada ejecución en el log
#     - CSV por keyword: agregadas las 3 columnas de allow list que faltaban
#     - NLTK pasa a ser dependencia OBLIGATORIA. Se eliminó el diccionario de
#       stopwords de respaldo (6-8 palabras/idioma vs 157-313 de NLTK), que
#       producía candidatos y TF-IDF no comparables sin dejar rastro
#     - FIX portabilidad: logging.FileHandler abría el log con la codificación
#       local del sistema. En Windows (cp1252) el script abortaba con
#       UnicodeEncodeError. Ahora declara encoding='utf-8'
#     - El único carácter no representable en cp1252 ('→', U+2192) se reemplazó
#       por '-->' ASCII. Los acentos españoles sí están en cp1252 y se conservan
#     - Progreso por página durante la recuperación (total disponible, páginas
#       estimadas, avance cada 5 páginas)
#
# --------------------------------------------------------------------------
# CAMBIOS v0.4
# --------------------------------------------------------------------------
#
#     - Tracking de keyword_origen en cada record (cuál keyword lo recuperó)
#     - TF-IDF: relevancia de cada término candidato en el corpus
#     - % en allow lists: para cada candidato, qué % de menciones están en DOAJ, CORE, etc
#     - Exportación POR KEYWORD: CSV individual + listado de IDs
#     - Exportación POR NÚCLEO TEÓRICO: CSV agregados
#     - Candidatos con métricas completas (TF-IDF, período, % allow lists)
#
# ============================================================================