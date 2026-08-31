"""
WPB_BIBLM_S02_analisis.py v0.2

Módulo: Análisis de Estadísticas por Término y País
Entrada: CSV principal de S01 (WPB_BIBLM_{iter:03d}_v{iter}.0.csv)
Salida: CSVs + TXTs de estadísticas (por palabra clave × país)

Métricas generadas (todas configurables desde el YAML, bloque 'metricas'):
  1. n_docs_anual                 documentos por año
  2. n_docs_acumulado             suma acumulada
  3. pct_total_anual              % del total anual del corpus de ese país
  4. n_autores_distintos          autores únicos por año
  5. largest_component_size_pct   tamaño relativo del componente mayor
                                  en la red de coautorías (requiere networkx)
  6. newcomers_pct                % de autores que aparecen por primera vez
  7. pct_article / pct_book / pct_book_chapter / pct_preprint
  8. pct_doaj / pct_core / pct_high_oa_rate / pct_scielo / pct_ojs

NOTA: los datos se segmentan por PAÍS (FR, DE), no se agregan. Un documento
con autores en ambos países se cuenta en los dos.

CAMBIOS v0.2:
    - La iteración se DERIVA del nombre del CSV de entrada, no se hardcodea.
      Antes los outputs llevaban el literal '000': cambiar la iteración en S01
      no se propagaba, y las estadísticas de una corrida pisaban las de otra.
      Se eliminó metadata.iteracion del YAML (lo define S01).
    - keyword_origen: coincidencia por PERTENENCIA, no por igualdad. S01 v0.6
      exporta la columna como lista separada por '|'; comparar con == dejaba
      fuera todo documento recuperado por más de una palabra clave.
    - Reporte de solapamiento entre palabras clave: resumen en el log y CSV
      dedicado (_SOLAPAMIENTO_KEYWORDS.csv).
    - Se implementan los bloques que el YAML declaraba y el código ignoraba:
      metricas, red, precision, logging, validacion, salida.formatos.
    - Eliminado el fallback silencioso ante YAML ilegible. Un YAML mal formado
      aborta con archivo, línea, columna y fragmento del error.
    - Protección de sobrescritura (--force) y copia del config usado.
    - Log por iteración con separador de corrida, como S01.
    - Flag unificado a --config. Los overrides --csv/--output se registran en
      el log y en la copia archivada del config (regla A.5).
    - NUEVO bloque periodo_analisis: recorta el corpus ANTES de calcular.
      Redefine el corpus de análisis, no la vista (regla A.4). Desactivado por
      defecto. n_docs_acumulado y newcomers_pct cambian de significado al
      activarlo; el log y el encabezado de cada TXT lo advierten.

PENDIENTE CONOCIDO:
    - Rendimiento: la pertenencia por país se recalcula con df.apply() en cada
      combinación palabra clave × país. Decisión de agosto 2026: dejarlo hasta
      medir el costo real sobre el corpus completo.
    - Validación de contenido del YAML (claves faltantes o de tipo incorrecto)
      no implementada. Solo se valida que el archivo sea YAML bien formado.

Referencias:
  - Milia (2026): Rewiring vs Reconfiguration
  - Bettencourt & Kaur (2011): Evolution and structure of sustainability science
  - Rule et al. (2019): Ten simple rules for computational analyses
"""

import re
import sys
import csv
import math
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

import pandas as pd
import yaml

try:
    import networkx as nx
except ImportError:
    nx = None


# ═════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═════════════════════════════════════════════════════════════════════════════

# Nombre de la métrica en el YAML -> columna del CSV de S01 de la que sale.
# Escritas una sola vez (regla B.1): nunca inline en el cuerpo del código.
ALLOW_LIST_FIELDS = {
    'pct_doaj': 'is_in_doaj',
    'pct_core': 'is_core',
    'pct_high_oa_rate': 'is_high_oa_rate',
    'pct_scielo': 'is_in_scielo',
    'pct_ojs': 'is_ojs',
}

TIPO_DOC_FIELDS = {
    'pct_article': 'article',
    'pct_book': 'book',
    'pct_book_chapter': 'book-chapter',
    'pct_preprint': 'preprint',
}

# Orden canónico de columnas del CSV de estadísticas.
METRICAS_ORDEN = [
    'n_docs_anual', 'n_docs_acumulado', 'pct_total_anual', 'n_autores_distintos',
    'largest_component_size_pct', 'newcomers_pct',
    'pct_article', 'pct_book', 'pct_book_chapter', 'pct_preprint',
    'pct_doaj', 'pct_core', 'pct_high_oa_rate', 'pct_scielo', 'pct_ojs',
]

# Métricas que dependen de la red de coautorías. Si red.habilitado es false,
# estas se omiten aunque figuren como true en el bloque 'metricas'.
METRICAS_DE_RED = ['largest_component_size_pct', 'newcomers_pct']

COLUMNAS_REQUERIDAS = ['keyword_origen', 'publication_year', 'author_countries']


# ═════════════════════════════════════════════════════════════════════════════
# CARGA DE CONFIGURACIÓN
# ═════════════════════════════════════════════════════════════════════════════

