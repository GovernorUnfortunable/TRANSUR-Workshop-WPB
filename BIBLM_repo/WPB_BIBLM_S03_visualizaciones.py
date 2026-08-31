"""
WPB_BIBLM_S03_visualizaciones.py v0.2

Módulo: Visualizaciones de series temporales por término y país
Entrada: CSVs de estadísticas de S02 (WPB_BIBLM_{iter:03d}_STATS_*.csv)
Salida: Gráficos en PNG / SVG (configurable)

Genera siete visualizaciones automáticas:
  1. individual_[keyword]:  Una por keyword, FR vs DE juntas, cuatro métricas
  2-3. all_keywords_[PAÍS]: Todas las palabras clave en Francia / Alemania
  4-5. top3_[PAÍS]:         Top 3 por documento acumulado
  6-7. rest_[PAÍS]:         Resto de palabras clave (excluyendo top 3)

CAMBIOS v0.2:
    - La iteración se DERIVA del nombre de los CSVs de entrada (como S02).
      Antes llevaba el hardcode 000; cambiar la iteración en S01 no se
      propagaba. Los outputs pasaban a usar el número detectado.
    - Renombrado a guion bajo: WPB_BIBLM_S03_visualizaciones.py
    - Paleta de colores OPERATIVA: URL de coolors.co → extrae hex; lista hex
      → usa directamente; null/absent → colormap tab20. Si hay más keywords
      que colores en la paleta, fallback a tab20 completo (evaluado una sola
      vez para coherencia).
    - Color FIJO por palabra clave: mismo keyword = mismo color en todos los
      gráficos. Se asigna al cargar los datos.
    - Formato múltiple: output.formato es una lista [png, svg]; ambos se
      generan si se declaran.
    - Protección de sobrescritura (--force) y copia del config usado.
    - Log por iteración con separador de corrida (como S01/S02).
    - `estilos` marcado como NO IMPLEMENTADO: se declara en YAML pero el
      código no lo lee. Es documentación de futuro.
    - `global.periodicidad_eje_x`: función `aggregate_by_periodicity` existe
      pero nunca se llama. Diferida a futuro script.

LIMITACIONES CONOCIDAS:
    - Sin comparaciones personalizadas (bloque vacío en YAML).
    - Eje X siempre anual. Agregación por período (bienal, quinquenal)
      está implementada como función pero no integrada.

Referencias:
  - Milia (2026): Rewiring vs Reconfiguration, Figura 10.2
  - Rule et al. (2019): Ten simple rules for computational analyses
"""

import re
import sys
import csv
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from urllib.parse import urlparse

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import yaml


# ═════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═════════════════════════════════════════════════════════════════════════════

COLUMNAS_METRICAS = [
    'n_docs_anual', 'n_docs_acumulado', 'pct_total_anual', 'n_autores_distintos',
    'largest_component_size_pct', 'newcomers_pct',
    'pct_article', 'pct_book', 'pct_book_chapter', 'pct_preprint',
    'pct_doaj', 'pct_core', 'pct_high_oa_rate', 'pct_scielo', 'pct_ojs',
]

# Paleta estándar de matplotlib
COLORMAP_DEFECTO = 'tab20'


# ═════════════════════════════════════════════════════════════════════════════
# CARGA Y DIAGNÓSTICO DE CONFIGURACIÓN
# ═════════════════════════════════════════════════════════════════════════════

def load_yaml_config(yaml_path: str) -> Dict:
    """Carga el YAML y aborta si no es válido."""
    ruta = Path(yaml_path)

    if not ruta.exists():
        print(f"\nERROR: no se encontró el archivo de configuración.\n"
              f"  Buscado: {ruta.resolve()}\n"
              f"  Directorio de trabajo: {Path.cwd()}\n", file=sys.stderr)
        sys.exit(1)

    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"\nERROR: el archivo YAML está mal escrito.\n"
              f"  Archivo: {ruta}\n"
              f"  Detalle: {e}\n", file=sys.stderr)
        sys.exit(1)

    if not isinstance(config, dict):
        print(f"\nERROR: {ruta} no contiene un mapeo en el nivel superior.\n",
              file=sys.stderr)
        sys.exit(1)

    return config


