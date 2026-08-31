"""
WPB_BIBLM_D02_diag_busqueda.py v0.3

Compara cuántos works devuelve OpenAlex para cada palabra clave del
diccionario según el modo de búsqueda, con los MISMOS filtros que aplica S01,
y desglosado por país.

Sirve para decidir qué debe hacer tipo_busqueda, hoy declarado en el
diccionario pero no leído por el script (regla A.1): S01 usa siempre `search`
con los términos entrecomillados, cualquiera sea el valor de la columna.

CAMBIOS v0.3
    - search.semantic: compara tres formas de pasar los sinónimos (solo el
      keyword, palabras sueltas, frase de lenguaje natural) para verificar
      si el modelo de embedding los integra como concepto o los trata como
      términos independientes. Determina cómo implementarlo en S01.

CAMBIOS v0.2
    - Lee el diccionario de palabras clave y los filtros del YAML, en vez de
      una lista fija de términos sin filtrar. Los conteos ya son comparables
      con los de una corrida real de S01.
    - Desglose por país: FR, DE y la combinación FR|DE que usa S01.
    - El diccionario se lee con load_keywords_csv() importada de S01, no con
      una copia: si el parseo cambia allá, cambia acá (regla G.7).

MODOS COMPARADOS
    search sin comillas   stemming y stopwords; palabras sueltas
    search con comillas   frase, pero DESPUÉS del stemming  <- lo que hace S01
    search.exact          sin stemming
    search.semantic       vecinos por similitud de embedding
      Documentación: developers.openalex.org/guides/searching (2026-08-26).
      Solo se admite UN parámetro de búsqueda por consulta.
      search.semantic no admite filtrar por country_code, así que en ese modo
      la columna por país se omite.

COSTO
    Una llamada por palabra clave, modo y país, con per_page=1 y select=id:
    se lee meta.count, no los resultados. Las consultas con search cuestan
    1 USD por cada 1.000 llamadas, diez veces una de filtro. Con 6 palabras
    clave son ~60 llamadas, unos 0,06 USD. El script imprime la estimación
    antes de empezar.

USO
    python3 WPB_BIBLM_D02_diag_busqueda.py --config WPB_BIBLM_S01-export.yaml
    python3 WPB_BIBLM_D02_diag_busqueda.py --keywords "buen vivir" pluriverso
    python3 WPB_BIBLM_D02_diag_busqueda.py --sin-sinonimos

No escribe ningún archivo.
"""

import sys
import time
import logging
import argparse
from pathlib import Path

import requests
import yaml

URL = 'https://api.openalex.org/works'
PAISES = [('FR', ['fr']), ('DE', ['de']), ('FR|DE', ['fr', 'de'])]


def cargar_yaml(ruta):
    p = Path(ruta)
    if not p.exists():
        print(f"\nERROR: no se encontró {p.resolve()}\n"
              f"  Directorio de trabajo: {Path.cwd()}\n", file=sys.stderr)
        sys.exit(1)
    try:
        return yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        print(f"\nERROR: YAML mal escrito.\n  {p}\n  {e}\n", file=sys.stderr)
        sys.exit(1)


def cargar_diccionario(cfg, logger):
    """Usa el lector de S01 para que el parseo sea el mismo (regla G.7)."""
    ruta = cfg.get('diccionario_palabras_clave', 'palabras_clave_biblm.csv')
    try:
        from WPB_BIBLM_S01_export import load_keywords_csv
    except ImportError as e:
        print(f"\nERROR: no se pudo importar WPB_BIBLM_S01_export.\n"
              f"  Debe estar en el mismo directorio. Detalle: {e}\n",
              file=sys.stderr)
        sys.exit(1)
    return load_keywords_csv(ruta, logger)


def filtro_base(filtros, paises):
    """Mismo filtro que arma S01.fetch_openalex, con el país como parámetro."""
    partes = [f"publication_year:{filtros['periodo_inicio']}-{filtros['periodo_fin']}"]
    if paises:
        partes.append(f"institutions.country_code:{'|'.join(paises)}")
    tipos = filtros.get('tipos_documento', [])
    if tipos:
        partes.append(f"type:{'|'.join(tipos)}")
    return ','.join(partes)


def contar(params, cred):
    """Devuelve (meta.count, error)."""
    p = dict(params, per_page=1, select='id')
    p.update(cred)
    try:
        r = requests.get(URL, params=p, timeout=60)
    except requests.exceptions.RequestException as e:
        return None, str(e)[:20]
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    return r.json().get('meta', {}).get('count'), None


def celda(n, err, ancho=15):
    return f"{(f'{n:,}' if n is not None else err):>{ancho}}"