def _fragmento_yaml(path: str, linea: int, columna: int, contexto: int = 2) -> str:
    """Devuelve las líneas alrededor del error, con un cursor en la columna."""
    try:
        lineas = open(path, encoding='utf-8').read().split('\n')
    except Exception:
        return ''

    ini = max(0, linea - 1 - contexto)
    fin = min(len(lineas), linea + contexto)
    ancho = len(str(fin))

    out = []
    for i in range(ini, fin):
        out.append(f"    {str(i+1).rjust(ancho)} | {lineas[i]}")
        if i + 1 == linea:
            out.append(f"    {' ' * ancho} | {' ' * columna}^")
    return '\n'.join(out)


def load_yaml_config(yaml_path: str) -> Dict:
    """Carga el YAML y aborta con diagnóstico si está mal formado.

    v0.2: reemplaza el fallback silencioso anterior, que ante un YAML ilegible
    armaba una configuración mínima con print() y seguía adelante. El usuario
    creía estar corriendo con su configuración y corría con otra.

    Solo valida que el archivo sea YAML bien formado (nivel 1). La validación
    de contenido —claves obligatorias, tipos— no está implementada.
    """
    ruta = Path(yaml_path)

    if not ruta.exists():
        print(f"\nERROR: no se encontró el archivo de configuración.\n"
              f"  Buscado: {ruta.resolve()}\n"
              f"  Directorio de trabajo: {Path.cwd()}\n"
              f"  Verificar la ruta pasada en --config.\n", file=sys.stderr)
        sys.exit(1)

    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"\n{'-' * 72}", file=sys.stderr)
        print("ERROR: el archivo YAML está mal escrito y no se pudo interpretar.",
              file=sys.stderr)
        print(f"\n  Archivo: {ruta}", file=sys.stderr)

        marca = getattr(e, 'problem_mark', None)
        if marca is not None:
            linea, columna = marca.line + 1, marca.column + 1
            print(f"  Línea {linea}, columna {columna}", file=sys.stderr)
            problema = getattr(e, 'problem', None)
            if problema:
                print(f"  Problema: {problema}", file=sys.stderr)
            contexto = getattr(e, 'context', None)
            if contexto:
                print(f"  Contexto: {contexto}", file=sys.stderr)
            fragmento = _fragmento_yaml(str(ruta), linea, columna)
            if fragmento:
                print(f"\n{fragmento}", file=sys.stderr)
            print("\n  NOTA: YAML señala dónde DETECTA el problema, que no siempre",
                  file=sys.stderr)
            print("  es donde se origina. Unas comillas sin cerrar en la línea 30",
                  file=sys.stderr)
            print("  pueden reportarse en la 45. Revisar también hacia arriba.",
                  file=sys.stderr)
        else:
            print(f"  Detalle: {e}", file=sys.stderr)

        print(f"{'-' * 72}\n", file=sys.stderr)
        sys.exit(1)

    if not isinstance(config, dict):
        print(f"\nERROR: {ruta} no contiene un mapeo de claves en el nivel "
              f"superior (se leyó: {type(config).__name__}).\n", file=sys.stderr)
        sys.exit(1)

    return config


def detectar_iteracion(csv_path: str, logger: Optional[logging.Logger] = None) -> int:
    """Deriva el número de iteración del nombre del CSV de S01.

    v0.2: antes el prefijo '000' estaba hardcodeado en los nombres de salida,
    de modo que subir metadata.iteracion en S01 no se propagaba y las
    estadísticas de dos iteraciones distintas se pisaban entre sí.

    Espera un nombre del tipo WPB_BIBLM_000_v0.0.csv y devuelve 0.
    """
    nombre = Path(csv_path).name
    m = re.search(r'WPB_BIBLM_(\d{3})_', nombre)

    if not m:
        msg = (f"No se pudo derivar la iteración del nombre '{nombre}'. "
               f"Se esperaba el patrón WPB_BIBLM_<NNN>_...  Se asume iteración 0; "
               f"los outputs pueden pisar los de otra corrida.")
        if logger:
            logger.warning(msg)
        else:
            print(f"[WARNING] {msg}", file=sys.stderr)
        return 0

    iteracion = int(m.group(1))
    if logger:
        logger.info(f"Iteración detectada desde '{nombre}': {iteracion:03d}")
    return iteracion


# ═════════════════════════════════════════════════════════════════════════════
# LOGGING, SOBRESCRITURA Y TRAZABILIDAD
# ═════════════════════════════════════════════════════════════════════════════

def setup_logging(output_dir: str, iteracion: int, nivel: str = 'INFO',
                  a_archivo: bool = True) -> logging.Logger:
    """Log por iteración con separador de corrida (coherente con S01).

    v0.2: antes se abría un archivo nuevo por corrida con timestamp en el
    nombre, que se acumulaban sin límite. Ahora un log por iteración, en modo
    append, con un separador al inicio de cada ejecución (regla D.2).
    """
    logger = logging.getLogger('WPB_BIBLM_S02')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')

    if a_archivo:
        log_file = Path(output_dir) / f"WPB_BIBLM_{iteracion:03d}_S02_ejecucion.log"
        # encoding explícito (regla E.1): FileHandler usa la codificación local
        # del sistema por defecto y aborta en Windows ante caracteres no cp1252
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('\n' + '=' * 78 + '\n')
            f.write(f"EJECUCIÓN {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write('=' * 78 + '\n')
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, str(nivel).upper(), logging.INFO))
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


