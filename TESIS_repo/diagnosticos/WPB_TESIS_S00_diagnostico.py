#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPB_TESIS_S00_diagnostico.py  --  v0.1

Verificacion empirica del comportamiento de la API de busqueda de theses.fr.
NO recupera corpus. Solo lanza consultas de conteo y compara los totales.

Resuelve cinco preguntas que no se pueden contestar leyendo la documentacion,
y de las que depende como se escribe WPB_TESIS_S01_busqueda.py:

  P1  Un termino multipalabra entrecomillado, se comporta distinto que sin
      comillas? El codigo fuente de la API llama a quoteFieldSuffix(".exact"),
      de modo que las frases entrecomilladas se enrutan a un subcampo .exact.
      Sabemos que ese subcampo existe para discipline y etabSoutenanceN
      (aparecen asi en la configuracion de facetas). NO sabemos si existe para
      sujetsLibelle, titres.* ni resumes.*. Si no existe, la consulta
      entrecomillada devuelve cero sin error.
      Consecuencia: define el valor de tipo_busqueda en los diccionarios.

  P2  El subcampo .exact normaliza acentos? La documentacion de Abes dice que
      "los acentos se neutralizan", pero eso describe el campo analizado, no
      necesariamente el .exact, que suele ser de tipo keyword sin normalizar.
      Consecuencia: define si hacen falta entradas separadas para decolonial
      y decolonial con tilde en los diccionarios.

  P3  El subcampo .exact normaliza mayusculas? Mismo razonamiento que P2.
      Consecuencia: define si Quilombo y quilombo son dos entradas o una.

  P4  titrePrincipal responde como campo indexado? Esta documentado por Abes
      como interrogable, pero NO figura en la lista de campos ponderados de
      buildQuery(), que usa titres.*. Si no existe como campo independiente,
      titrePrincipal:(x) devuelve cero sin error.
      Consecuencia: define que campos se ofrecen en campos_palabras_clave.

  P5  dateInsertionDansES responde? De el depende el modo incremental de S01
      (buscar solo lo indexado desde la corrida anterior). Si no responde,
      la busqueda incremental devuelve cero en silencio y pareceria que no
      hay tesis nuevas.

INTERPRETACION DE LOS RESULTADOS
  Un total de 0 no prueba que el campo no exista: puede que no haya tesis que
  cumplan la condicion. Por eso cada prueba compara contra una consulta de
  control que SI debe devolver resultados. Lo que se interpreta es la relacion
  entre ambos totales, no el valor absoluto.

USO
    python3 WPB_TESIS_S00_diagnostico.py
    python3 WPB_TESIS_S00_diagnostico.py --contacto tu@correo.org

Dependencia externa: requests

Fuentes:
  Abes (2026). Le moteur de recherche theses.fr. Documentation.
      https://documentation.abes.fr/aidethesesfr/index.html
  abes-esr/theses-api-recherche, rama develop. Consultado 2026-08-28.
  Datos bajo Licence Ouverte 2.0 (Etalab).
  Atribucion: Agence bibliographique de l'enseignement superieur.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from urllib.parse import urlencode, quote

import requests

VERSION = "0.1"
BASE_URL = "https://theses.fr/api/v1/theses/recherche/"

# Pausa entre peticiones, en segundos. Conservador: la API no declara limite
# de tasa en ninguno de sus OpenAPI ni en la documentacion de Abes, asi que
# se asume el valor prudente y no se paraleliza.
PAUSA = 1.0

TIMEOUT = 30

# Terminos de prueba. Se eligen del diccionario real del proyecto para que el
# diagnostico mida el caso de uso, no un caso de laboratorio.
#   MULTI  : termino de varias palabras, sin acentos ni mayusculas -> P1
#   ACENTO : mismo termino con y sin tilde                          -> P2
#   CAJA   : mismo termino con y sin mayuscula inicial              -> P3
MULTI = "buen vivir"
ACENTO_CON = "décolonial"
ACENTO_SIN = "decolonial"
CAJA_ALTA = "Quilombo"
CAJA_BAJA = "quilombo"

# Campo sobre el que se prueban P1-P3. Es el campo de palabras clave libres,
# uno de los que el proyecto va a interrogar de verdad.
CAMPO_PRUEBA = "sujetsLibelle"

LOG_PATH = "WPB_TESIS_S00_diagnostico.log"


def configurar_log(contacto):
    """Log a archivo y a consola. encoding explicito (regla E.1: FileHandler
    no lo declara por defecto y aborta en Windows ante caracteres no cp1252).
    Separador con timestamp al abrir en modo append (regla D.2)."""
    fh = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    sh = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    log = logging.getLogger()
    log.setLevel(logging.INFO)
    log.addHandler(fh)
    log.addHandler(sh)
    log.info("=" * 70)
    log.info("WPB_TESIS_S00_diagnostico v%s -- inicio", VERSION)
    log.info("Contacto declarado en User-Agent: %s", contacto)
    return log


