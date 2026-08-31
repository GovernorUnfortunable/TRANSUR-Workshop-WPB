"""
WPB_BIBLM_S01b_completar_refs.py v0.1

Módulo: WPB_BIBLM — Completado de referencias no resueltas
Entrada: CSV principal de S01 v0.8+ (WPB_BIBLM_{iter:03d}_v*.csv)
Salida:  el mismo CSV, reescrito con la columna referenced_works completada

QUÉ RESUELVE
------------
S01 v0.8 resuelve autor y año de cada work referenciado consultando OpenAlex
con el corpus por defecto (corpus=core). Ese corpus excluye el expansion
corpus —los ~190M registros incorporados en la actualización Walden, sobre
todo datasets y registros de un solo repositorio—, de modo que las
referencias que viven ahí no se resuelven y quedan en el CSV como su ID a
secas.

En la corrida del 2026-08-26 fueron 13.159 de 160.778 (8,2%), concentradas
en un bloque contiguo de identificadores altos. Verificado con
WPB_BIBLM_D01_diag_refs.py sobre una muestra de 50: 0 devueltos con el
corpus por defecto, 41 con corpus=all, los 41 con is_xpac=true. Los 9
restantes no los devuelve ninguna de las dos vías (fusionados o retirados).

Este script recorre el CSV, toma los IDs sin resolver y los reconsulta con
corpus=all. No vuelve a pedir los ya resueltos.

    Documentación del parámetro corpus y del atributo is_xpac:
    help.openalex.org, "Attributes - Works" (2026-08-12) y
    "LLM Quick Reference" (consultado 2026-08-26).

FORMATO DE LA COLUMNA
---------------------
S01 v0.8 emite tres componentes por referencia:

    W123~Smith~2019|W456~Müller~2021
    |  separa referencias    ~  une id, primer autor y año

Este script agrega un CUARTO componente a las que provienen del expansion
corpus, y solo a ellas:

    W123~Smith~2019          referencia del corpus core
    W789~Nowak~2020~xpac     referencia del expansion corpus
    W999                     no resuelta por ninguna vía

El corpus de documentos NO se ve afectado: la búsqueda por palabra clave de
S01 usa el corpus por defecto y sigue siendo íntegramente core. La marca
xpac aplica únicamente a las obras CITADAS.

Se marca porque OpenAlex declara menor calidad de metadatos en el expansion
corpus, y porque una vez escritas sin marca las dos poblaciones quedan
indistinguibles en el CSV: no hay forma de reconstruir el origen sin volver
a consultar los 13.159 identificadores. La decisión de incluirlas o no en un
análisis corresponde a quien analiza (corolario de la regla B.5).

REESCRITURA SEGURA
------------------
El CSV se reescribe en su lugar, pero pasando por un archivo temporal que
reemplaza al original solo cuando la escritura terminó completa. Un fallo a
mitad de camino deja el CSV original intacto (regla C.1).

USO
---
    python3 WPB_BIBLM_S01b_completar_refs.py \
        --csv output/WPB_BIBLM_000_v0.0.csv \
        --config WPB_BIBLM_S01_export.yaml

    --force              sobrescribe sin pedir confirmación
    --dry-run            consulta y reporta, sin tocar el CSV
    --lote N             IDs por consulta (default 50, tope del filtro OR)

Es idempotente: reejecutarlo solo reintenta lo que siga sin resolver. Los
que no devuelve ninguna vía volverán a consultarse en cada corrida; el log
informa cuántos son.

Referencias:
  - Rule et al. (2019): Ten simple rules for computational analyses
"""

import re
import csv
import sys
import time
import shutil
import logging
import argparse
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional

import requests
import yaml


# ═════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═════════════════════════════════════════════════════════════════════════════

# Tope de IDs por consulta en un filtro OR de OpenAlex. Ver nota en S01 v0.8:
# la documentación da 50 y 100 según la página; 50 es válido bajo ambas.
LOTE_DEFECTO = 50