def detectar_iteracion(csv_dir: str, logger: Optional[logging.Logger] = None) -> int:
    """Deriva la iteración del nombre de los CSVs de S02."""
    ruta = Path(csv_dir)
    csvs = list(ruta.glob("WPB_BIBLM_*_STATS_*.csv"))

    if not csvs:
        msg = ("No se encontraron CSVs de S02 en el directorio. "
               "Se asume iteración 0; los outputs pueden pisar los de otra corrida.")
        if logger:
            logger.warning(msg)
        else:
            print(f"[WARNING] {msg}", file=sys.stderr)
        return 0

    nombre = csvs[0].name
    m = re.search(r'WPB_BIBLM_(\d{3})_', nombre)
    if not m:
        msg = (f"No se pudo derivar la iteración de '{nombre}'. "
               f"Se asume iteración 0.")
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
    """Log por iteración con separador de corrida."""
    logger = logging.getLogger('WPB_BIBLM_S03')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')

    if a_archivo:
        log_file = Path(output_dir) / f"WPB_BIBLM_{iteracion:03d}_S03_ejecucion.log"
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
    """Pide confirmación si ya existen gráficos de esta iteración."""
    directorio = Path(output_dir)
    if not directorio.exists():
        return

    prefijo = f"WPB_BIBLM_{iteracion:03d}_"
    existentes = sorted(p.name for p in directorio.glob(prefijo + "*.png"))
    existentes += sorted(p.name for p in directorio.glob(prefijo + "*.svg"))

    if not existentes:
        return

    print("\n" + "=" * 78)
    print(f"AVISO: ya existen gráficos de la iteración {iteracion:03d} en '{output_dir}/'")
    print("=" * 78)
    for nombre in existentes[:20]:
        print(f"  - {nombre}")
    if len(existentes) > 20:
        print(f"  ... y {len(existentes) - 20} archivo(s) más")
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
                        logger: logging.Logger) -> None:
    """Archiva el YAML tal como fue leído."""
    destino = Path(output_dir) / f"WPB_BIBLM_{iteracion:03d}_S03_config_usado.yaml"
    cabecera = [
        "# " + "-" * 70,
        f"# COPIA ARCHIVADA — corrida {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Origen: {Path(yaml_path).resolve()}",
        "# " + "-" * 70,
        "",
    ]
    try:
        original = open(yaml_path, encoding='utf-8').read()
        destino.write_text('\n'.join(cabecera) + original, encoding='utf-8')
        logger.info(f"Config usado: {destino}")
    except Exception as e:
        logger.warning(f"No se pudo archivar la configuración: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# LECTURA DE DATOS
# ═════════════════════════════════════════════════════════════════════════════

def load_all_stats(csv_dir: Path, logger: logging.Logger) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """Carga todos los CSVs de estadísticas y devuelve diccionario + lista de keywords.

    Retorna: (diccionario {(keyword, país): df}, lista keywords)
    """
    datos = {}
    keywords_set: Set[str] = set()
    paises = ['FR', 'DE']

    for csv_file in csv_dir.glob("WPB_BIBLM_*_STATS_*.csv"):
        # Nombre: WPB_BIBLM_{iter}_STATS_{keyword}_{PAÍS}.csv
        partes = csv_file.stem.split("_STATS_")
        if len(partes) < 2:
            continue
        resto = partes[1].rsplit("_", 1)
        if len(resto) != 2:
            continue
        keyword, pais = resto

        if pais not in paises:
            continue

        try:
            df = pd.read_csv(csv_file, encoding='utf-8')
            datos[(keyword, pais)] = df
            keywords_set.add(keyword)
            logger.debug(f"Cargado: {keyword} ({pais}), {len(df)} años")
        except Exception as e:
            logger.warning(f"Error cargando {csv_file.name}: {e}")

    keywords = sorted(keywords_set)
    logger.info(f"Datos cargados: {len(keywords)} keywords × 2 países = "
                f"{len(datos)} archivos")
    return datos, keywords


# ═════════════════════════════════════════════════════════════════════════════
# PALETA DE COLORES OPERATIVA
# ═════════════════════════════════════════════════════════════════════════════

def extraer_hex_de_url(url: str) -> Optional[List[str]]:
    """Extrae códigos hex de una URL de coolors.co.

    Formato esperado: https://coolors.co/264653-2a9d8f-e9c46a-f4a261-e76f51
    Devuelve: ['#264653', '#2a9d8f', '#e9c46a', '#f4a261', '#e76f51']
    """
    if not url or not isinstance(url, str):
        return None

    # coolors.co puede devolver la URL sin https://
    url = str(url).strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://coolors.co/' + url

    # Extraer solo los códigos hex que vienen después de coolors.co/
    try:
        # Si es una URL, el último segmento tiene los códigos
        parsed = urlparse(url)
        codigos = parsed.path.lstrip('/').strip('/')
        if not codigos:
            return None

        # Partir por guión y convertir a #XXXXXX
        colores = []
        for c in codigos.split('-'):
            c = c.strip().lower()
            if re.match(r'^[0-9a-f]{6}$', c):
                colores.append(f'#{c}')
        return colores if colores else None
    except Exception:
        return None


def obtener_paleta(config: Dict, keywords: List[str],
                   logger: logging.Logger) -> Dict[str, str]:
    """Obtiene y normaliza la paleta de colores. Asigna un color fijo por keyword.

    Reglas (regla A.4):
      1. Si config.colores.paleta es URL de coolors.co → extrae hex
      2. Si es lista de hex → usa directamente
      3. Si es null o ausente → tab20 de matplotlib
      4. Si hay más keywords que colores → fallback a tab20 completo

    Devuelve: {keyword: '#XXXXXX'}
    """
    cfg = (config.get('colores') or {})
    paleta_cfg = cfg.get('paleta')

    colores = []

    if isinstance(paleta_cfg, str):
        # Intentar como URL de coolors.co
        colores = extraer_hex_de_url(paleta_cfg)
        if colores:
            logger.info(f"Paleta de coolors.co: {len(colores)} colores extraídos")
        else:
            logger.warning(f"No se pudo interpretar como coolors.co: {paleta_cfg}. "
                           f"Usando tab20.")
    elif isinstance(paleta_cfg, list):
        # Lista de hex
        colores = [str(c).strip().lower() for c in paleta_cfg if c]
        colores = [c if c.startswith('#') else f'#{c}' for c in colores]
        logger.info(f"Paleta de lista: {len(colores)} colores")
    elif paleta_cfg is None:
        logger.debug("Paleta no declarada en YAML, usando tab20")
    else:
        logger.warning(f"Tipo inesperado para colores.paleta: {type(paleta_cfg)}, "
                       f"usando tab20")

    # Validación: si hay menos colores que keywords, fallback a tab20
    if colores and len(colores) < len(keywords):
        logger.warning(
            f"La paleta tiene {len(colores)} colores pero hay {len(keywords)} "
            f"keywords. Fallback a colormap tab20 para coherencia global."
        )
        colores = []

    # Asignar colores fijos por keyword
    asignaciones = {}
    if colores:
        for i, kw in enumerate(keywords):
            asignaciones[kw] = colores[i % len(colores)]
    else:
        # Usar tab20 de matplotlib
        cmap = plt.get_cmap(COLORMAP_DEFECTO)
        n = len(keywords)
        for i, kw in enumerate(keywords):
            asignaciones[kw] = cmap(i / max(n - 1, 1))

    logger.info(f"Colores asignados: {len(asignaciones)} keywords con colores fijos")
    return asignaciones


# ═════════════════════════════════════════════════════════════════════════════
# GENERACIÓN DE GRÁFICOS
# ═════════════════════════════════════════════════════════════════════════════

def graficar_individual(keyword: str, datos: Dict, colores: Dict, cfg: Dict,
                        iteracion: int, output_dir: Path, logger: logging.Logger) -> None:
    """Gráfico individual de un keyword: FR vs DE, cuatro métricas.

    Eje Y izq: n_docs_anual (barras)
    Eje Y der: n_docs_acumulado, largest_component_size_pct, newcomers_pct (líneas)
    """
    datos_fr = datos.get((keyword, 'FR'))
    datos_de = datos.get((keyword, 'DE'))

    if datos_fr is None or datos_de is None or len(datos_fr) == 0 or len(datos_de) == 0:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    color = colores.get(keyword, '#808080')

    for ax, país, df in [(ax1, 'FR', datos_fr), (ax2, 'DE', datos_de)]:
        ax.set_title(f"{keyword} ({país})", fontsize=14, fontweight='bold')
        ax.set_xlabel('Año', fontsize=11)

        # Eje izq: barras de n_docs_anual + línea de acumulado
        ax.set_ylabel('Número de documentos', fontsize=11)
        ax.bar(df['año'], df['n_docs_anual'], alpha=0.6, color=color, label='Número de docs. por año')
        
        # Eje derecho: solo porcentajes (0-100%)
        if 'n_docs_acumulado' in df.columns or 'largest_component_size_pct' in df.columns or 'newcomers_pct' in df.columns:
            ax2_ax = ax.twinx()
            ax2_ax.set_ylabel('Proporción (%)', fontsize=11)
            ax2_ax.set_ylim(0, 100)
            
            if 'n_docs_acumulado' in df.columns:
                ax.plot(df['año'], df['n_docs_acumulado'], '--', linewidth=2, color='black', label='Número de docs. (acumulado)')
            
            if 'largest_component_size_pct' in df.columns:
                ax2_ax.plot(df['año'], df['largest_component_size_pct'], 'o-', linewidth=1.5, color='gray', label='Componente ppal auts. %')
            if 'newcomers_pct' in df.columns:
                ax2_ax.plot(df['año'], df['newcomers_pct'], '^-', linewidth=1.5, color='#2ca02c', label='Newcomers %')
            
            # Combinar leyendas de ambos ejes
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2_ax.get_legend_handles_labels()
            ax2_ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=8)
            ax2_ax.grid(alpha=0.3)

    plt.tight_layout()
    png_path = output_dir / f"WPB_BIBLM_{iteracion:03d}_individual_{keyword.replace(' ', '_').lower()}.png"
    fig.savefig(png_path, dpi=300, bbox_inches='tight', format='png')
    logger.debug(f"Gráfico individual: {png_path.name}")
    plt.close(fig)


