"""
WPB_BIBLM_D01_diag_refs.py v0.1

Diagnóstico: por qué el 8,2% de los works referenciados no se resolvió en la
corrida de S01 v0.8 (13.159 de 160.778, concentrados en un bloque contiguo de
identificadores, lotes 3.020-3.180).

NO modifica ningún archivo. Solo lee el CSV de S01 y consulta la API.

HIPÓTESIS A CONTRASTAR
----------------------
Los works no resueltos pertenecen al expansion corpus de OpenAlex (~190M
registros incorporados en la actualización Walden, sobre todo datasets y
registros de un solo repositorio). La API los excluye por defecto
(corpus=core) y hay que pedirlos con corpus=all.
    Documentación: atributo is_xpac y parámetro corpus en
    help.openalex.org, "Attributes - Works" y "LLM Quick Reference".

La forma del hueco -un rango contiguo de IDs, no una muestra dispersa- es
lo que sugiere esta explicación: el expansion corpus se cargó en bloque y
recibió identificadores correlativos.

ALTERNATIVAS SI LA HIPÓTESIS NO SE SOSTIENE
-------------------------------------------
  - Works fusionados: /works/{id} responde 301 y redirige al superviviente.
  - Works inexistentes o retirados: responde 404.
Ambos casos producirían dispersión, no un bloque, pero se comprueban igual.

QUÉ HACE
--------
  1. Lee referenced_works del CSV y separa los IDs sin resolver (los que
     quedaron con un solo componente, sin '~').
  2. Toma una muestra del extremo alto del rango, que es donde está el hueco.
  3. Consulta esa misma muestra dos veces: con corpus por defecto y con
     corpus=all. Compara cuántos devuelve cada una.
  4. Si ninguna de las dos los devuelve, consulta tres IDs sueltos por
     /works/{id} sin seguir redirecciones, para distinguir 301 de 404.

USO
---
    python3 WPB_BIBLM_D01_diag_refs.py --csv output/WPB_BIBLM_000_v0.0.csv \
        --config WPB_BIBLM_S01_export.yaml

    --n            tamaño de la muestra (default 50, tope de un filtro OR)
    --muestra      alto (default) | bajo | aleatorio
                   'alto' toma los IDs mayores, que es donde el log ubica el
                   hueco; 'aleatorio' sirve de control.

Costo: 2 consultas de filtro y hasta 3 lookups por ID. Despreciable.
"""

import re
import csv
import sys
import json
import random
import argparse
from pathlib import Path

import requests
import yaml

CSV_DEFECTO = 'output/WPB_BIBLM_000_v0.0.csv'
YAML_DEFECTO = 'WPB_BIBLM_S01_export.yaml'


def cargar_credenciales(yaml_path):
    """Toma api_key y mailto del YAML de S01, si existe."""
    p = Path(yaml_path)
    if not p.exists():
        print(f"[aviso] No se encontró {p}; se consulta sin api_key.")
        return {}
    cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    api = cfg.get('api') or {}
    cred = {}
    if api.get('api_key'):
        cred['api_key'] = api['api_key']
    if api.get('mailto'):
        cred['mailto'] = api['mailto']
    return cred


def extraer_ids(csv_path):
    """Separa los IDs de referenced_works en resueltos y sin resolver.

    Un ID resuelto tiene tres componentes (W123~Autor~2019); uno sin resolver
    quedó como 'W123' a secas. El criterio es la ausencia de '~'.
    """
    sin_resolver, resueltos = set(), set()
    p = Path(csv_path)
    if not p.exists():
        print(f"\nERROR: no existe {p.resolve()}\n", file=sys.stderr)
        sys.exit(1)

    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    with open(p, encoding='utf-8', newline='') as f:
        lector = csv.DictReader(f)
        if 'referenced_works' not in (lector.fieldnames or []):
            print("\nERROR: el CSV no tiene columna referenced_works.\n"
                  f"  Columnas: {lector.fieldnames}\n", file=sys.stderr)
            sys.exit(1)
        for fila in lector:
            for item in (fila.get('referenced_works') or '').split('|'):
                item = item.strip()
                if not item:
                    continue
                if '~' in item:
                    resueltos.add(item.split('~')[0])
                else:
                    sin_resolver.add(item)
    return sin_resolver, resueltos


def clave_num(oid):
    """W2741809807 -> 2741809807, para ordenar por rango de identificador."""
    m = re.search(r'W(\d+)', oid)
    return int(m.group(1)) if m else 0


def consultar(ids, cred, corpus=None):
    """Un filtro OR con la muestra. Devuelve los IDs que la API sí trae."""
    params = {
        'filter': f"openalex:{'|'.join(ids)}",
        'per_page': len(ids),
        'select': 'id,publication_year,is_xpac',
    }
    params.update(cred)
    if corpus:
        params['corpus'] = corpus
    try:
        r = requests.get('https://api.openalex.org/works', params=params,
                         timeout=60)
    except requests.exceptions.RequestException as e:
        return None, f"fallo de red: {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    datos = r.json().get('results') or []
    return datos, None


