#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPB_TESIS_S00_diagnostico5.py  --  v0.5

Quinta ronda. Aisla la causa del HTTP 400 que devolvieron las seis consultas
de la primera corrida de WPB_TESIS_S01_busqueda.py v0.1 (2026-08-29).

QUE PASO
  Las seis consultas fallaron con 400. Las cuatro que S01 interroga son
  titres.*, resumes.*, sujetsLibelle y sujetsRameauLibelle. Los dos ultimos
  estan verificados desde la ronda 3 y responden. Los dos primeros NO se
  verificaron nunca: la ronda 3 midio titres.fr y resumes.fr, con subcampo de
  idioma explicito, y la constante de mapeo del script se escribio con el
  comodin .*, tomado de la lista interna de campos ponderados de la API.
  Es una lógica escrita sobre un campo no verificado (regla B.3).

  El escapado queda descartado como causa: las consultas de conviviality,
  buen vivir y pluriverso no contienen ningun caracter escapado y tambien
  devolvieron 400.

HIPOTESIS A CONTRASTAR

  H1  El comodin en el nombre de campo no es sintaxis admitida en q, y hay
      que enumerar los subcampos de idioma o usar el campo base.

  H2  El asterisco debe escaparse. La documentacion de Abes escribe el campo
      como  resumes.\\*:(XXX)  con barra invertida, y no esta claro si es
      escapado de Markdown o parte de la sintaxis. El asterisco figura ademas
      en la lista de caracteres significativos de Elasticsearch que la propia
      documentacion manda escapar.

  H3  El campo base sin sufijo responde.

METODO
  Cada forma se consulta con un termino de total conocido, para poder
  comparar. Se registra el CODIGO HTTP ademas del total: un 400 y un 0 son
  resultados distintos y confundirlos fue lo que llevo a diagnosticar mal.

  Controles conocidos de la ronda 3, con status:(soutenue) ausente:
      titres.fr:(decolonial)   = 44
      resumes.fr:(decolonial)  = 165
      sujetsLibelle:(decolonial) = 63

  Se prueba ademas una consulta con el filtro de status y otra sin el, para
  descartar que el 400 venga de combinar la clausula de campos con el AND del
  filtro y no de los campos en si.

USO
    python3 WPB_TESIS_S00_diagnostico5.py --contacto tu@correo.org

Dependencia externa: requests

Fuentes:
  Abes (2026). Le moteur de recherche theses.fr. Documentation.
      https://documentation.abes.fr/aidethesesfr/index.html
  Datos bajo Licence Ouverte 2.0 (Etalab).
  Atribucion: Agence bibliographique de l'enseignement superieur.
