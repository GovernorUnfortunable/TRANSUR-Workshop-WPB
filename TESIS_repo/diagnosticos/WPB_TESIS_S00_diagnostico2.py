#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WPB_TESIS_S00_diagnostico2.py  --  v0.2

Segunda ronda de verificacion empirica de la API de busqueda de theses.fr.
Cierra las dos preguntas que la primera ronda dejo abiertas.
NO recupera corpus: solo lanza consultas de conteo.

RESULTADOS DE LA PRIMERA RONDA (2026-08-29), que esta ronda no repite:

  P2  CERRADA. Los acentos se normalizan aun dentro de comillas.
      sujetsLibelle:("décolonial") = sujetsLibelle:("decolonial") = 63.
      Consecuencia: las variantes que solo difieren en tildes son entradas
      redundantes en los diccionarios.

  P3  CERRADA. Las mayusculas se normalizan aun dentro de comillas.
      sujetsLibelle:("Quilombo") = sujetsLibelle:("quilombo") = 1.
      Consecuencia: idem, las variantes que solo difieren en caja sobran.

  P5  NO CONCLUYENTE, y se descarta del alcance. El filtro por
      dateInsertionDansES devolvio el indice completo (563.719 con y sin
      restriccion). No se ha determinado si el campo se ignora o si todo el
      indice se reconstruyo despues de 2024. Decision: S01 no implementa modo
      incremental; correra siempre completo y marcara las filas nuevas
      comparando contra los NNT ya conocidos. Queda anotado en el YAML de S01
      como NO IMPLEMENTADO con esta razon.

PREGUNTAS QUE ESTA RONDA RESUELVE:

  P1  Las comillas activan realmente el subcampo .exact?
      Primera ronda: sujetsLibelle:(buen vivir) y sujetsLibelle:("buen vivir")
      dieron 7 y 7. No concluyente, porque los documentos que contienen las dos
      palabras sueltas pueden ser los mismos que contienen la frase.
      Prueba decisiva: invertir el orden de las palabras dentro de las comillas.
      Si las comillas imponen orden de frase, "vivir buen" debe dar 0.
      Si las comillas se ignoran, dara 7, igual que "buen vivir".
      Consecuencia: define si tipo_busqueda=exact aporta algo o es decorativo.

  P4  Por que titrePrincipal recupera nueve veces menos que titres.fr?
      Primera ronda: titrePrincipal:(decolonial)=5 frente a
      titres.fr:(decolonial)=44. El campo existe, pero recupera mucho menos.
      Hipotesis a contrastar: titres.* aplica stemming y titrePrincipal no,
      de modo que el primero solo captura la palabra tal cual y el segundo
      tambien sus formas flexionadas.
      Prueba decisiva: consultar una forma flexionada. Si titres.fr da el mismo
      total para la forma base y la flexionada, colapsa ambas y hay stemming.
      Si titrePrincipal da totales distintos para cada forma, no lo hay.
      Prueba complementaria: _exists_ sobre cada campo, para descartar que la
      diferencia venga de cobertura (campo poblado en pocos registros) en lugar
      de analisis. Si _exists_ no es sintaxis admitida devolvera un error o un
      total anomalo; en ese caso la prueba se descarta y se anota, no se
      interpreta.

INTERPRETACION
  Ningun total aislado prueba nada. Lo que se interpreta es la comparacion
  dentro de cada bloque, contra la consulta de control.

USO
    python3 WPB_TESIS_S00_diagnostico2.py --contacto tu@correo.org

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
from urllib.parse import urlencode, quote

import requests

VERSION = "0.2"
BASE_URL = "https://theses.fr/api/v1/theses/recherche/"

# Pausa entre peticiones, en segundos. Conservador: la API no declara limite
# de tasa en su OpenAPI ni en la documentacion de Abes.
PAUSA = 1.0
TIMEOUT = 30

# Terminos de prueba. Se reutilizan los de la primera ronda para que los
# totales sean comparables entre ambas.
#   FRASE / FRASE_INV : misma frase en orden directo e invertido      -> P1
#   BASE / FLEXION    : forma base y forma flexionada del mismo lema  -> P4
FRASE = "buen vivir"
FRASE_INV = "vivir buen"
BASE = "decolonial"
FLEXION = "decolonialite"

CAMPO_PRUEBA = "sujetsLibelle"

LOG_PATH = "WPB_TESIS_S00_diagnostico2.log"


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
    log.info("WPB_TESIS_S00_diagnostico2 v%s -- inicio", VERSION)
    log.info("Contacto declarado en User-Agent: %s", contacto)
    return log