def lookup_individual(oid, cred):
    """/works/{id} sin seguir redirecciones: distingue 301 de 404."""
    try:
        r = requests.get(f'https://api.openalex.org/works/{oid}',
                         params=cred, timeout=30, allow_redirects=False)
    except requests.exceptions.RequestException as e:
        return f"fallo de red: {e}"
    if r.status_code == 301:
        return f"301 fusionado -> {r.headers.get('Location', '?')}"
    if r.status_code == 404:
        return "404 no existe"
    if r.status_code == 200:
        try:
            d = r.json()
            return (f"200 existe (is_xpac={d.get('is_xpac')}, "
                    f"año={d.get('publication_year')})")
        except json.JSONDecodeError:
            return "200 pero la respuesta no es JSON"
    return f"HTTP {r.status_code}"


def main():
    ap = argparse.ArgumentParser(
        description='Diagnóstico de referencias no resueltas de S01 v0.8')
    ap.add_argument('--csv', default=CSV_DEFECTO)
    ap.add_argument('--config', default=YAML_DEFECTO)
    ap.add_argument('--n', type=int, default=50,
                    help='Tamaño de muestra (máx. 50, tope del filtro OR)')
    ap.add_argument('--muestra', choices=['alto', 'bajo', 'aleatorio'],
                    default='alto')
    args = ap.parse_args()
    n = min(args.n, 50)

    cred = cargar_credenciales(args.config)
    sin_resolver, resueltos = extraer_ids(args.csv)

    print("=" * 74)
    print("DIAGNÓSTICO DE REFERENCIAS NO RESUELTAS")
    print("=" * 74)
    print(f"CSV: {args.csv}")
    print(f"IDs distintos sin resolver: {len(sin_resolver):,}")
    print(f"IDs distintos resueltos:    {len(resueltos):,}")
    if not sin_resolver:
        print("\nNo hay IDs sin resolver. Nada que diagnosticar.")
        return

    ordenados = sorted(sin_resolver, key=clave_num)
    print(f"Rango de los no resueltos:  {ordenados[0]} .. {ordenados[-1]}")
    if resueltos:
        r_ord = sorted(resueltos, key=clave_num)
        print(f"Rango de los resueltos:     {r_ord[0]} .. {r_ord[-1]}")

    if args.muestra == 'alto':
        muestra = ordenados[-n:]
    elif args.muestra == 'bajo':
        muestra = ordenados[:n]
    else:
        muestra = random.sample(ordenados, min(n, len(ordenados)))
    print(f"\nMuestra ({args.muestra}): {len(muestra)} IDs, "
          f"{muestra[0]} .. {muestra[-1]}")

    print("\n" + "-" * 74)
    print("PRUEBA 1 — misma consulta que hizo S01 (corpus por defecto)")
    print("-" * 74)
    d1, err1 = consultar(muestra, cred)
    if err1:
        print(f"  ERROR: {err1}")
    else:
        print(f"  Devueltos: {len(d1)} de {len(muestra)}")

    print("\n" + "-" * 74)
    print("PRUEBA 2 — misma muestra con corpus=all")
    print("-" * 74)
    d2, err2 = consultar(muestra, cred, corpus='all')
    if err2:
        print(f"  ERROR: {err2}")
    else:
        print(f"  Devueltos: {len(d2)} de {len(muestra)}")
        xpac = sum(1 for w in d2 if w.get('is_xpac') is True)
        print(f"  De ellos, con is_xpac=true: {xpac}")

    n1 = len(d1) if d1 is not None else -1
    n2 = len(d2) if d2 is not None else -1

    print("\n" + "=" * 74)
    print("LECTURA")
    print("=" * 74)
    if n2 > n1 and n2 >= len(muestra) * 0.8:
        print("  corpus=all los recupera y la consulta por defecto no.")
        print("  HIPÓTESIS CONFIRMADA: expansion corpus.")
        print("  Corrección: agregar corpus=all al reintento de los no")
        print("  resueltos. Nota analítica: el expansion corpus tiene menor")
        print("  calidad de metadatos según OpenAlex; conviene marcar en el")
        print("  CSV qué referencias provienen de ahí (is_xpac).")
    elif n2 > n1:
        print(f"  corpus=all recupera más ({n2} vs {n1}), pero no todos.")
        print("  Explicación PARCIAL: hay al menos una segunda causa.")
    elif n1 == 0 and n2 == 0:
        print("  Ninguna de las dos los devuelve. NO es el expansion corpus.")
        print("  Se comprueban tres IDs sueltos para distinguir fusionado")
        print("  (301) de inexistente (404):")
        for oid in muestra[:3]:
            print(f"    {oid}: {lookup_individual(oid, cred)}")
    else:
        print(f"  Resultado inesperado: por defecto {n1}, corpus=all {n2}.")
        print("  Si la consulta por defecto SÍ los devuelve ahora, el fallo")
        print("  original fue transitorio y basta reintentar sin cambios.")
        for oid in muestra[:3]:
            print(f"    {oid}: {lookup_individual(oid, cred)}")

    print("\n" + "-" * 74)
    print("CONTROL — muestra aleatoria de RESUELTOS por la misma vía")
    print("-" * 74)
    if resueltos:
        ctrl = random.sample(sorted(resueltos), min(n, len(resueltos)))
        d3, err3 = consultar(ctrl, cred)
        if err3:
            print(f"  ERROR: {err3}")
        else:
            print(f"  Devueltos: {len(d3)} de {len(ctrl)}")
            print("  (Debe ser alto. Si no lo es, el problema no está en el")
            print("   corpus sino en la consulta misma.)")
    print()


if __name__ == '__main__':
    main()