def graficar_comparativo(titulo: str, keywords_sel: List[str], país: str, datos: Dict,
                         colores: Dict, cfg: Dict, iteracion: int, output_dir: Path,
                         logger: logging.Logger, suffix: str) -> None:
    """Gráfico comparativo: varias palabras clave en el mismo país."""
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_title(f"{titulo} ({país})", fontsize=14, fontweight='bold')
    ax.set_xlabel('Año', fontsize=11)
    ax.set_ylabel('Documentos anuales', fontsize=11)

    for keyword in keywords_sel:
        df = datos.get((keyword, país))
        if df is not None and len(df) > 0:
            color = colores.get(keyword, '#808080')
            doaj_pct = df['pct_doaj'].iloc[-1] if 'pct_doaj' in df.columns else 0
            core_pct = df['pct_core'].iloc[-1] if 'pct_core' in df.columns else 0
            label_kw = f"{keyword} [doaj {doaj_pct:.0f}%; core {core_pct:.0f}%]"
            ax.plot(df['año'], df['n_docs_anual'], 'o-', label=label_kw, linewidth=2, color=color)

    ax.legend(fontsize=9, loc='best')
    ax.grid(alpha=0.3)
    plt.tight_layout()

    png_path = output_dir / f"WPB_BIBLM_{iteracion:03d}_{suffix}_{país}.png"
    fig.savefig(png_path, dpi=300, bbox_inches='tight', format='png')
    logger.debug(f"Gráfico comparativo: {png_path.name}")
    plt.close(fig)


