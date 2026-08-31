#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPB_TESIS_S00_diagnostico3.py  --  v0.3

Tercera ronda de verificacion empirica de la API de busqueda de theses.fr.
NO recupera corpus: solo lanza consultas de conteo.

OBJETIVO
  Determinar, para cada campo que el proyecto va a interrogar, como se analiza
  su contenido. De esto depende como se escriben los diccionarios y que dice el
  README sobre la busqueda por terminos.

  Tres propiedades por campo:
    A. Plegado de acentos  -- decolonial encuentra decolonial con tilde?
    B. Stemming            -- decolonial encuentra decoloniale y decoloniaux?
    C. Orden de frase      -- las comillas imponen orden de palabras?

  El mapeo del indice Elasticsearch NO es publico: no figura en
  abes-esr/theses-api-recherche ni en abes-esr/theses-api-indexation (este
  ultimo solo define el indice 'referencement', que es otro). Por eso las tres
  propiedades solo se pueden establecer por observacion.

ESTADO DE LAS RONDAS ANTERIORES

  Ronda 1 (2026-08-29)
    P2 CERRADA. sujetsLibelle pliega acentos aun entre comillas: 63 = 63.
    P3 CERRADA. sujetsLibelle pliega mayusculas aun entre comillas: 1 = 1.
    P5 DESCARTADA DEL ALCANCE. dateInsertionDansES devolvio el indice completo
       (563.719 con y sin restriccion). No se determino si el campo se ignora
       o si todo el indice se reconstruyo despues de 2024. S01 no implementa
       modo incremental; correra siempre completo y marcara las filas nuevas
       comparando contra los NNT ya conocidos.

  Ronda 2 (2026-08-29)
    P1 CERRADA. Las comillas imponen orden de frase en sujetsLibelle:
       "buen vivir" = 7, "vivir buen" = 0. El subcampo .exact existe y
       funciona. tipo_busqueda=exact es una distincion real.
    P4b CERRADA. La sintaxis _exists_ funciona y devuelve totales distintos
       por campo, de modo que no se esta ignorando. titrePrincipal esta
       poblado en 563.718 de 563.719 registros; titres.fr en 555.485.
       Conclusion: el campo que MENOS recupera es el que MAS cobertura tiene.
       La diferencia 9:1 observada en la ronda 1 no es de cobertura.
    P4a NO CONCLUYENTE, por error de diseno de la prueba. Se uso
       'decolonialite' como forma flexionada de 'decolonial', pero es una
       derivacion (nominalizacion), no una flexion. Ningun stemmer estandar
       las une, asi que la prueba no medía lo que decía medir.
       Esta ronda la repite con flexiones reales: decoloniale, decoloniaux.

DATOS DE PARTIDA CONOCIDOS, para contrastar
    titres.fr:(decolonial)      = 44
    titrePrincipal:(decolonial) = 5
    sujetsLibelle:("buen vivir")= 7

INTERPRETACION
  Ningun total aislado prueba nada. Cada celda de la matriz se lee contra la
  celda 'base' de su misma fila.

USO
    python3 WPB_TESIS_S00_diagnostico3.py --contacto tu@correo.org

Dependencia externa: requests

Fuentes:
  Abes (2026). Le moteur de recherche theses.fr. Documentation.
      https://documentation.abes.fr/aidethesesfr/index.html
  abes-esr/theses-api-recherche, rama develop. Consultado 2026-08-28.
  abes-esr/theses-api-indexation, rama develop. Consultado 2026-08-29.
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

VERSION = "0.3"
BASE_URL = "https://theses.fr/api/v1/theses/recherche/"

# Pausa entre peticiones, en segundos. Conservador: la API no declara limite
# de tasa en su OpenAPI ni en la documentacion de Abes.
PAUSA = 1.0
TIMEOUT = 30

# Campos que el proyecto va a interrogar. Se prueban todos porque nada
# garantiza que compartan analizador: la ronda 1 ya mostro comportamientos
# distintos entre titrePrincipal y titres.fr.
CAMPOS = [
    "titres.fr",
    "titrePrincipal",
    "sujetsLibelle",
    "sujetsRameauLibelle",
    "resumes.fr",
    "discipline",
]

# Familia morfologica de prueba, en frances.
#   BASE      : forma masculina singular, sin tilde
#   ACENTO    : la misma, con tilde -> mide plegado de acentos (propiedad A)
#   FEMENINO  : flexion de genero   -> mide stemming (propiedad B)
#   PLURAL    : flexion de numero   -> mide stemming (propiedad B)
# Son flexiones reales del mismo lema, no derivaciones. Ese fue el error de
# la ronda 2.
BASE = "decolonial"
ACENTO = "décolonial"
FEMENINO = "décoloniale"
PLURAL = "décoloniaux"

# Frase de prueba para el orden de palabras (propiedad C).
FRASE = "buen vivir"
FRASE_INV = "vivir buen"

LOG_PATH = "WPB_TESIS_S00_diagnostico3.log"


def configurar_log(contacto):
    """Log a archivo y consola. encoding explicito (regla E.1: FileHandler no
    lo declara por defecto y aborta en Windows ante caracteres no cp1252).
    Separador con timestamp al abrir en append (regla D.2)."""
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
    log.info("WPB_TESIS_S00_diagnostico3 v%s -- inicio", VERSION)
    log.info("Contacto declarado en User-Agent: %s", contacto)
    return log