def consultar(q, contacto, log):
    """Lanza una consulta y devuelve totalHits, o None si fallo.

    nombre=1 porque solo interesa el contador: pedir mas registros no aporta
    nada al diagnostico y carga el servicio sin motivo.

    Se codifica con quote (%20) y no con quote_plus (+) porque los ejemplos
    de la documentacion de Abes usan %20 de forma explicita. Ambos deberian
    funcionar; en una prueba diagnostica no conviene introducir una variable
    mas de la necesaria.

    User-Agent identificado con proyecto y contacto: es la practica que la
    Abes espera de un reutilizador, y permite que puedan contactarnos si el
    volumen de peticiones les resulta problematico.
    """
    url = BASE_URL + "?" + urlencode(
        {"q": q, "debut": 0, "nombre": 1}, quote_via=quote
    )
    headers = {
        "User-Agent": f"WPB_TESIS/{VERSION} (proyecto TRANSUR; {contacto})",
        "Accept": "application/json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        # No se degrada en silencio a un valor por defecto (regla F.2):
        # se registra el fallo y se devuelve None, que el informe muestra
        # como ERROR y no como cero.
        log.error("Fallo de red en la consulta [%s]: %s", q, e)
        return None

    if r.status_code == 503:
        log.error("503: la API puede estar en modo mantenimiento. Se aborta.")
        sys.exit(1)
    if r.status_code != 200:
        log.error("HTTP %s en la consulta [%s]", r.status_code, q)
        return None

    try:
        return r.json().get("totalHits")
    except json.JSONDecodeError as e:
        log.error("Respuesta no es JSON valido en [%s]: %s", q, e)
        return None


def main():
    ap = argparse.ArgumentParser(
        description="Diagnostico del comportamiento de la API de theses.fr"
    )
    ap.add_argument(
        "--contacto",
        default="sin-contacto-declarado",
        help="Correo de contacto que se envia en el User-Agent",
    )
    args = ap.parse_args()
    log = configurar_log(args.contacto)

    # Cada prueba: (id, pregunta, etiqueta, consulta)
    # Las pruebas de un mismo bloque se comparan entre si.
    pruebas = [
        ("P1", "Comillas en termino multipalabra",
         "sin comillas", f'{CAMPO_PRUEBA}:({MULTI})'),
        ("P1", "Comillas en termino multipalabra",
         "con comillas", f'{CAMPO_PRUEBA}:("{MULTI}")'),

        ("P2", "Acentos en subcampo .exact",
         "con tilde",  f'{CAMPO_PRUEBA}:("{ACENTO_CON}")'),
        ("P2", "Acentos en subcampo .exact",
         "sin tilde",  f'{CAMPO_PRUEBA}:("{ACENTO_SIN}")'),

        ("P3", "Mayusculas en subcampo .exact",
         "mayuscula", f'{CAMPO_PRUEBA}:("{CAJA_ALTA}")'),
        ("P3", "Mayusculas en subcampo .exact",
         "minuscula", f'{CAMPO_PRUEBA}:("{CAJA_BAJA}")'),

        ("P4", "titrePrincipal como campo indexado",
         "titrePrincipal", f'titrePrincipal:({ACENTO_SIN})'),
        ("P4", "titrePrincipal como campo indexado",
         "titres.fr (control)", f'titres.fr:({ACENTO_SIN})'),

        ("P5", "dateInsertionDansES responde",
         "rango abierto", '* AND dateInsertionDansES:([2024-01-01 TO *])'),
        ("P5", "dateInsertionDansES responde",
         "sin filtro (control)", '*'),
    ]

    resultados = []
    for pid, pregunta, etiqueta, q in pruebas:
        total = consultar(q, args.contacto, log)
        resultados.append((pid, pregunta, etiqueta, q, total))
        log.info("%s | %-22s | total=%s | q=%s", pid, etiqueta, total, q)
        time.sleep(PAUSA)

    # Informe en consola. Se agrupa por pregunta porque lo que se interpreta
    # es la relacion entre los dos totales de cada bloque, no cada uno solo.
    print("\n" + "=" * 74)
    print("INFORME DE DIAGNOSTICO")
    print("=" * 74)
    actual = None
    for pid, pregunta, etiqueta, q, total in resultados:
        if pid != actual:
            print(f"\n[{pid}] {pregunta}")
            actual = pid
        marca = "ERROR" if total is None else f"{total:>9,}"
        print(f"    {etiqueta:<22} {marca}")

    print("\n" + "-" * 74)
    print("COMO LEERLO")
    print("-" * 74)
    print("""
P1  Si 'con comillas' da 0 y 'sin comillas' no, el subcampo .exact no existe
    para este campo: los diccionarios deben usar tipo_busqueda=default.
    Si ambos dan resultados y difieren, .exact funciona y la distincion es
    util. Si dan lo mismo, las comillas no cambian nada en este campo.

P2  Si 'con tilde' y 'sin tilde' dan totales distintos, el .exact NO normaliza
    acentos: cada variante acentuada necesita su propia entrada de sinonimo.
    Si dan lo mismo, sobran las entradas duplicadas por acento.

P3  Igual que P2, para mayusculas.

P4  Si titrePrincipal da 0 y titres.fr no, titrePrincipal no existe como campo
    indexado pese a estar documentado: hay que usar titres.* en su lugar.

P5  Si 'rango abierto' da 0 y el control no, dateInsertionDansES no responde
    y el modo incremental de S01 no se puede implementar sobre este campo.
    Si da un total menor que el control, funciona.

NOTA  Un 0 aislado no prueba nada por si solo: puede que no haya tesis que
      cumplan la condicion. Lo que se interpreta es la comparacion dentro de
      cada bloque.
""")
    log.info("Fin del diagnostico. Registro en %s", LOG_PATH)


if __name__ == "__main__":
    main()