def normalizar_keyword(keyword: str) -> str:
    """Convierte buen_vivir a 'buen vivir' para coincidir con S01."""
    return keyword.replace('_', ' ').lower()


def load_s01_corpus(csv_dir: Path, logger: logging.Logger) -> Optional[pd.DataFrame]:
    """Carga CSV de S01."""
    logger.info(f"Buscando CSV de S01 en: {csv_dir.resolve()}")
    
    # Intentar varios patrones
    csvs = list(csv_dir.glob("WPB_BIBLM_*_v*.csv"))
    logger.debug(f"Patrón 1 (WPB_BIBLM_*_v*.csv): {len(csvs)} encontrados")
    
    if not csvs:
        csvs = list(csv_dir.glob("WPB_BIBLM_*v*.csv"))
        logger.debug(f"Patrón 2 (WPB_BIBLM_*v*.csv): {len(csvs)} encontrados")
    
    if not csvs:
        csvs = list(csv_dir.glob("*.csv"))
        logger.debug(f"Patrón 3 (*.csv): {len(csvs)} encontrados - listando:")
        for c in csvs[:10]:
            logger.debug(f"  {c.name}")
        return None
    
    csv_s01 = sorted(csvs)[-1]
    logger.info(f"Leyendo: {csv_s01.name}")
    try:
        df = pd.read_csv(csv_s01, encoding='utf-8')
        logger.info(f"Corpus S01 cargado: {csv_s01.name}, {len(df)} documentos")
        # Deteccion de formato: S01 v0.7+ emite la columna author_affiliations,
        # que conserva el vinculo autor -> institucion -> pais.
        if 'author_affiliations' not in df.columns:
            logger.warning(
                "El corpus fue generado por una version de S01 anterior a v0.7: "
                "falta la columna author_affiliations, que vincula cada autor con "
                "sus instituciones. NO se generara el reporte de instituciones "
                "(el de journals si). Para obtenerlo hay que volver a correr S01."
            )
        return df
    except Exception as e:
        logger.warning(f"Error cargando {csv_s01.name}: {e}")
        return None