def consultar(q, contacto, log):
    """Lanza una consulta y devuelve totalHits, o None si fallo.

    nombre=1 porque solo interesa el contador.
    Codificacion con quote (%20), como en los ejemplos de Abes.
    Ante fallo devuelve None y no 0: un 0 seria indistinguible de un resultado
    legitimo y convertiria un error de red en una conclusion falsa (regla F.2).
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
        log.error("Fallo de red en [%s]: %s", q, e)
        return None
    if r.status_code == 503:
        log.error("503: la API puede estar en mantenimiento. Se aborta.")
        sys.exit(1)
    if r.status_code != 200:
        log.error("HTTP %s en [%s]", r.status_code, q)
        return None
    try:
        return r.json().get("totalHits")
    except json.JSONDecodeError as e:
        log.error("Respuesta no es JSON valido en [%s]: %s", q, e)
        return None


def fmt(v):
    """Formatea un total para la tabla. None se muestra como ERR, nunca como 0."""
    return "ERR" if v is None else f"{v:,}"


def main():
    ap = argparse.ArgumentParser(
        description="Tercera ronda de diagnostico de la API de theses.fr"
    )
    ap.add_argument("--contacto", default="sin-contacto-declarado",
                    help="Correo de contacto que se envia en el User-Agent")
    args = ap.parse_args()
    log = configurar_log(args.contacto)

    # ---- Matriz principal: campo x forma morfologica -------------------
    # Se consulta sin comillas, para medir el analizador del campo y no el
    # del subcampo .exact.
    formas = [("base", BASE), ("acento", ACENTO),
              ("femenino", FEMENINO), ("plural", PLURAL)]
    matriz = {}
    for campo in CAMPOS:
        matriz[campo] = {}
        for etiqueta, termino in formas:
            q = f"{campo}:({termino})"
            total = consultar(q, args.contacto, log)
            matriz[campo][etiqueta] = total
            log.info("MATRIZ | %-20s | %-9s | total=%s", campo, etiqueta, total)
            time.sleep(PAUSA)

    # ---- Orden de frase, por campo -------------------------------------
    # Solo se interpreta en los campos donde la frase directa devuelve algo:
    # si 'directo' es 0, el 0 de 'invertido' no dice nada.
    frases = {}
    for campo in CAMPOS:
        d = consultar(f'{campo}:("{FRASE}")', args.contacto, log)
        time.sleep(PAUSA)
        i = consultar(f'{campo}:("{FRASE_INV}")', args.contacto, log)
        time.sleep(PAUSA)
        frases[campo] = (d, i)
        log.info("FRASE | %-20s | directo=%s invertido=%s", campo, d, i)

    # ---- Informe --------------------------------------------------------
    print("\n" + "=" * 78)
    print("MATRIZ DE ANALISIS POR CAMPO -- consultas SIN comillas")
    print("=" * 78)
    print(f"{'campo':<22}{'base':>14}{'acento':>14}{'femenino':>14}{'plural':>14}")
    print(f"{'':<22}{BASE:>14}{ACENTO:>14}{FEMENINO:>14}{PLURAL:>14}")
    print("-" * 78)
    for campo in CAMPOS:
        m = matriz[campo]
        print(f"{campo:<22}{fmt(m['base']):>14}{fmt(m['acento']):>14}"
              f"{fmt(m['femenino']):>14}{fmt(m['plural']):>14}")

    print("\n" + "=" * 78)
    print(f'ORDEN DE FRASE -- "{FRASE}" vs "{FRASE_INV}", CON comillas')
    print("=" * 78)
    print(f"{'campo':<22}{'directo':>12}{'invertido':>12}")
    print("-" * 78)
    for campo in CAMPOS:
        d, i = frases[campo]
        print(f"{campo:<22}{fmt(d):>12}{fmt(i):>12}")

    print("\n" + "-" * 78)
    print("COMO LEERLO")
    print("-" * 78)
    print("""
A. PLEGADO DE ACENTOS   columnas 'base' y 'acento'
   Iguales  -> el campo pliega acentos. En los diccionarios sobran las
               entradas que solo se diferencian por tildes.
   Distintas-> no los pliega. Cada variante acentuada necesita su entrada.

B. STEMMING             columnas 'femenino' y 'plural' frente a 'base'
   Las tres iguales -> el campo aplica stemming y colapsa las flexiones:
                       basta una forma por lema en el diccionario.
   Distintas        -> no hay stemming: cada flexion que interese debe ir
                       como sinonimo explicito.
   Nota: en la ronda 1, titres.fr dio 44 y titrePrincipal 5 para la misma
   forma base, con cobertura casi identica. Si aqui titres.fr colapsa las
   flexiones y titrePrincipal no, esa es la explicacion de la diferencia.

C. ORDEN DE FRASE       tabla de frases
   invertido = 0 y directo > 0 -> las comillas imponen orden: tipo_busqueda
                                  =exact es una distincion real en ese campo.
   directo = invertido         -> las comillas no cambian nada en ese campo.
   directo = 0                 -> la prueba no dice nada en ese campo: el
                                  termino no esta presente. No interpretar.

ADVERTENCIA  Un campo puede comportarse distinto de otro. No se debe
             generalizar de una fila a las demas: la ronda 1 ya mostro que
             titrePrincipal y titres.fr no coinciden.
""")
    log.info("Fin de la tercera ronda. Registro en %s", LOG_PATH)


if __name__ == "__main__":
    main()