# Clave del filtro por ID. La corrida del 2026-08-26 confirmó que la API
# acepta 'openalex' (línea de log: "Clave de filtro por ID aceptada por la
# API: 'openalex'"). Se conserva la segunda variante como respaldo.
CLAVES_FILTRO_ID = ('openalex', 'openalex_id')

MARCA_XPAC = 'xpac'

REINTENTOS = 3
BACKOFF_BASE = 2
DEMORA = 0.1


# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN Y LOGGING
# ═════════════════════════════════════════════════════════════════════════════

def cargar_credenciales(yaml_path: str,
                        logger: Optional[logging.Logger] = None) -> Dict:
    """Toma api_key y mailto del YAML de S01. Sin YAML, consulta sin clave."""
    p = Path(yaml_path)
    if not p.exists():
        msg = (f"No se encontró {p}. Se consulta sin api_key, contra el "
               f"presupuesto libre (menor cuota diaria).")
        if logger:
            logger.warning(msg)
        else:
            print(f"[aviso] {msg}")
        return {}
    try:
        cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        print(f"\nERROR: el YAML está mal escrito.\n  Archivo: {p}\n"
              f"  Detalle: {e}\n", file=sys.stderr)
        sys.exit(1)
    api = cfg.get('api') or {}
    cred = {}
    if api.get('api_key'):
        cred['api_key'] = api['api_key']
    if api.get('mailto'):
        cred['mailto'] = api['mailto']
    return cred


def detectar_iteracion(csv_path: Path) -> int:
    """Deriva la iteración del nombre del CSV (regla C.6)."""
    m = re.search(r'WPB_BIBLM_(\d{3})_', csv_path.name)
    return int(m.group(1)) if m else 0