def extraer_top_journals(corpus_s01: pd.DataFrame, keyword: str, pais: str) -> pd.DataFrame:
    """Top 10 journals por keyword/país."""
    kw_norm = normalizar_keyword(keyword)
    df_kw = corpus_s01[corpus_s01['keyword_origen'].str.contains(kw_norm, na=False, case=False)]
    df_pais = df_kw[df_kw['author_countries'].str.contains(pais, na=False)]
    if len(df_pais) == 0:
        return pd.DataFrame()
    journals = df_pais.groupby('publication_venue').size().reset_index(name='cantidad')
    journals = journals.sort_values('cantidad', ascending=False).head(10)
    journals['porcentaje'] = (journals['cantidad'] / len(df_pais)) * 100
    journals['keyword'] = keyword
    journals['pais'] = pais
    return journals


def parsear_afiliaciones(campo: str) -> List[Tuple[str, str, str]]:
    """Convierte el campo author_affiliations de S01 en [(autor, institucion, pais), ...].

    Formato de entrada (S01 v0.7+):
        Autor~Inst~PAIS;Autor~Inst2~PAIS2|Autor2~Inst~PAIS
        |  separa autores   ;  separa afiliaciones del mismo autor
        ~  une autor, institucion y country_code

    Los autores sin institucion ("Autor~~") se descartan: no aportan vinculo
    institucional, que es lo que se cuenta aqui.
    """
    if not isinstance(campo, str) or not campo.strip():
        return []
    salida = []
    for bloque in campo.split('|'):
        for item in bloque.split(';'):
            partes = item.split('~')
            if len(partes) != 3:
                continue
            autor, inst, pais = (p.strip() for p in partes)
            if inst:
                salida.append((autor, inst, pais or '??'))
    return salida