def confirmar_sobrescritura(output_dir: str, iteracion: int, force: bool) -> None:
    """Pide confirmación si ya existen estadísticas de esta iteración.

    Se ejecuta ANTES de setup_logging para que el propio log no dispare el
    aviso. Por eso usa print() y no el logger.
    """
    directorio = Path(output_dir)
    if not directorio.exists():
        return

    prefijo = f"WPB_BIBLM_{iteracion:03d}_STATS_"
    existentes = sorted(p.name for p in directorio.glob(prefijo + "*"))
    solapamiento = directorio / f"WPB_BIBLM_{iteracion:03d}_SOLAPAMIENTO_KEYWORDS.csv"
    if solapamiento.exists():
        existentes.append(solapamiento.name)

    if not existentes:
        return

    print("\n" + "=" * 78)
    print(f"AVISO: ya existen estadísticas de la iteración {iteracion:03d} en '{output_dir}/'")
    print("=" * 78)
    for nombre in existentes[:20]:
        print(f"  - {nombre}")
    if len(existentes) > 20:
        print(f"  ... y {len(existentes) - 20} archivo(s) más")
    print("=" * 78)
    print("Continuar SOBRESCRIBE estos archivos. Los datos anteriores se pierden.")
    print("La iteración la define S01: para conservarlos, correr S01 con otra")
    print("iteración y apuntar entrada.csv_principal al CSV nuevo.")
    print("NOTA: no se eliminan los archivos de palabras clave que ya no estén")
    print("en el corpus; sobreviven de la corrida anterior (regla C.4).")
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


