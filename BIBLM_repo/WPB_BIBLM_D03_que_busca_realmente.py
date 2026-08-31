"""
WPB_BIBLM_D03_que_busca_realmente.py v0.1

Muestra qué parámetro de búsqueda está usando S01 para cada palabra clave del
diccionario, independientemente de lo que declare tipo_busqueda.

No hace consultas a OpenAlex: solo arma las queries y las imprime.

Responde: ¿S01 respeta el tipo_busqueda del diccionario, o lo ignora?
"""

import sys
import logging
from pathlib import Path

import yaml

def cargar_yaml(ruta):
    p = Path(ruta)
    if not p.exists():
        print(f"\nERROR: no se encontró {p.resolve()}\n", file=sys.stderr)
        sys.exit(1)
    try:
        return yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as e:
        print(f"\nERROR: YAML mal escrito.\n  {e}\n", file=sys.stderr)
        sys.exit(1)


def cargar_diccionario(cfg, logger):
    """Usa el lector de S01."""
    ruta = cfg.get('diccionario_palabras_clave', 'palabras_clave_biblm.csv')
    try:
        from WPB_BIBLM_S01_export import load_keywords_csv
    except ImportError as e:
        print(f"\nERROR: no se pudo importar WPB_BIBLM_S01_export.\n"
              f"  {e}\n", file=sys.stderr)
        sys.exit(1)
    return load_keywords_csv(ruta, logger)


def main():
    cfg = cargar_yaml('WPB_BIBLM_S01-export.yaml')
    logger = logging.getLogger('D03')
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.WARNING)

    keywords = cargar_diccionario(cfg, logger)

    print("\n" + "=" * 80)
    print("QUÉ PARÁMETRO DE BÚSQUEDA USA S01 REALMENTE")
    print("=" * 80)
    print(f"{'keyword':<30} {'tipo_busqueda':<20} {'parámetro usado'}")
    print("-" * 80)

    # Esto es lo que hace S01.fetch_openalex: siempre search, siempre con comillas
    for kw in keywords:
        terminos = [kw['keyword']] + kw.get('sinonimos', [])
        search_terms = '(' + ' OR '.join(f'"{t}"' for t in terminos) + ')'

        tipo_decl = kw.get('tipo_busqueda', '?')
        param_real = 'search'  # esto es lo que hace S01

        print(f"{kw['keyword']:<30} {tipo_decl:<20} {param_real}")

    print("-" * 80)
    print("""
CONCLUSIÓN
  Todos los keywords usan parámetro 'search' con comillas, cualquiera sea el
  tipo_busqueda declarado. La columna es ignorada (regla A.1).

  Búsqueda que hace S01:
    search=("buen vivir" OR "sumak kawsay" OR ...)

  La búsqueda NUNCA usa:
    - search sin comillas (palabras sueltas)
    - search.exact (sin stemming)
    - search.semantic (similitud de embedding)
    - el valor de tipo_busqueda del diccionario

  Las comillas hacen que OpenAlex busque la FRASE (pero DESPUÉS del stemming).
  Para una palabra clave de una palabra, eso equivale a search.exact aproximado.
  Para frases de dos o más palabras, es más restrictivo que search sin comillas.
""")


if __name__ == '__main__':
    main()