def main():
    ap = argparse.ArgumentParser(
        description='Compara modos de búsqueda de OpenAlex con los filtros de S01')
    ap.add_argument('--config', default='WPB_BIBLM_S01-export.yaml')
    ap.add_argument('--keywords', nargs='+', default=None,
                    help='Solo estas palabras clave (por defecto, todas)')
    ap.add_argument('--sin-sinonimos', action='store_true',
                    help='Consulta solo el término principal')
    args = ap.parse_args()

    logger = logging.getLogger('D02')
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.WARNING)   # el lector de S01 loguea en INFO

    cfg = cargar_yaml(args.config)
    api = cfg.get('api') or {}
    cred = {k: api[k] for k in ('api_key', 'mailto') if api.get(k)}
    if not cred.get('api_key'):
        print("[aviso] Sin api_key en el YAML: cuota diaria menor.\n")

    filtros = cfg.get('filtros') or {}
    if 'periodo_inicio' not in filtros or 'periodo_fin' not in filtros:
        print("\nERROR: el YAML no declara filtros.periodo_inicio ni "
              "filtros.periodo_fin.\n", file=sys.stderr)
        sys.exit(1)

    keywords = cargar_diccionario(cfg, logger)
    if args.keywords:
        pedidas = {k.lower() for k in args.keywords}
        keywords = [k for k in keywords if k['keyword'].lower() in pedidas]
        if not keywords:
            print("\nERROR: ninguna de esas palabras clave está en el "
                  "diccionario.\n", file=sys.stderr)
            sys.exit(1)

    # 3 modos x 3 países, más 3 consultas de search.semantic
    n_llamadas = len(keywords) * (3 * len(PAISES) + 3)
    print(f"Palabras clave: {len(keywords)}   "
          f"Filtros: {filtros['periodo_inicio']}-{filtros['periodo_fin']}, "
          f"tipos [{','.join(filtros.get('tipos_documento', [])) or 'todos'}]")
    print(f"Llamadas a la API: {n_llamadas} (~{n_llamadas/1000:.3f} USD)\n")

    for kw in keywords:
        terminos = [kw['keyword']]
        if not args.sin_sinonimos:
            terminos += kw.get('sinonimos', [])

        con_comillas = '(' + ' OR '.join(f'"{t}"' for t in terminos) + ')'
        sin_comillas = '(' + ' OR '.join(terminos) + ')'

        print("=" * 72)
        print(f"{kw['keyword']}   (+{len(terminos)-1} sinónimos | "
              f"tipo_busqueda declarado: {kw.get('tipo_busqueda', '?')})")
        print("=" * 72)
        print(f"{'modo':<24}" + ''.join(f"{p:>15}" for p, _ in PAISES))
        print("-" * 72)

        for nombre, clave, valor in [
            ('search sin comillas', 'search', sin_comillas),
            ('search con comillas', 'search', con_comillas),   # lo que hace S01
            ('search.exact', 'search.exact', con_comillas),
        ]:
            fila = f"{nombre:<24}"
            for _, codigos in PAISES:
                n, err = contar({clave: valor,
                                 'filter': filtro_base(filtros, codigos)}, cred)
                fila += celda(n, err)
                time.sleep(0.2)
            print(fila)

        # search.semantic — sin filtro por country_code (API no lo admite).
        # Se comparan tres formas de pasar los sinónimos para verificar si el
        # modelo de embedding los integra como concepto ampliado o los trata
        # como palabras sueltas. Si los conteos convergen, tiene sentido pasar
        # los sinónimos como frase de lenguaje natural en S01.
        print(f"\n  search.semantic (sin filtro de país):")
        sem_consultas = [
            ('solo keyword',      kw['keyword']),
            ('palabras sueltas',  ' '.join(terminos)),
            ('frase natural',     ', '.join(terminos[:3])),  # coma como en lenguaje natural
        ]
        for label, valor in sem_consultas:
            n, err = contar({'search.semantic': valor,
                             'filter': filtro_base(filtros, None)}, cred)
            print(f"    {label:<20}{celda(n, err)}   query: \"{valor[:55]}{'...' if len(valor)>55 else ''}\"")
            time.sleep(0.2)
        print()

    print("""CÓMO LEER/INTERPETAR LOS RESULTADOS      
  'sin comillas' == 'con comillas'  -> las comillas no cambian nada: S01 está
                                       recuperando por palabras sueltas.
  'con comillas' <  'sin comillas'  -> las comillas sí restringen a la frase.
  'search.exact' <  'con comillas'  -> el stemming estaba ampliando el corpus.
> La fila 'search con comillas' es la que corresponde al default de S01.
> search.semantic devuelve vecinos por similitud de embedding: su conteo no es comparable con los otros tres.
  Las tres formas del bloque semantic se leen así:
    solo keyword == palabras sueltas == frase natural  -> sinonimos no aportan
    frase natural  > solo keyword                      -> sinonimos amplian el concepto
    frase natural  < solo keyword                      -> sinonimos restringen
  Si frase natural >= solo keyword, vale la pena pasar los sinonimos como
  concepto expandido en S01; si no, usar solo el keyword.

  NOTA: Decimos STEMMING por el proceo que reduce las palabras a su raíz para recoger
  variantes morfológicas como una misma cosa: 
    "decolonial", "decolonization", "decolonizing" → "decolon". 
    Así una búsqueda de "decolonial" devuelve también documentos que usan 
    "decolonize" o "decolonization". 
    OpenAlex lo aplica por defecto en search; search.exact desactiva el stemming. 
""")


if __name__ == '__main__':
    main()