def volcar_config_usado(yaml_path: str, output_dir: str, iteracion: int,
                        overrides: Dict[str, str], logger: logging.Logger) -> None:
    """Archiva el YAML tal como fue leído, anotando los overrides de CLI.

    Regla D.1 (copia fiel del archivo) y regla A.5 (los overrides de línea de
    comandos deben quedar registrados): la copia se guarda intacta y los
    overrides se anotan como comentario de cabecera. Así ni la copia miente
    sobre el archivo, ni el override queda invisible.
    """
    destino = Path(output_dir) / f"WPB_BIBLM_{iteracion:03d}_S02_config_usado.yaml"
    try:
        cabecera = [
            "# " + "-" * 70,
            f"# COPIA ARCHIVADA — corrida {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Origen: {Path(yaml_path).resolve()}",
        ]
        if overrides:
            cabecera.append("#")
            cabecera.append("# OVERRIDES DE LÍNEA DE COMANDOS aplicados en esta corrida:")
            for flag, detalle in overrides.items():
                cabecera.append(f"#   {flag}  {detalle}")
            cabecera.append("# El cuerpo de abajo es el archivo original SIN modificar:")
            cabecera.append("# los valores efectivos son los de arriba.")
        else:
            cabecera.append("# Sin overrides de línea de comandos.")
        cabecera.append("# " + "-" * 70)
        cabecera.append("")

        original = open(yaml_path, encoding='utf-8').read()
        destino.write_text('\n'.join(cabecera) + original, encoding='utf-8')
        logger.info(f"Config usado: {destino}")
        if overrides:
            for flag, detalle in overrides.items():
                logger.warning(f"Override de CLI: {flag} {detalle}")
    except Exception as e:
        logger.warning(f"No se pudo archivar la configuración: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# LECTURA DEL CORPUS
# ═════════════════════════════════════════════════════════════════════════════

def load_csv_principal(csv_path: str, logger: logging.Logger) -> pd.DataFrame:
    """Carga el CSV principal de S01 y verifica las columnas que S02 necesita."""
    ruta = Path(csv_path)
    if not ruta.exists():
        logger.error(f"CSV no encontrado: {ruta.resolve()}")
        logger.error(f"Directorio de trabajo: {Path.cwd()}")
        logger.error("Revisar entrada.directorio_entrada y entrada.csv_principal.")
        sys.exit(1)

    df = pd.read_csv(ruta, encoding='utf-8')

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        logger.error(f"Al CSV {ruta.name} le faltan columnas requeridas: {faltantes}")
        logger.error(f"Columnas encontradas: {list(df.columns)}")
        logger.error("¿Es el CSV principal de S01, y no un export por palabra clave?")
        sys.exit(1)

    if len(df) == 0:
        logger.error(f"El CSV {ruta.name} no tiene registros. Nada que analizar.")
        sys.exit(1)

    logger.info(f"CSV cargado: {ruta} ({len(df)} registros)")
    return df


# ═════════════════════════════════════════════════════════════════════════════
# PERTENENCIA A PALABRA CLAVE Y PAÍS
# ═════════════════════════════════════════════════════════════════════════════

def split_pipe(valor) -> List[str]:
    """Parte un campo separado por '|' en lista, tolerando nulos."""
    if pd.isna(valor):
        return []
    return [x.strip() for x in str(valor).split('|') if x.strip()]


def belongs_to_keyword(valor_keyword_origen, keyword: str) -> bool:
    """¿Este registro fue recuperado por esta palabra clave?

    FIX v0.2: S01 v0.6 exporta keyword_origen como lista separada por '|',
    porque un documento puede ser recuperado por varias palabras clave. La
    comparación anterior (== keyword) devolvía False para todos los registros
    multi-palabra, excluyéndolos de todos sus subcorpus menos, a lo sumo, uno.
    """
    return keyword in split_pipe(valor_keyword_origen)


def belongs_to_country(valor_author_countries, country: str) -> bool:
    """¿Este registro tiene alguna afiliación en este país?

    Un documento con autores en Francia y Alemania pertenece a los dos y se
    cuenta en ambos. La comparación es contra los elementos separados, no
    contra la cadena entera: 'FR' no debe coincidir con 'FRO' (Islas Feroe).
    """
    return country in split_pipe(valor_author_countries)


def reportar_solapamiento(df: pd.DataFrame, keywords: List[str], iteracion: int,
                          output_dir: Path, logger: logging.Logger) -> None:
    """Reporta los documentos recuperados por más de una palabra clave.

    NUEVO v0.2. Desde S01 v0.6 los subcorpus por palabra clave dejaron de ser
    mutuamente excluyentes: un documento hallado por 'decolonial' y por
    'quilombo' entra en ambos, y la suma de los subcorpus supera el tamaño del
    corpus. Sin este reporte, esa diferencia parece un error de conteo.
    """
    conteo_por_kw = {kw: 0 for kw in keywords}
    filas_multi = []

    for _, row in df.iterrows():
        kws_doc = [k for k in split_pipe(row['keyword_origen']) if k in conteo_por_kw]
        for k in kws_doc:
            conteo_por_kw[k] += 1
        if len(kws_doc) > 1:
            filas_multi.append({
                'openalex_id': row.get('openalex_id', ''),
                'title': row.get('title', ''),
                'publication_year': row.get('publication_year', ''),
                'keywords': '|'.join(sorted(kws_doc)),
                'n_keywords': len(kws_doc),
            })

    suma_subcorpus = sum(conteo_por_kw.values())
    total_corpus = len(df)
    n_multi = len(filas_multi)
    pct = (100 * n_multi / total_corpus) if total_corpus else 0.0

    logger.info("-" * 60)
    logger.info("Solapamiento entre palabras clave")
    logger.info(f"  Corpus total:                      {total_corpus}")
    logger.info(f"  Suma de subcorpus por palabra clave: {suma_subcorpus}")
    logger.info(f"  Documentos en más de una:          {n_multi} ({pct:.1f}%)")
    if suma_subcorpus > total_corpus:
        logger.info(f"  Diferencia (conteos repetidos):    {suma_subcorpus - total_corpus}")
        logger.info("  Los subcorpus NO son mutuamente excluyentes: su suma")
        logger.info("  supera el corpus porque un documento puede pertenecer a varios.")
    logger.info("-" * 60)

    csv_path = output_dir / f"WPB_BIBLM_{iteracion:03d}_SOLAPAMIENTO_KEYWORDS.csv"
    fieldnames = ['openalex_id', 'title', 'publication_year', 'keywords', 'n_keywords']
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for fila in sorted(filas_multi, key=lambda r: (-r['n_keywords'], r['keywords'])):
            writer.writerow(fila)
    logger.info(f"CSV solapamiento: {csv_path} ({n_multi} documentos)")


# ═════════════════════════════════════════════════════════════════════════════
# PRECISIÓN NUMÉRICA
# ═════════════════════════════════════════════════════════════════════════════

def hacer_redondeador(precision_cfg: Dict, logger: logging.Logger):
    """Construye la función de redondeo declarada en el bloque 'precision'.

    v0.2: el bloque existía en el YAML y el código redondeaba siempre a un
    decimal con round(). Ahora decimales_porcentaje, decimales_componentes y
    el modo de redondeo se respetan.
    """
    modo = str(precision_cfg.get('redondeo', 'round')).lower()
    dec_pct = int(precision_cfg.get('decimales_porcentaje', 1))
    dec_comp = int(precision_cfg.get('decimales_componentes', 1))

    if modo not in ('round', 'floor', 'ceil'):
        logger.warning(f"precision.redondeo='{modo}' no reconocido "
                       f"(round|floor|ceil). Se usa 'round'.")
        modo = 'round'

    def redondear(valor: float, es_componente: bool = False) -> float:
        decimales = dec_comp if es_componente else dec_pct
        factor = 10 ** decimales
        if modo == 'floor':
            resultado = math.floor(valor * factor) / factor
        elif modo == 'ceil':
            resultado = math.ceil(valor * factor) / factor
        else:
            resultado = round(valor * factor) / factor
        return int(resultado) if decimales == 0 else resultado

    logger.debug(f"Precisión: {modo}, {dec_pct} decimales en porcentajes, "
                 f"{dec_comp} en métricas de red")
    return redondear


# ═════════════════════════════════════════════════════════════════════════════
# RED DE COAUTORÍAS
# ═════════════════════════════════════════════════════════════════════════════

def calcular_lcc(df_year: pd.DataFrame, red_cfg: Dict, redondear,
                 logger: logging.Logger) -> float:
    """Tamaño relativo del componente mayor en la red de coautorías del año.

    Cálculo LOCAL: no hay llamadas de red externa. Los autores del CSV son los
    nodos; dos autores quedan unidos si firman el mismo documento.

    v0.2: red.incluir_sin_id ahora se respeta. Con true, los documentos sin
    author_ids se omiten del grafo pero siguen contando en las demás
    estadísticas; con false se omiten igual y se deja constancia en el log.
    """
    if nx is None or len(df_year) == 0:
        return 0.0

    incluir_sin_id = bool(red_cfg.get('incluir_sin_id', True))

    G = nx.Graph()
    autores = set()
    sin_id = 0

    for _, row in df_year.iterrows():
        author_ids = split_pipe(row.get('author_ids'))
        if not author_ids:
            sin_id += 1
            continue
        G.add_nodes_from(author_ids)
        autores.update(author_ids)
        for i in range(len(author_ids)):
            for j in range(i + 1, len(author_ids)):
                G.add_edge(author_ids[i], author_ids[j])

    if sin_id and not incluir_sin_id:
        logger.debug(f"  {sin_id} documento(s) sin author_ids omitidos de la red")

    if not autores:
        return 0.0

    componentes = list(nx.connected_components(G))
    if not componentes:
        return 0.0

    mayor = max(componentes, key=len)
    return redondear(len(mayor) / len(autores) * 100, es_componente=True)


# ═════════════════════════════════════════════════════════════════════════════
# CÁLCULO DE MÉTRICAS
# ═════════════════════════════════════════════════════════════════════════════

def metricas_activas(config: Dict, logger: logging.Logger) -> List[str]:
    """Devuelve las métricas habilitadas, respetando el bloque 'metricas'.

    v0.2: el bloque se declaraba en el YAML y el código calculaba las quince
    siempre. Si red.habilitado es false, las métricas de red se desactivan
    aunque figuren como true.
    """
    cfg = config.get('metricas') or {}
    if not cfg:
        logger.warning("El YAML no declara el bloque 'metricas'; se calculan todas.")
        activas = list(METRICAS_ORDEN)
    else:
        activas = [m for m in METRICAS_ORDEN if cfg.get(m, True)]
        omitidas = [m for m in METRICAS_ORDEN if m not in activas]
        if omitidas:
            logger.info(f"Métricas desactivadas en el YAML: {omitidas}")

    red_habilitada = bool((config.get('red') or {}).get('habilitado', True))
    if not red_habilitada:
        quitadas = [m for m in METRICAS_DE_RED if m in activas]
        if quitadas:
            logger.info(f"red.habilitado=false: se omiten {quitadas}")
        activas = [m for m in activas if m not in METRICAS_DE_RED]
    elif nx is None:
        quitadas = [m for m in METRICAS_DE_RED if m in activas]
        if quitadas:
            logger.warning(
                f"networkx no está instalado: se omiten {quitadas}. "
                f"Estas columnas NO aparecerán en los CSV, de modo que los "
                f"resultados no son equivalentes a los de una corrida con "
                f"networkx. Instalar con: pip install networkx"
            )
        activas = [m for m in activas if m not in METRICAS_DE_RED]

    logger.debug(f"Métricas activas ({len(activas)}): {activas}")
    return activas


def calcular_metricas(df: pd.DataFrame, keyword: str, country: str,
                      activas: List[str], config: Dict, redondear,
                      logger: logging.Logger) -> Optional[Tuple[Dict, pd.DataFrame]]:
    """Calcula las métricas de una palabra clave en un país.

    Devuelve (metricas, df_filtrado) o None si no hay datos.
    """
    mask_kw = df['keyword_origen'].apply(lambda v: belongs_to_keyword(v, keyword))
    mask_pais = df['author_countries'].apply(lambda v: belongs_to_country(v, country))
    df_filtrado = df[mask_kw & mask_pais].copy()

    if len(df_filtrado) == 0:
        return None

    años = sorted({int(y) for y in df_filtrado['publication_year'].dropna()})
    if not años:
        logger.warning(f"  {keyword} ({country}): sin años válidos")
        return None

    logger.info(f"  {keyword} ({country}): {len(df_filtrado)} registros, "
                f"{años[0]}-{años[-1]}")

    # Denominador de pct_total_anual: todo el corpus del país, no solo esta
    # palabra clave. Se calcula una vez por (palabra clave, país).
    df_pais = df[mask_pais]
    total_por_año = df_pais['publication_year'].dropna().astype(int).value_counts().to_dict()

    red_cfg = config.get('red') or {}
    resultados = {'años': años}
    for m in activas:
        resultados[m] = []

    acumulado = 0
    autores_previos: Set[str] = set()

    for año in años:
        df_año = df_filtrado[df_filtrado['publication_year'] == año]
        n_docs = len(df_año)
        acumulado += n_docs

        autores_año: Set[str] = set()
        for _, row in df_año.iterrows():
            autores_año.update(split_pipe(row.get('author_ids')))

        if 'n_docs_anual' in resultados:
            resultados['n_docs_anual'].append(n_docs)
        if 'n_docs_acumulado' in resultados:
            resultados['n_docs_acumulado'].append(acumulado)
        if 'pct_total_anual' in resultados:
            total_año = total_por_año.get(año, 0)
            pct = (n_docs / total_año * 100) if total_año else 0.0
            resultados['pct_total_anual'].append(redondear(pct))
        if 'n_autores_distintos' in resultados:
            resultados['n_autores_distintos'].append(len(autores_año))
        if 'largest_component_size_pct' in resultados:
            resultados['largest_component_size_pct'].append(
                calcular_lcc(df_año, red_cfg, redondear, logger))
        if 'newcomers_pct' in resultados:
            nuevos = autores_año - autores_previos
            pct_nuevos = (len(nuevos) / len(autores_año) * 100) if autores_año else 0.0
            resultados['newcomers_pct'].append(redondear(pct_nuevos, es_componente=True))

        autores_previos.update(autores_año)

        tipos = df_año['type'].value_counts().to_dict() if 'type' in df_año.columns else {}
        for metrica, tipo in TIPO_DOC_FIELDS.items():
            if metrica in resultados:
                pct = (tipos.get(tipo, 0) / n_docs * 100) if n_docs else 0.0
                resultados[metrica].append(redondear(pct))

        for metrica, columna in ALLOW_LIST_FIELDS.items():
            if metrica in resultados:
                if columna in df_año.columns and n_docs:
                    pct = df_año[columna].fillna(False).astype(bool).sum() / n_docs * 100
                else:
                    pct = 0.0
                resultados[metrica].append(redondear(pct))

    return resultados, df_filtrado


# ═════════════════════════════════════════════════════════════════════════════
# EXPORTACIÓN
# ═════════════════════════════════════════════════════════════════════════════

def recortar_periodo(df: pd.DataFrame, config: Dict,
                     logger: logging.Logger) -> pd.DataFrame:
    """Recorta el corpus de análisis al período declarado en el YAML.

    NUEVO v0.2. ALCANCE (regla A.4): este recorte redefine el CORPUS DE
    ANÁLISIS, no la vista. Todo lo que S02 calcula parte del corpus recortado.

    Dos métricas cambian de significado según dónde se recorte:

      n_docs_acumulado  arrastra el histórico. Recortado aquí, la serie
                        arranca en cero el primer año del período. Recortado
                        en S03, la curva entra al período con el valor que el
                        término ya traía.

      newcomers_pct     'nuevo' es relativo a un histórico. Recortado aquí,
                        un autor que publicó antes del período y reaparece
                        dentro cuenta como nuevo, porque su aparición previa
                        quedó fuera del universo. Recortado en S03, sigue
                        siendo un autor previo.

    Ninguna de las dos lecturas es más correcta: responden preguntas distintas.
    Recortar aquí equivale a definir 'nuevo en el período'. Para ver una
    ventana de un proceso que empezó antes, usar global.periodo_* en S03 y
    dejar este bloque desactivado.
    """
    cfg = config.get('periodo_analisis') or {}
    if not cfg.get('habilitado', False):
        logger.debug("Recorte temporal del corpus: DESACTIVADO")
        return df

    inicio = cfg.get('inicio')
    fin = cfg.get('fin')
    if inicio is None and fin is None:
        logger.warning("periodo_analisis.habilitado=true pero no se declaró "
                       "inicio ni fin. No se recorta nada.")
        return df

    n_antes = len(df)
    años = pd.to_numeric(df['publication_year'], errors='coerce')

    mask = pd.Series(True, index=df.index)
    if inicio is not None:
        mask &= años >= int(inicio)
    if fin is not None:
        mask &= años <= int(fin)

    sin_año = int(años.isna().sum())
    df_recortado = df[mask].copy()
    excluidos = n_antes - len(df_recortado)

    etiqueta = f"{inicio if inicio is not None else '...'}-{fin if fin is not None else '...'}"
    logger.warning("=" * 60)
    logger.warning(f"CORPUS DE ANÁLISIS RECORTADO al período {etiqueta}")
    logger.warning(f"  Registros antes:    {n_antes}")
    logger.warning(f"  Registros después:  {len(df_recortado)}")
    logger.warning(f"  Excluidos:          {excluidos} "
                   f"({100*excluidos/n_antes:.1f}%)" if n_antes else "")
    if sin_año:
        logger.warning(f"  Sin año de publicación (excluidos): {sin_año}")
    logger.warning("  n_docs_acumulado arranca en cero al inicio del período.")
    logger.warning("  newcomers_pct considera 'nuevo' a quien no publicó DENTRO")
    logger.warning("  del período, aunque hubiera publicado antes.")
    logger.warning("  Estas series NO son comparables con las de una corrida")
    logger.warning("  sin recorte ni con un recorte hecho en S03.")
    logger.warning("=" * 60)

    if len(df_recortado) == 0:
        logger.error(f"El recorte al período {etiqueta} dejó el corpus vacío. "
                     f"Revisar periodo_analisis. Ejecución abortada.")
        sys.exit(1)

    return df_recortado


def slug(texto: str) -> str:
    """Normaliza una palabra clave para usarla en un nombre de archivo."""
    return str(texto).replace(' ', '_').lower()


def export_stats_csv(metricas: Dict, activas: List[str], keyword: str, country: str,
                     iteracion: int, output_dir: Path, logger: logging.Logger) -> None:
    """CSV de estadísticas de una palabra clave en un país."""
    csv_path = output_dir / f"WPB_BIBLM_{iteracion:03d}_STATS_{slug(keyword)}_{country}.csv"
    fieldnames = ['año'] + activas

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, año in enumerate(metricas['años']):
            fila = {'año': año}
            for m in activas:
                fila[m] = metricas[m][i]
            writer.writerow(fila)

    logger.debug(f"  CSV: {csv_path.name}")


def export_stats_txt(metricas: Dict, activas: List[str], keyword: str, country: str,
                     df_filtrado: pd.DataFrame, iteracion: int, output_dir: Path,
                     logger: logging.Logger, periodo_cfg: Optional[Dict] = None) -> None:
    """Resumen legible de una palabra clave en un país."""
    txt_path = output_dir / f"WPB_BIBLM_{iteracion:03d}_STATS_{slug(keyword)}_{country}.txt"
    años = metricas['años']

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write(f"ESTADÍSTICAS: {keyword} ({country})\n")
        f.write("=" * 80 + "\n\n")

        f.write("METADATA\n" + "-" * 80 + "\n")
        f.write(f"Palabra clave: {keyword}\n")
        f.write(f"País: {country}\n")
        f.write(f"Iteración: {iteracion:03d}\n")
        f.write(f"Primer año con registros: {años[0]}\n")
        f.write(f"Último año con registros: {años[-1]}\n")
        f.write(f"Años con actividad: {len(años)}\n")
        f.write(f"Total de documentos: {len(df_filtrado)}\n")
        if 'n_autores_distintos' in metricas:
            f.write(f"Máx. autores distintos en un año: {max(metricas['n_autores_distintos'])}\n")
        f.write("\nNOTA: un documento recuperado por varias palabras clave aparece\n")
        f.write("en las estadísticas de todas ellas. Ver _SOLAPAMIENTO_KEYWORDS.csv\n")

        if periodo_cfg and periodo_cfg.get('habilitado', False):
            ini = periodo_cfg.get('inicio', '...')
            fin = periodo_cfg.get('fin', '...')
            f.write("\n" + "!" * 80 + "\n")
            f.write(f"CORPUS RECORTADO AL PERÍODO {ini}-{fin}\n")
            f.write("Los documentos fuera de ese rango se excluyeron ANTES de calcular.\n")
            f.write("  - n_docs_acumulado arranca en cero al inicio del período\n")
            f.write("  - newcomers_pct considera 'nuevo' a quien no publicó dentro\n")
            f.write("    del período, aunque hubiera publicado antes\n")
            f.write("Estas series no son comparables con las de una corrida sin recorte.\n")
            f.write("!" * 80 + "\n")

        f.write("\n")

        if 'author_institutions' in df_filtrado.columns:
            f.write("INSTITUCIONES PRINCIPALES (Top 5)\n" + "-" * 80 + "\n")
            instituciones: Dict[str, int] = defaultdict(int)
            for _, row in df_filtrado.iterrows():
                for inst in split_pipe(row.get('author_institutions')):
                    instituciones[inst] += 1
            top = sorted(instituciones.items(), key=lambda x: x[1], reverse=True)[:5]
            if top:
                for i, (inst, n) in enumerate(top, 1):
                    f.write(f"{i}. {inst} — {n} documentos ({n/len(df_filtrado)*100:.1f}%)\n")
            else:
                f.write("(sin datos de institución)\n")
            f.write("\n")

        presentes = [(m, c) for m, c in ALLOW_LIST_FIELDS.items()
                     if c in df_filtrado.columns]
        if presentes:
            f.write("DISTRIBUCIÓN DE ACCESO ABIERTO (agregado del período)\n")
            f.write("-" * 80 + "\n")
            total = len(df_filtrado)
            for metrica, columna in presentes:
                n = df_filtrado[columna].fillna(False).astype(bool).sum()
                f.write(f"{columna}: {n/total*100:.1f}%  ({n}/{total})\n")
            f.write("\n")

        f.write("TABLA TEMPORAL\n" + "-" * 80 + "\n")
        columnas = ['año'] + activas
        anchos = {c: max(len(c), 9) for c in columnas}
        f.write(" | ".join(c.ljust(anchos[c]) for c in columnas) + "\n")
        f.write("-" * 80 + "\n")
        for i, año in enumerate(años):
            valores = [str(año).ljust(anchos['año'])]
            valores += [str(metricas[m][i]).ljust(anchos[m]) for m in activas]
            f.write(" | ".join(valores) + "\n")
        f.write("\n")

    logger.debug(f"  TXT: {txt_path.name}")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='WPB_BIBLM S02: análisis de estadísticas por término y país')
    parser.add_argument('--config', default='WPB_BIBLM_S02_analisis.yaml',
                        help='Ruta al YAML de configuración')
    parser.add_argument('--csv', default=None,
                        help='(Override) Ruta al CSV principal de S01')
    parser.add_argument('--output', default=None,
                        help='(Override) Directorio de salida')
    parser.add_argument('--force', action='store_true',
                        help='Sobrescribe sin confirmación (ejecución no atendida)')
    args = parser.parse_args()

    config = load_yaml_config(args.config)

    # Precedencia: CLI > YAML. Cada override se anota (regla A.5).
    overrides: Dict[str, str] = {}

    entrada = config.get('entrada') or {}
    csv_yaml = str(Path(entrada.get('directorio_entrada', '.')) /
                   entrada.get('csv_principal', ''))
    if args.csv:
        csv_path = args.csv
        overrides['--csv'] = f"= {args.csv}   (el YAML declaraba: {csv_yaml})"
    else:
        csv_path = csv_yaml

    salida = config.get('salida') or {}
    dir_yaml = salida.get('directorio', 'output')
    if args.output:
        output_dir = args.output
        overrides['--output'] = f"= {args.output}   (el YAML declaraba: {dir_yaml})"
    else:
        output_dir = dir_yaml
    output_dir = Path(output_dir)

    iteracion = detectar_iteracion(csv_path)

    confirmar_sobrescritura(str(output_dir), iteracion, args.force)

    log_cfg = config.get('logging') or {}
    logger = setup_logging(str(output_dir), iteracion,
                           nivel=log_cfg.get('nivel', 'INFO'),
                           a_archivo=bool(log_cfg.get('archivo_log', True)))

    logger.info("=" * 78)
    logger.info(f"WPB_BIBLM S02 v0.2 iniciado (iteración {iteracion:03d})")
    logger.info("=" * 78)
    logger.info(f"Config: {args.config}")

    volcar_config_usado(args.config, str(output_dir), iteracion, overrides, logger)
    detectar_iteracion(csv_path, logger)   # registra la detección en el log

    df = load_csv_principal(csv_path, logger)

    # El recorte va ANTES del solapamiento y de las métricas: redefine el
    # corpus de análisis, de modo que todo lo posterior parte de él.
    df = recortar_periodo(df, config, logger)

    filtros = config.get('filtros') or {}
    disponibles = sorted({kw for v in df['keyword_origen'] for kw in split_pipe(v)})

    if filtros.get('procesar_todos', True):
        keywords = disponibles
    else:
        pedidas = filtros.get('keywords_seleccionados') or []
        if not pedidas:
            logger.warning("procesar_todos=false pero keywords_seleccionados está "
                           "vacío; se procesan todas las palabras clave.")
            keywords = disponibles
        else:
            keywords = [k for k in pedidas if k in disponibles]
            ausentes = [k for k in pedidas if k not in disponibles]
            if ausentes:
                logger.warning(f"Palabras clave pedidas que no están en el corpus: {ausentes}")

    if not keywords:
        logger.error("No hay palabras clave para procesar. Ejecución abortada.")
        sys.exit(1)

    paises = filtros.get('paises') or ['FR', 'DE']
    logger.info(f"Palabras clave: {len(keywords)} | Países: {', '.join(paises)}")

    reportar_solapamiento(df, keywords, iteracion, output_dir, logger)

    activas = metricas_activas(config, logger)
    if not activas:
        logger.error("No quedó ninguna métrica activa. Revisar el bloque 'metricas'.")
        sys.exit(1)

    redondear = hacer_redondeador(config.get('precision') or {}, logger)

    formatos = (config.get('salida') or {}).get('formatos') or {}
    hacer_csv = bool(formatos.get('csv', True))
    hacer_txt = bool(formatos.get('txt', True))
    if not (hacer_csv or hacer_txt):
        logger.error("salida.formatos: csv y txt están ambos en false. "
                     "No habría nada que escribir. Ejecución abortada.")
        sys.exit(1)
    if not hacer_csv:
        logger.warning("salida.formatos.csv=false: S03 necesita estos CSV y no "
                       "podrá generar gráficos de esta corrida.")

    reportar_vacios = bool((config.get('validacion') or {}).get('reportar_vacios', True))

    generados = 0
    vacios: List[str] = []

    for keyword in keywords:
        logger.info(f"Procesando: {keyword}")
        for country in paises:
            resultado = calcular_metricas(df, keyword, country, activas,
                                          config, redondear, logger)
            if resultado is None:
                vacios.append(f"{keyword} ({country})")
                if reportar_vacios:
                    logger.warning(f"  {keyword} ({country}): sin registros, se omite")
                continue

            metricas, df_filtrado = resultado
            if hacer_csv:
                export_stats_csv(metricas, activas, keyword, country,
                                 iteracion, output_dir, logger)
            if hacer_txt:
                export_stats_txt(metricas, activas, keyword, country, df_filtrado,
                                 iteracion, output_dir, logger,
                                 periodo_cfg=config.get('periodo_analisis'))
            generados += 1

    logger.info("=" * 78)
    logger.info(f"S02 completado: {generados} combinación(es) palabra clave × país")
    if vacios:
        logger.info(f"Sin registros ({len(vacios)}): {', '.join(vacios[:10])}"
                    + (" ..." if len(vacios) > 10 else ""))
    logger.info(f"Resultados en: {output_dir}/")
    logger.info("=" * 78)


if __name__ == '__main__':
    main()