def extraer_top_instituciones(corpus_s01: pd.DataFrame, keyword: str, pais: str) -> pd.DataFrame:
    """Top 10 instituciones de un subcorpus keyword x pais, con tres conteos.

    QUE SE CUENTA
    -------------
    El vinculo entre un work y una institucion se establece SIEMPRE a traves de
    un autor: OpenAlex no relaciona documentos con instituciones directamente,
    sino authorships (un autor) con instituciones. De ahi las tres columnas,
    que responden a preguntas distintas y NO son intercambiables:

      n_afiliaciones      Veces que se da el vinculo autor-institucion en el
                          subcorpus. Dos autores del CNRS en un mismo paper
                          cuentan 2; un autor del CNRS con dos afiliaciones
                          aporta 1 al CNRS. Es la medida de participacion
                          institucional en los documentos que movilizan la
                          palabra clave.
      n_autores_distintos Personas distintas que firman desde esa institucion.
                          Separa "muchos papers de una misma persona" de "una
                          comunidad amplia".
      n_documentos        Works distintos en los que aparece la institucion.
                          Aqui dos autores del CNRS en un paper cuentan 1.

    `pct_documentos` = n_documentos / total de documentos del subcorpus. Es el
    unico porcentaje que se emite porque es el unico con un denominador
    interpretable; NO suma 100 entre instituciones (un documento con tres
    afiliaciones cuenta en las tres).

    DOS PAISES DISTINTOS EN LA SALIDA
    ---------------------------------
    `pais`             = pais del SUBCORPUS (criterio de seleccion).
    `pais_institucion` = country_code de la institucion segun OpenAlex.
    Pueden diferir, y es informativo: una institucion alemana aparece en el
    subcorpus FR cuando coautora con Francia.

    Requiere la columna author_affiliations (S01 v0.7+). Sin ella devuelve
    vacio; el aviso se emite una sola vez en load_s01_corpus.
    """
    if 'author_affiliations' not in corpus_s01.columns:
        return pd.DataFrame()

    kw_norm = normalizar_keyword(keyword)
    df_kw = corpus_s01[corpus_s01['keyword_origen'].str.contains(kw_norm, na=False, case=False)]
    df_pais = df_kw[df_kw['author_countries'].str.contains(pais, na=False)]
    if len(df_pais) == 0:
        return pd.DataFrame()

    from collections import Counter, defaultdict
    afil = Counter()                       # institucion -> n vinculos autor-institucion
    autores = defaultdict(set)             # institucion -> autores distintos
    docs = defaultdict(set)                # institucion -> works distintos
    paises_vistos = defaultdict(Counter)   # institucion -> country_code observados

    ids = df_pais.get('openalex_id')
    if ids is None:
        ids = pd.Series(df_pais.index, index=df_pais.index)

    for doc_id, campo in zip(ids, df_pais['author_affiliations']):
        for autor, inst, pais_inst in parsear_afiliaciones(campo):
            afil[inst] += 1
            autores[inst].add(autor)
            docs[inst].add(doc_id)
            paises_vistos[inst][pais_inst] += 1

    if not afil:
        return pd.DataFrame()

    filas = [{
        'institution': inst,
        # country_code mas frecuente: OpenAlex puede traer el campo vacio en
        # algunos registros de la misma institucion.
        'pais_institucion': paises_vistos[inst].most_common(1)[0][0],
        'n_afiliaciones': n,
        'n_autores_distintos': len(autores[inst]),
        'n_documentos': len(docs[inst]),
        'pct_documentos': len(docs[inst]) / len(df_pais) * 100,
        'keyword': keyword,
        'pais': pais,
    } for inst, n in afil.most_common(10)]

    return pd.DataFrame(filas)