def setup_logging(output_dir: Path, iteracion: int) -> logging.Logger:
    """Log por iteración, con separador de corrida (regla D.2)."""
    logger = logging.getLogger('WPB_BIBLM_S01b')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    output_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    log_file = output_dir / f"WPB_BIBLM_{iteracion:03d}_S01b_ejecucion.log"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write('\n' + '=' * 78 + '\n')
        f.write(f"EJECUCIÓN {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write('=' * 78 + '\n')

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def confirmar_reescritura(csv_path: Path, n_pendientes: int,
                          force: bool) -> None:
    """El CSV se modifica en su lugar: se avisa antes (regla C.1)."""
    print("\n" + "=" * 78)
    print(f"AVISO: se va a REESCRIBIR {csv_path.name}")
    print("=" * 78)
    print(f"  Referencias sin resolver a completar: {n_pendientes:,}")
    print(f"  El archivo original se reemplaza solo si la escritura termina")
    print(f"  completa (se escribe primero un temporal).")
    print("=" * 78)

    if force:
        print("--force activo: se reescribe sin confirmación.\n")
        return

    if not sys.stdin.isatty():
        print("\nERROR: no hay terminal interactiva para confirmar (notebook,")
        print("cron, pipeline). Ejecución abortada; no se modificó nada.")
        print("Usar --force para ejecución no atendida.\n")
        sys.exit(1)

    if input("¿Reescribir? [s/N]: ").strip().lower() not in ('s', 'si', 'sí'):
        print("Ejecución abortada. No se modificó ningún archivo.\n")
        sys.exit(0)
    print()


# ═════════════════════════════════════════════════════════════════════════════
# LECTURA DEL CSV
# ═════════════════════════════════════════════════════════════════════════════

def _id_corto(oid: str) -> str:
    """https://openalex.org/W123 -> W123."""
    if not isinstance(oid, str):
        return ''
    m = re.search(r'(W\d+)\s*$', oid.strip())
    return m.group(1) if m else oid.strip()


def leer_pendientes(csv_path: Path, logger: logging.Logger) -> Tuple[Set[str], int, int]:
    """Recorre el CSV y devuelve (ids_sin_resolver, n_resueltos, n_menciones).

    Una referencia resuelta tiene 3 o 4 componentes separados por '~'; una sin
    resolver quedó como el ID a secas. El criterio es la ausencia de '~'.
    """
    if not csv_path.exists():
        print(f"\nERROR: no existe {csv_path.resolve()}\n", file=sys.stderr)
        sys.exit(1)

    # Un documento puede referenciar decenas de works: el campo supera con
    # holgura el límite por defecto de csv (131.072 caracteres).
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

    pendientes: Set[str] = set()
    resueltos: Set[str] = set()
    menciones = 0

    with open(csv_path, encoding='utf-8', newline='') as f:
        lector = csv.DictReader(f)
        columnas = lector.fieldnames or []
        if 'referenced_works' not in columnas:
            print("\nERROR: el CSV no tiene columna referenced_works.\n"
                  "  Fue generado sin campos_opcionales.referenced_works, o\n"
                  "  por una versión de S01 anterior a v0.8.\n"
                  f"  Columnas encontradas: {columnas}\n", file=sys.stderr)
            sys.exit(1)
        for fila in lector:
            for item in (fila.get('referenced_works') or '').split('|'):
                item = item.strip()
                if not item:
                    continue
                menciones += 1
                if '~' in item:
                    resueltos.add(item.split('~')[0])
                else:
                    pendientes.add(_id_corto(item))

    logger.info(f"CSV leído: {menciones:,} menciones de referencia")
    logger.info(f"  Ya resueltas: {len(resueltos):,} works distintos")
    logger.info(f"  Sin resolver: {len(pendientes):,} works distintos")
    return pendientes, len(resueltos), menciones


# ═════════════════════════════════════════════════════════════════════════════
# CONSULTA A OPENALEX
# ═════════════════════════════════════════════════════════════════════════════

def _sanear(texto: str) -> str:
    """Quita los separadores del formato de un valor que va dentro del campo.

    | ; ~ estructuran la columna; un nombre propio que los contenga rompería
    el parseo aguas abajo. Misma regla B.6 que aplica S01.
    """
    if not texto:
        return ''
    for ch in ('|', ';', '~'):
        texto = texto.replace(ch, ' ')
    return ' '.join(texto.split())


def resolver_con_expansion(ids: List[str], cred: Dict, lote_n: int,
                           logger: logging.Logger) -> Tuple[Dict[str, str], int]:
    """Consulta los IDs con corpus=all. Devuelve (cache, n_xpac).

    El cache mapea id -> 'Autor~Año' o 'Autor~Año~xpac' según is_xpac.
    Los IDs que la API no devuelva quedan fuera del cache.
    """
    total = len(ids)
    n_consultas = -(-total // lote_n)
    logger.info(f"Reconsultando {total:,} works con corpus=all "
                f"en {n_consultas:,} lotes de {lote_n}.")

    cache: Dict[str, str] = {}
    n_xpac = 0
    lotes_fallidos = 0
    clave_filtro = None

    for n, inicio in enumerate(range(0, total, lote_n), start=1):
        lote = ids[inicio:inicio + lote_n]

        def armar(clave: str) -> Dict:
            p = {'filter': f"{clave}:{'|'.join(lote)}",
                 'per_page': len(lote),
                 'corpus': 'all',
                 'select': 'id,publication_year,authorships,is_xpac'}
            p.update(cred)
            return p

        candidatas = [clave_filtro] if clave_filtro else list(CLAVES_FILTRO_ID)
        data = None

        for clave in candidatas:
            for intento in range(REINTENTOS):
                try:
                    resp = requests.get('https://api.openalex.org/works',
                                        params=armar(clave), timeout=60)
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Lote {n}/{n_consultas}, intento "
                                   f"{intento+1} falló (red): {e}")
                    time.sleep(BACKOFF_BASE ** intento)
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    if clave_filtro is None:
                        clave_filtro = clave
                        logger.info(f"Clave de filtro aceptada: '{clave}'.")
                    break

                # 429 y 5xx son transitorios: se reintentan con espera.
                # (El 504 de la corrida de S01 v0.8 caía en una rama sin
                # reintento; aquí sí lo tiene.)
                if resp.status_code == 429 or resp.status_code >= 500:
                    espera = BACKOFF_BASE ** intento
                    logger.warning(f"HTTP {resp.status_code} en lote "
                                   f"{n}/{n_consultas}. Esperando {espera}s "
                                   f"(intento {intento+1}/{REINTENTOS}).")
                    time.sleep(espera)
                    continue

                if resp.status_code == 400 and clave_filtro is None:
                    logger.debug(f"Filtro '{clave}' rechazado (400). "
                                 f"Se prueba la variante siguiente.")
                    break

                logger.error(f"Error {resp.status_code} en lote "
                             f"{n}/{n_consultas}: {resp.text[:200]}")
                break
            if data is not None:
                break

        if data is None and clave_filtro is None and n == 1:
            logger.error("Ninguna clave de filtro por ID fue aceptada. "
                         "No se completa nada.")
            return {}, 0

        if data is None:
            lotes_fallidos += 1
            logger.warning(f"Lote {n}/{n_consultas} descartado tras agotar "
                           f"los reintentos ({len(lote)} works).")
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
            valor = f"{_sanear(autor) or 's.a.'}~{anio if anio else 's.f.'}"
            if w.get('is_xpac') is True:
                valor += f"~{MARCA_XPAC}"
                n_xpac += 1
            cache[corto] = valor

        if n % 20 == 0 or n == n_consultas:
            logger.info(f"Lote {n}/{n_consultas}: {len(cache):,}/{total:,} "
                        f"resueltos")

        time.sleep(DEMORA)

    if lotes_fallidos:
        logger.warning(f"{lotes_fallidos} lote(s) fallaron tras los reintentos.")

    irrecuperables = total - len(cache)
    logger.info(f"Recuperados con corpus=all: {len(cache):,} de {total:,} "
                f"({100*len(cache)/total:.1f}%)")
    logger.info(f"  De ellos, del expansion corpus (is_xpac): {n_xpac:,}")
    if irrecuperables:
        logger.warning(
            f"{irrecuperables:,} works no los devuelve ninguna de las dos "
            f"vías. Probablemente fusionados (la API responde 301 al "
            f"consultarlos de a uno) o retirados. Conservan su ID sin autor "
            f"ni año y se volverán a consultar en cada reejecución."
        )
    return cache, n_xpac


# ═════════════════════════════════════════════════════════════════════════════
# REESCRITURA DEL CSV
# ═════════════════════════════════════════════════════════════════════════════

def reescribir_csv(csv_path: Path, cache: Dict[str, str],
                   logger: logging.Logger) -> Tuple[int, int]:
    """Reescribe referenced_works completando lo que el cache resolvió.

    Escribe primero un temporal en el MISMO directorio (os.replace es atómico
    solo dentro del mismo sistema de archivos) y reemplaza al final. Un fallo
    a mitad deja el original intacto.

    Las referencias ya resueltas no se tocan; las que el cache no resolvió
    conservan su ID a secas. Devuelve (menciones_completadas, filas_tocadas).
    """
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
    completadas = 0
    filas_tocadas = 0

    tmp = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='', delete=False,
        dir=str(csv_path.parent), prefix=csv_path.stem + '_tmp_', suffix='.csv')

    try:
        with open(csv_path, encoding='utf-8', newline='') as f_in:
            lector = csv.DictReader(f_in)
            escritor = csv.DictWriter(tmp, fieldnames=lector.fieldnames)
            escritor.writeheader()

            for fila in lector:
                crudo = fila.get('referenced_works') or ''
                if crudo:
                    salida = []
                    cambio = False
                    for item in crudo.split('|'):
                        item = item.strip()
                        if not item:
                            continue
                        if '~' in item:
                            salida.append(item)
                            continue
                        corto = _id_corto(item)
                        if corto in cache:
                            salida.append(f"{corto}~{cache[corto]}")
                            completadas += 1
                            cambio = True
                        else:
                            salida.append(corto)
                    fila['referenced_works'] = '|'.join(salida)
                    if cambio:
                        filas_tocadas += 1
                escritor.writerow(fila)
        tmp.close()
        shutil.move(tmp.name, str(csv_path))
    except Exception:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        logger.error("Fallo durante la reescritura. El CSV original NO se "
                     "modificó; el temporal se eliminó.")
        raise

    logger.info(f"CSV reescrito: {csv_path.name}")
    logger.info(f"  Menciones completadas: {completadas:,}")
    logger.info(f"  Filas modificadas: {filas_tocadas:,}")
    return completadas, filas_tocadas


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description='WPB_BIBLM S01b: completa las referencias que S01 dejó '
                    'sin resolver, reconsultándolas con corpus=all')
    ap.add_argument('--csv', default='output/WPB_BIBLM_000_v0.0.csv',
                    help='CSV principal de S01')
    ap.add_argument('--config', default='WPB_BIBLM_S01_export.yaml',
                    help='YAML de S01, de donde se toman api_key y mailto')
    ap.add_argument('--lote', type=int, default=LOTE_DEFECTO,
                    help=f'IDs por consulta (máx. {LOTE_DEFECTO})')
    ap.add_argument('--force', action='store_true',
                    help='Reescribe sin pedir confirmación')
    ap.add_argument('--dry-run', action='store_true',
                    help='Consulta y reporta, sin modificar el CSV')
    args = ap.parse_args()

    csv_path = Path(args.csv)
    iteracion = detectar_iteracion(csv_path)
    logger = setup_logging(csv_path.parent, iteracion)

    logger.info("=" * 78)
    logger.info(f"WPB_BIBLM S01b v0.1 iniciado (iteración {iteracion:03d})")
    logger.info("=" * 78)
    logger.info(f"CSV: {csv_path}")
    if args.dry_run:
        logger.info("MODO --dry-run: no se modificará ningún archivo.")

    cred = cargar_credenciales(args.config, logger)
    pendientes, n_resueltos, n_menciones = leer_pendientes(csv_path, logger)

    if not pendientes:
        logger.info("No hay referencias sin resolver. Nada que hacer.")
        return

    lote_n = max(1, min(args.lote, LOTE_DEFECTO))
    if not args.dry_run:
        confirmar_reescritura(csv_path, len(pendientes), args.force)

    # Ordenados por número de ID: agrupa identificadores contiguos, que es
    # como está distribuido el bloque del expansion corpus.
    ids = sorted(pendientes, key=lambda x: int(re.search(r'W(\d+)', x).group(1))
                 if re.search(r'W(\d+)', x) else 0)

    cache, n_xpac = resolver_con_expansion(ids, cred, lote_n, logger)

    if not cache:
        logger.warning("No se resolvió ningún work. El CSV queda igual.")
        return

    if args.dry_run:
        logger.info(f"--dry-run: se habrían completado {len(cache):,} works "
                    f"({n_xpac:,} del expansion corpus). CSV sin modificar.")
        return

    completadas, filas = reescribir_csv(csv_path, cache, logger)

    logger.info("=" * 78)
    logger.info("RESUMEN")
    logger.info(f"  Menciones totales en el CSV: {n_menciones:,}")
    logger.info(f"  Completadas en esta corrida: {completadas:,}")
    logger.info(f"  Works del expansion corpus, marcados '~{MARCA_XPAC}': "
                f"{n_xpac:,}")
    logger.info(f"  Sin resolver todavía: {len(pendientes) - len(cache):,} works")
    logger.info("=" * 78)


if __name__ == '__main__':
    main()