def consultar(q, contacto, log):
    """Lanza una consulta y devuelve totalHits, o None si fallo.

    nombre=1 porque solo interesa el contador: pedir mas registros no aporta
    al diagnostico y carga el servicio sin motivo.

    Se codifica con quote (%20) y no con quote_plus (+) porque los ejemplos de
    la documentacion de Abes usan %20 de forma explicita.

    User-Agent identificado con proyecto y contacto: practica esperable de un
    reutilizador, y permite que la Abes nos contacte si el volumen de
    peticiones les resulta problematico.

    Ante fallo devuelve None, no 0. Un 0 seria indistinguible de un resultado
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
        log.error("Fallo de red en la consulta [%s]: %s", q, e)
        return None

    if r.status_code == 503:
        log.error("503: la API puede estar en modo mantenimiento. Se aborta.")
        sys.exit(1)
    if r.status_code != 200:
        # Un 400 aqui es informativo, no solo un fallo: indica que la sintaxis
        # no es admitida. Es el resultado esperable de la prueba _exists_ si
        # esa sintaxis no esta habilitada.
        log.error("HTTP %s en la consulta [%s]", r.status_code, q)
        return None

    try:
        return r.json().get("totalHits")
    except json.JSONDecodeError as e:
        log.error("Respuesta no es JSON valido en [%s]: %s", q, e)
        return None


def main():
    ap = argparse.ArgumentParser(
        description="Segunda ronda de diagnostico de la API de theses.fr"
    )
    ap.add_argument(
        "--contacto",
        default="sin-contacto-declarado",
        help="Correo de contacto que se envia en el User-Agent",
    )
    args = ap.parse_args()
    log = configurar_log(args.contacto)

    # Cada prueba: (id, pregunta, etiqueta, consulta)
    # Las pruebas de un mismo bloque se comparan entre si, nunca en aislado.
    pruebas = [
        # -- P1: las comillas imponen orden de frase? ----------------------
        ("P1", "Comillas y orden de frase",
         "directo (control)", f'{CAMPO_PRUEBA}:("{FRASE}")'),
        ("P1", "Comillas y orden de frase",
         "invertido", f'{CAMPO_PRUEBA}:("{FRASE_INV}")'),

        # -- P4a: hay stemming en titres.* y no en titrePrincipal? ---------
        # Se consultan las cuatro combinaciones de campo x forma. Lo que se
        # compara es si cada campo colapsa o distingue las dos formas.
        ("P4a", "Stemming: forma base vs flexionada",
         "titres.fr / base", f'titres.fr:({BASE})'),
        ("P4a", "Stemming: forma base vs flexionada",
         "titres.fr / flexion", f'titres.fr:({FLEXION})'),
        ("P4a", "Stemming: forma base vs flexionada",
         "titrePrincipal / base", f'titrePrincipal:({BASE})'),
        ("P4a", "Stemming: forma base vs flexionada",
         "titrePrincipal / flexion", f'titrePrincipal:({FLEXION})'),

        # -- P4b: la diferencia viene de cobertura del campo? --------------
        # Sintaxis _exists_ no documentada por Abes. Si devuelve ERROR o un
        # total anomalo, la prueba se descarta; no se interpreta.
        ("P4b", "Cobertura de los campos (_exists_)",
         "_exists_ titrePrincipal", '_exists_:titrePrincipal'),
        ("P4b", "Cobertura de los campos (_exists_)",
         "_exists_ titres.fr", '_exists_:titres.fr'),
        ("P4b", "Cobertura de los campos (_exists_)",
         "sin filtro (control)", '*'),
    ]

    resultados = []
    for pid, pregunta, etiqueta, q in pruebas:
        total = consultar(q, args.contacto, log)
        resultados.append((pid, pregunta, etiqueta, q, total))
        log.info("%s | %-26s | total=%s | q=%s", pid, etiqueta, total, q)
        time.sleep(PAUSA)

    print("\n" + "=" * 74)
    print("INFORME DE DIAGNOSTICO -- SEGUNDA RONDA")
    print("=" * 74)
    actual = None
    for pid, pregunta, etiqueta, q, total in resultados:
        if pid != actual:
            print(f"\n[{pid}] {pregunta}")
            actual = pid
        marca = "ERROR" if total is None else f"{total:>9,}"
        print(f"    {etiqueta:<26} {marca}")

    print("\n" + "-" * 74)
    print("COMO LEERLO")
    print("-" * 74)
    print("""
P1   Si 'invertido' da 0 y 'directo' no, las comillas imponen orden de frase:
     el subcampo .exact funciona y tipo_busqueda=exact es una distincion real.
     Si ambos dan el mismo total, las comillas se ignoran en este campo y
     tipo_busqueda no aporta nada: se elimina de los diccionarios o se marca
     como NO IMPLEMENTADO.

P4a  Si titres.fr da el MISMO total para base y flexion, colapsa ambas formas:
     hay stemming. Si titrePrincipal da totales DISTINTOS para base y flexion,
     no lo hay. Las dos condiciones juntas confirman la hipotesis y autorizan
     a documentarla como verificada.
     Si titres.fr tambien distingue las formas, la hipotesis del stemming
     queda descartada y la causa de la diferencia 9:1 sigue sin explicar: en
     ese caso se documenta el hecho observado y no la causa (regla B.2).

P4b  Si '_exists_ titrePrincipal' da un total muy inferior al control, el campo
     esta poblado solo en parte del corpus y la diferencia es de cobertura, no
     de analisis.
     Si ambos _exists_ dan ERROR, la sintaxis no esta admitida: la prueba no
     dice nada y se descarta sin interpretarla.
     Si ambos dan exactamente el total del control, sospechar que la sintaxis
     se ignora y se esta ejecutando una consulta vacia, no que la cobertura
     sea del 100%.

NOTA Ningun total aislado prueba nada por si solo. Lo que se interpreta es la
     comparacion dentro de cada bloque.
""")
    log.info("Fin de la segunda ronda. Registro en %s", LOG_PATH)


if __name__ == "__main__":
    main()