"""

import argparse
import json
import logging
import sys
import time
from urllib.parse import urlencode, quote

import requests

VERSION = "0.5"
BASE_URL = "https://theses.fr/api/v1/theses/recherche/"
PAUSA = 1.0
TIMEOUT = 30

TERMINO = "decolonial"
LOG_PATH = "WPB_TESIS_S00_diagnostico5.log"


def configurar_log(contacto):
    """encoding explicito (regla E.1); separador con timestamp (regla D.2)."""
    fh = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    sh = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    log = logging.getLogger()
    log.setLevel(logging.INFO)
    log.handlers = [fh, sh]
    log.info("=" * 70)
    log.info("WPB_TESIS_S00_diagnostico5 v%s -- inicio", VERSION)
    return log


def consultar(q, contacto, log):
    """Devuelve (codigo_http, totalHits).

    A diferencia de las rondas anteriores, aqui se devuelve el codigo HTTP:
    distinguir un 400 de un 0 es justo lo que esta ronda tiene que medir.
    """
    url = BASE_URL + "?" + urlencode(
        {"q": q, "debut": 0, "nombre": 1}, quote_via=quote)
    headers = {
        "User-Agent": f"WPB_TESIS/{VERSION} (proyecto TRANSUR; {contacto})",
        "Accept": "application/json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        log.error("Fallo de red en [%s]: %s", q, e)
        return None, None
    if r.status_code != 200:
        return r.status_code, None
    try:
        return 200, r.json().get("totalHits")
    except json.JSONDecodeError:
        return 200, None


def main():
    ap = argparse.ArgumentParser(
        description="Aisla la causa del 400 en las consultas de S01")
    ap.add_argument("--contacto", default="sin-contacto-declarado")
    args = ap.parse_args()
    log = configurar_log(args.contacto)

    t = TERMINO
    st = "status:(soutenue)"

    # (bloque, etiqueta, consulta)
    pruebas = [
        # --- H1/H2/H3 sobre titres ---
        ("titres", "titres.fr (control ronda 3)", f"titres.fr:({t})"),
        ("titres", "titres.* (el que fallo)",     f"titres.*:({t})"),
        ("titres", "titres.\\* (asterisco escapado)", f"titres.\\*:({t})"),
        ("titres", "titres (campo base)",         f"titres:({t})"),

        # --- H1/H2/H3 sobre resumes ---
        ("resumes", "resumes.fr (control ronda 3)", f"resumes.fr:({t})"),
        ("resumes", "resumes.* (el que fallo)",     f"resumes.*:({t})"),
        ("resumes", "resumes.\\* (escapado)",       f"resumes.\\*:({t})"),
        ("resumes", "resumes (campo base)",         f"resumes:({t})"),

        # --- el AND con el filtro de status ---
        # Descarta que el 400 venga de combinar la clausula con el filtro y
        # no de los campos en si.
        ("filtro", "campo verificado sin status",
         f"sujetsLibelle:({t})"),
        ("filtro", "campo verificado CON status",
         f"(sujetsLibelle:({t})) AND {st}"),
        ("filtro", "dos campos verificados con status",
         f"(sujetsLibelle:({t}) OR sujetsRameauLibelle:({t})) AND {st}"),

        # --- escapado dentro de comillas ---
        # No puede ser la causa del fallo general, pero conviene saber si el
        # guion escapado dentro de una frase es sintaxis valida antes de
        # dejarlo en el diccionario.
        ("escape", "frase sin caracteres especiales",
         'sujetsLibelle:("de colonial")'),
        ("escape", "guion escapado dentro de comillas",
         'sujetsLibelle:("de\\-colonial")'),
        ("escape", "guion sin escapar dentro de comillas",
         'sujetsLibelle:("de-colonial")'),
    ]

    resultados = []
    for bloque, etiqueta, q in pruebas:
        code, total = consultar(q, args.contacto, log)
        resultados.append((bloque, etiqueta, q, code, total))
        log.info("%-8s | %-34s | HTTP %s | total=%s",
                 bloque, etiqueta, code, total)
        time.sleep(PAUSA)

    print("\n" + "=" * 78)
    print("AISLAMIENTO DEL HTTP 400")
    print("=" * 78)
    actual = None
    for bloque, etiqueta, q, code, total in resultados:
        if bloque != actual:
            print(f"\n[{bloque}]")
            actual = bloque
        tot = "-" if total is None else f"{total:,}"
        print(f"    {etiqueta:<34} HTTP {str(code):<5} {tot:>10}")

    print("\n" + "-" * 78)
    print("COMO LEERLO")
    print("-" * 78)
    print("""
titres / resumes
    La forma que devuelva HTTP 200 con un total distinto de cero es la que
    debe ir en la constante de mapeo de S01.

    Si titres.fr responde y titres.* da 400  -> H1: el comodin no es sintaxis
        admitida en q. S01 debe enumerar los subcampos de idioma, y esa lista
        pasa a ser un parametro del YAML.
    Si titres.\\* responde                    -> H2: el asterisco hay que
        escaparlo, y basta corregir la constante.
    Si titres (base) responde con un total >= al de titres.fr -> H3: el campo
        base cubre todos los idiomas y es la opcion mas simple.

    Si mas de una forma responde, se elige por el TOTAL: la que recupere mas
    cubre mas subcampos. Un total identico al de titres.fr sugiere que solo
    esta mirando el frances.

filtro
    Si las tres responden 200, el AND con status no tiene nada que ver con el
    400 y la causa esta enteramente en los campos con comodin.
    Si la que lleva status falla, el problema es la combinacion y hay que
    revisar como se compone q en construir_filtros().

escape
    Si el guion escapado da 400 y el sin escapar responde, dentro de comillas
    NO hay que escapar: la frase ya es literal. En ese caso, preparar_termino()
    debe escapar solo cuando tipo_busqueda=default.
    Si ambos responden con el mismo total, el escapado es inocuo y se deja.

NOTA  Un 400 y un 0 son resultados distintos. Confundirlos fue lo que hizo
      que el comodin llegara al script sin verificar.
""")
    log.info("Fin de la quinta ronda. Registro en %s", LOG_PATH)


if __name__ == "__main__":
    main()