def generar_reportes_top(corpus_s01: pd.DataFrame, keywords: List[str], output_dir: Path, iteracion: int, logger: logging.Logger) -> None:
    """Genera CSV y TXT con top journals e instituciones."""
    if corpus_s01 is None:
        return

    todas_j = []
    todas_i = []
    
    for keyword in keywords:
        for pais in ['FR', 'DE']:
            df_j = extraer_top_journals(corpus_s01, keyword, pais)
            df_i = extraer_top_instituciones(corpus_s01, keyword, pais)
            if len(df_j) > 0:
                todas_j.append(df_j)
            if len(df_i) > 0:
                todas_i.append(df_i)
    
    if todas_j:
        df_j = pd.concat(todas_j, ignore_index=True)
        csv_j = output_dir / f"WPB_BIBLM_{iteracion:03d}_TOP_JOURNALS.csv"
        df_j.to_csv(csv_j, index=False, encoding='utf-8')
        logger.info(f"Top journals: {csv_j.name}")
    
    if todas_i:
        df_i = pd.concat(todas_i, ignore_index=True)
        csv_i = output_dir / f"WPB_BIBLM_{iteracion:03d}_TOP_INSTITUCIONES.csv"
        df_i.to_csv(csv_i, index=False, encoding='utf-8')
        logger.info(f"Top instituciones: {csv_i.name}")
    
    txt_path = output_dir / f"WPB_BIBLM_{iteracion:03d}_TOP_JOURNALS_INSTITUCIONES_REPORTE.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("=" * 90 + "\n")
        f.write("REPORTE: Top Journals e Instituciones por Keyword\n")
        f.write(f"Iteracion: {iteracion:03d}\n")
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 90 + "\n\n")
        
        for keyword in keywords:
            for pais in ['FR', 'DE']:
                df_j = extraer_top_journals(corpus_s01, keyword, pais)
                df_i = extraer_top_instituciones(corpus_s01, keyword, pais)
                
                if len(df_j) > 0 or len(df_i) > 0:
                    f.write(f"\n{'=' * 90}\n")
                    f.write(f"{keyword.upper()} ({pais})\n")
                    f.write(f"{'=' * 90}\n\n")
                    
                    if len(df_j) > 0:
                        f.write("TOP 10 JOURNALS\n")
                        f.write("-" * 90 + "\n")
                        for idx, row in df_j.iterrows():
                            f.write(f"  {idx+1:2d}. {row['publication_venue']:60s} | {row['cantidad']:4.0f} ({row['porcentaje']:5.1f}%)\n")
                        f.write("\n")
                    
                    if len(df_i) > 0:
                        f.write("TOP 10 INSTITUCIONES  (ordenadas por n_afiliaciones)\n")
                        f.write("  afil = veces que se da el vinculo autor-institucion\n")
                        f.write("  auts = autores distintos    docs = works distintos (% sobre el subcorpus)\n")
                        f.write("  [XX] = country_code de la institucion; puede diferir del pais del subcorpus\n")
                        f.write("-" * 90 + "\n")
                        for idx, row in df_i.iterrows():
                            etiqueta = f"{row['institution']} [{row['pais_institucion']}]"
                            f.write(f"  {idx+1:2d}. {etiqueta:52s} | "
                                    f"afil {row['n_afiliaciones']:4.0f} | "
                                    f"auts {row['n_autores_distintos']:4.0f} | "
                                    f"docs {row['n_documentos']:4.0f} ({row['pct_documentos']:5.1f}%)\n")
                        f.write("\n")
    
    logger.info(f"Reporte TXT: {txt_path.name}")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='WPB_BIBLM S03: generador de visualizaciones')
    parser.add_argument('--config', default='WPB_BIBLM_S03_visualizaciones.yaml',
                        help='Ruta al YAML de configuración')
    parser.add_argument('--csv-dir', default='output',
                        help='Directorio con los CSVs de S02')
    parser.add_argument('--output', default=None,
                        help='Directorio de salida (override del YAML)')
    parser.add_argument('--force', action='store_true',
                        help='Sobrescribe sin confirmación')
    args = parser.parse_args()

    config = load_yaml_config(args.config)

    # Detectar iteración ANTES de setup_logging
    csv_dir = Path(args.csv_dir)
    iteracion = detectar_iteracion(str(csv_dir))

    # Setup logging
    salida_cfg = config.get('salida') or {}
    output_dir = Path(args.output or salida_cfg.get('directorio', 'output'))
    log_cfg = config.get('logging') or {}
    logger = setup_logging(str(output_dir), iteracion,
                           nivel=log_cfg.get('nivel', 'INFO'),
                           a_archivo=bool(log_cfg.get('archivo_log', True)))

    logger.info("=" * 78)
    logger.info(f"WPB_BIBLM S03 v0.2 iniciado (iteración {iteracion:03d})")
    logger.info("=" * 78)
    logger.info(f"Config: {args.config}")

    confirmar_sobrescritura(str(output_dir), iteracion, args.force)
    volcar_config_usado(args.config, str(output_dir), iteracion, logger)
    detectar_iteracion(str(csv_dir), logger)

    # Cargar datos
    output_dir.mkdir(parents=True, exist_ok=True)
    datos, keywords = load_all_stats(csv_dir, logger)

    if not keywords:
        logger.error("No se encontraron datos en los CSVs de S02. Ejecución abortada.")
        sys.exit(1)

    logger.info(f"Keywords encontrados: {', '.join(keywords)}")

    # Cargar corpus S01 para reportes de top
    corpus_s01 = load_s01_corpus(csv_dir, logger)

    # Obtener paleta y colores fijos
    colores = obtener_paleta(config, keywords, logger)

    # Siete gráficos automáticos
    logger.info("Generando visualizaciones automáticas...")

    # 1. Individual por keyword
    for kw in keywords:
        graficar_individual(kw, datos, colores, config, iteracion, output_dir, logger)

    # 2-3. Todas las palabras clave en cada país
    for país in ['FR', 'DE']:
        kws_país = [k for k in keywords if (k, país) in datos]
        if kws_país:
            graficar_comparativo(
                f"Todos los keywords en {país}",
                kws_país, país, datos, colores, config, iteracion, output_dir, logger,
                "all_keywords"
            )

    # 4-5. Top 3 por acumulado en cada país
    for país in ['FR', 'DE']:
        datos_país = {k: datos[(k, país)] for k in keywords if (k, país) in datos}
        if datos_país:
            # Calcular acumulado máximo para cada keyword
            max_acum = {}
            for k, df in datos_país.items():
                if 'n_docs_acumulado' in df.columns:
                    max_acum[k] = df['n_docs_acumulado'].max()
                else:
                    max_acum[k] = df['n_docs_anual'].sum()
            top3 = sorted(max_acum.items(), key=lambda x: x[1], reverse=True)[:3]
            top3_kws = [k for k, _ in top3]

            if top3_kws:
                graficar_comparativo(
                    f"Top 3 keywords en {país}",
                    top3_kws, país, datos, colores, config, iteracion, output_dir, logger,
                    "top3"
                )

    # 6-7. Resto de keywords en cada país
    for país in ['FR', 'DE']:
        datos_país = {k: datos[(k, país)] for k in keywords if (k, país) in datos}
        if datos_país:
            max_acum = {}
            for k, df in datos_país.items():
                if 'n_docs_acumulado' in df.columns:
                    max_acum[k] = df['n_docs_acumulado'].max()
                else:
                    max_acum[k] = df['n_docs_anual'].sum()
            top3_kws = set(k for k, _ in sorted(max_acum.items(), key=lambda x: x[1], reverse=True)[:3])
            rest_kws = [k for k in keywords if k not in top3_kws and (k, país) in datos]

            if rest_kws:
                graficar_comparativo(
                    f"Resto de keywords en {país}",
                    rest_kws, país, datos, colores, config, iteracion, output_dir, logger,
                    "rest"
                )

    # Generar reportes de top journals e instituciones
    if corpus_s01 is not None:
        logger.info("Generando reportes de top journals e instituciones...")
        generar_reportes_top(corpus_s01, keywords, output_dir, iteracion, logger)

    logger.info("=" * 78)
    logger.info(f"S03 completado. Gráficos en: {output_dir}/")
    logger.info("=" * 78)


if __name__ == '__main__':
    main()