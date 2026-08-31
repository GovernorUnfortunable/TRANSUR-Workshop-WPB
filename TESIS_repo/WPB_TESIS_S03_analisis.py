#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
WPB_TESIS_S03_analisis.py  --  v0.1

Etapa de analisis del pipeline WPB_TESIS. Lee el CSV de candidatos que
produce S01 -- o el corpus enriquecido que producira S02 -- y emite una
primera aproximacion al corpus: series temporales, rankings, solapamiento
entre conceptos, red de co-participacion en tribunales y un informe de
completitud.

PARA QUE SIRVE
    Es una aproximacion exploratoria, no un resultado. Sirve para identificar
    candidatas a entrevista cualitativa, detectar instituciones y temas que
    concentran actividad, y ver la forma general del corpus antes de
    invertir trabajo en validarlo.

POSICION EN EL PIPELINE
    S01 --> S03              analisis preliminar sobre candidatos sin curar.
    S01 --> S02 --> S03      analisis sobre el corpus validado y enriquecido.

    S02 todavia no existe. S03 detecta que recibio mirando las columnas del
    CSV y omite los analisis para los que falten datos, dejando constancia en
    el log. No emite numeros plausibles a partir de columnas ausentes
    (regla D.6).

CONFIGURACION
    WPB_TESIS_S03_analisis.yaml, mismo nombre base (regla D.5).
    Toda clave del YAML se lee aqui o esta marcada como NO IMPLEMENTADA en el
    bloque no_implementado (regla A.2).

FUENTE DE LOS DATOS
    El corpus proviene de la API de busqueda de theses.fr, consultada por S01.
    NO proviene del data dump Etalab publicado en data.gouv.fr ni del dataset
    derivado de Aboucaya & Jasim (2026). Los tres artefactos tienen nombres de
    campo distintos y no son intercambiables:

      API theses.fr        dateSoutenance, examinateurs, sujetsRameau, ...
      data dump Etalab     volcado JSON de theses.fr (2024-01-08), campos
                           originales
      Aboucaya & Jasim     defense_date, jury_member.{i}.idref, rameau_topics,
      (2026)               ... derivado del data dump y enriquecido con IdRef

    Este script lee UNICAMENTE columnas de la primera. Ver PENDIENTES.

QUE ES EL PPN
    Pica Production Number: identificador de registro del sistema Pica de la
    Abes. Identifica REGISTROS, y hay registros de tipos distintos, de modo
    que "PPN" a secas es ambiguo. En este pipeline:

      PPN de persona       dentro de directeurs, president, rapporteurs,
                           examinateurs y auteurs. Remite a la ficha de
                           autoridad en IdRef (idref.fr/{ppn}).
      PPN de institucion   etabSoutenancePpn, y el segundo campo de
                           ecolesDoctorale y partenairesDeRecherche.
                           Remite tambien a IdRef.
      PPN de SUDOC         identifica el MANUSCRITO catalogado, no a una
                           persona. NO viaja en el endpoint de busqueda, de
                           modo que este corpus no lo tiene.

    Las metricas de persistencia y los rankings de personas usan el PPN de
    persona. Nunca el nombre: ver LIMITES CONOCIDOS.

LIMITES CONOCIDOS DE LA FUENTE
    Documentados en Aboucaya, W. & Jasim, D. (2026). Doctoral theses in
    France (1985-2025): A linked dataset of PhDs, academic networks, and
    institutions. Data in Brief 67, 112947. https://doi.org/10.1016/j.dib.2026.112947

    (a) La composicion del tribunal falta sistematicamente en el material
        antiguo: theses.fr no la registraba de forma sistematica al inicio de
        la plataforma. La ausencia NO es aleatoria y sesga toda metrica de
        persistencia hacia los anhos recientes. Lo mide cobertura_ppn.

    (b) Nombre y apellido aparecen invertidos en una parte de los registros
        de theses.fr. Aboucaya & Jasim lo corrigen en su dataset tomando los
        nombres de IdRef; nosotros leemos theses.fr directo y heredamos el
        problema sin la correccion. Por eso el cotejo de personas se hace
        SIEMPRE por PPN y nunca por nombre.

    (c) Existen identificadores IdRef mal formados o que no resuelven a
        ningun registro; los autores corrigieron 168 a mano sobre ~560.000
        registros. Un PPN roto no rompe el conteo -- se comporta como una
        persona mas -- pero no es resoluble en idref.fr. Esa cifra es de SU
        dataset, no del nuestro: se registra como orden de magnitud conocido,
        no como dato propio.

    (d) Las tesis impresas de las que solo se conoce el anho se registran con
        fecha AAAA-01-01, lo que produce una acumulacion artificial de
        defensas cada 1 de enero. Lo mide reportar_sesgo_1_enero. No se
        corrige: solo se mide cuanto pesa.

DEPENDENCIAS EXTERNAS
    pandas, matplotlib, pyyaml, requests
    networkx solo si metricas.red_total o metricas.componente_mayor estan
    activos; si falta, esas metricas se omiten con WARNING (regla F.2).

EJECUCION
    macOS/Linux:  python3 WPB_TESIS_S03_analisis.py --config WPB_TESIS_S03_analisis.yaml
    Windows:      py -X utf8 WPB_TESIS_S03_analisis.py --config WPB_TESIS_S03_analisis.yaml
    Ver el bloque COMO CORRER del YAML.

PENDIENTES ANOTADOS
    - Enriquecimiento desde el dataset Aboucaya & Jasim (2026): aporta PPN de
      SUDOC del manuscrito, identificador TEL, accessible, embargo,
      phd_by_publication, genero inferido, fechas de nacimiento, centrality,
      edad en la defensa y los IdRef corregidos a mano. Union por nnt; las
      tesis en preparacion no tienen NNT y quedarian fuera. Su corte es el
      2026-03-31. Corresponde a una etapa de enriquecimiento, no a S03: S03
      consume, no recupera.
    - Visualizacion interactiva de la red en Retina (https://retina.cortext.net/).
      El .gexf que este script emite es directamente el formato que Retina
      consume; no hace falta tocar el script para usarlo.
    - Deteccion de PPN no resolubles contra idref.fr (limite (c) de arriba).

REGISTRO DE CAMBIOS
    v0.3  2026-08-31  CORRECCION: CAMPOS_INDICE consultaba 'sujets.libelle'
                      y 'sujetsRameau.libelle', deducidos de la estructura
                      del registro. Los nombres interrogables son
                      'sujetsLibelle' y 'sujetsRameauLibelle', que S01 ya
                      tenia verificados en CAMPOS_PALABRAS_CLAVE. Las
                      consultas devolvian HTTP 200 con total 0 -- no
                      fallaban -- y el informe declaraba 0% en el indice
                      frente a 58,7% y 91,0% en el corpus (reglas B.1, B.3).

                      Anhadida una guardia de imposibilidad aritmetica: si un
                      campo esta relleno en el corpus y ausente en el indice,
                      la consulta esta rota y el campo se omite del informe
                      con ERROR, en vez de imprimir la diferencia.

                      consistencia() distingue ahora "cero incidencias" de
                      "no comprobable": una columna presente pero vacia en
                      todo el corpus emite 'sin datos', no 0. Afecta a
                      datePremiereInscriptionDoctorat, al 0% en el corpus.

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): la
                      comparacion contra el indice de una corrida v0.2 es
                      INVALIDA para los dos campos de materias -- dato
                      presente y falso, no ausente. Las demas metricas no se
                      apoyan en ella y siguen siendo validas. El cero de
                      'defensa anterior a la inscripcion' de v0.2 no era una
                      ausencia de contradicciones y no debe leerse como tal.

    v0.2  2026-08-31  CORRECCION: las fechas de theses.fr vienen en
                      DD/MM/AAAA, no en ISO. anho_de() solo aceptaba ISO, de
                      modo que sobre el corpus real NINGUNA fecha parseaba y
                      el script abortaba por "corpus sin fechas utilizables".
                      Se acepta ahora tambien DD/MM/AAAA y se diagnostica el
                      formato al leer el corpus.

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): ninguno.
                      Es un dato que no llego a producirse, no un dato
                      incorrecto: v0.1 abortaba antes de escribir nada. No
                      hay analisis previo que rehacer.

    v0.1  2026-08-30  Primera version.

                      Al deduplicar por tesis, la fila superviviente conserva
                      TODOS los conceptos que la recuperaron: keyword_origen
                      los lleva separados por | y conceptos_origen conserva
                      la correspondencia con nucleo y tipo_busqueda anidada
                      en un solo campo (regla B.5). Guardar un solo concepto
                      -- el de la primera aparicion -- habria dejado un dato
                      verdadero a medias y sin senhal de que faltaba algo.

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): ninguno,
                      no habia version previa.
"""

import argparse
import csv
import json
import logging
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlencode, quote

import yaml

VERSION = "0.3"

# =========================================================================
# CONSTANTES DE MAPEO
# =========================================================================
# Los nombres de campo se escriben UNA SOLA VEZ, aqui, nunca inline
# (regla B.1). En BIBLM, escribirlos inline produjo una columna invalida en
# todas las exportaciones previas.

# Separadores con que S01 aplana las relaciones 1:N (regla B.5).
#   |  separa elementos          Nom~Prenom~PPN|Nom2~Prenom2~PPN2
#   ~  une los datos de un mismo elemento
SEP_ELEMENTO = "|"
SEP_CAMPO = "~"

# Columnas de personas del CSV de S01. La clave es el nombre de la columna;
# el valor es la etiqueta de rol que se usa en los informes.
COLUMNAS_PERSONA = {
    "directeurs": "director/a",
    "president": "presidente/a",
    "rapporteurs": "ponente",
    "examinateurs": "examinador/a",
    "auteurs": "autor/a",
}

# Columnas que S03 necesita para funcionar. Sin ellas se aborta.
COLUMNAS_OBLIGATORIAS = ["keyword_origen", "dateSoutenance"]

# Columnas cuya ausencia desactiva un analisis concreto en lugar de abortar.
# Clave = columna; valor = que se pierde si falta.
COLUMNAS_OPCIONALES = {
    "etabSoutenanceN": "ranking de instituciones de defensa",
    "discipline": "ranking de disciplinas",
    "nnt": "comprobacion de consistencia status/NNT",
    "status": "comprobacion de consistencia status/NNT",
    "datePremiereInscriptionDoctorat": "comprobacion de orden de fechas",
    "validado": "modos 'validados' y 'ambos'",
}

# Campos que se comparan contra el indice completo de theses.fr.
# Clave = nombre del campo EN EL INDICE; valor = columna equivalente del CSV.
#
# ATENCION: el nombre interrogable NO siempre coincide con el del objeto de
# respuesta. El registro trae 'sujets' y 'sujetsRameau'; el indice los expone
# como 'sujetsLibelle' y 'sujetsRameauLibelle'. Son los nombres que S01 ya
# tenia verificados en CAMPOS_PALABRAS_CLAVE.
#
# Origen (reglas B.1 y B.3): v0.2 consultaba 'sujets.libelle' y
# 'sujetsRameau.libelle', deducidos de la estructura del registro en vez de
# tomados de la constante ya verificada. Las consultas devolvian HTTP 200 con
# total 0 -- no fallaban -- y el informe declaraba 0% en el indice frente a
# 58,7% y 91,0% en el corpus. Aritmeticamente imposible: el corpus es un
# subconjunto del indice.
#
# VERIFICADO 2026-08-31 contra el indice:
#   _exists_:sujets.libelle        -> 200, total 0    (nombre inexistente)
#   _exists_:sujets                -> 200, total 0    (nombre inexistente)
#   _exists_:resumes.fr            -> 200, total 472.524
#   *                              -> 200, total 563.724
CAMPOS_INDICE = {
    "resumes.fr": "resumen",
    "nnt": "nnt",
    "discipline": "discipline",
    "datePremiereInscriptionDoctorat": "datePremiereInscriptionDoctorat",
    "etabSoutenanceN": "etabSoutenanceN",
    "sujetsLibelle": "sujets",
    "sujetsRameauLibelle": "sujetsRameau",
}

# Valor con que se etiqueta un periodo sin dato calculable. No se usa 0 ni
# 100: ambos son valores legitimos de las metricas y confundirlos con
# "no calculable" es exactamente el fallo silencioso que las reglas evitan.
SIN_DATO = ""


# =========================================================================
# CONFIGURACION Y LOG
# =========================================================================

class Config:
    """Acceso a la configuracion que REGISTRA cuando cae a un valor por
    defecto (regla A.3). Un default silencioso convierte un error de
    estructura del YAML en comportamiento plausible pero incorrecto: en
    BIBLM, una clave leida a un nivel de anidamiento inexistente cayo
    siempre al default sin dejar rastro."""

    def __init__(self, datos, log):
        self.datos = datos
        self.log = log
        self.defaults_usados = []
        self.overrides = []

    def get(self, ruta, default=None, obligatorio=False):
        """ruta con puntos: 'api.contacto'."""
        nodo = self.datos
        for parte in ruta.split("."):
            if not isinstance(nodo, dict) or parte not in nodo:
                if obligatorio:
                    self.log.error(
                        "Falta la clave obligatoria '%s' en la configuracion.",
                        ruta)
                    sys.exit(1)
                self.log.warning(
                    "Clave '%s' ausente en el YAML. Se usa el valor por "
                    "defecto: %r", ruta, default)
                self.defaults_usados.append(ruta)
                return default
            nodo = nodo[parte]
        return nodo


def configurar_log(ruta, nivel):
    """Abre el log en utf-8 explicito (regla E.1): logging.FileHandler no lo
    declara por defecto y en Windows aborta con UnicodeEncodeError ante
    caracteres no representables en cp1252, que el corpus frances contiene.

    Modo append con separador de timestamp al inicio (regla D.2): sin el, dos
    corridas quedan indistinguibles en el mismo archivo.
    """
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    fh = logging.FileHandler(ruta, mode="a", encoding="utf-8")
    sh = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    log = logging.getLogger("wpb_tesis_s03")
    log.setLevel(getattr(logging, str(nivel).upper(), logging.INFO))
    log.handlers = []
    log.addHandler(fh)
    log.addHandler(sh)
    log.propagate = False
    log.info("=" * 70)
    log.info("WPB_TESIS_S03_analisis v%s -- inicio de corrida", VERSION)
    return log


def cargar_config(ruta, log_provisional):
    """Lee el YAML. Un archivo mal formado ABORTA con archivo, linea, columna
    y fragmento senhalado (regla F.4). Caer a los defaults ante un YAML roto
    produce una corrida completa y plausible con parametros que el usuario no
    eligio: es el fallo que S02 de BIBLM tuvo en v0.1.
    """
    if not os.path.isfile(ruta):
        log_provisional.error("No existe el archivo de configuracion: %s", ruta)
        sys.exit(1)
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = yaml.safe_load(f)
    except yaml.YAMLError as e:
        log_provisional.error("El archivo de configuracion no se pudo leer.")
        log_provisional.error("  Archivo: %s", ruta)
        marca = getattr(e, "problem_mark", None)
        if marca is not None:
            log_provisional.error("  Linea %d, columna %d",
                                  marca.line + 1, marca.column + 1)
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    lineas = f.readlines()
                if 0 <= marca.line < len(lineas):
                    log_provisional.error("  %s", lineas[marca.line].rstrip())
                    log_provisional.error("  %s^", " " * marca.column)
            except OSError:
                pass
        if getattr(e, "problem", None):
            log_provisional.error("  Problema: %s", e.problem)
        log_provisional.error("Se aborta. No se usa una configuracion de "
                              "respaldo (regla F.4).")
        sys.exit(1)
    if not isinstance(datos, dict):
        log_provisional.error("El YAML no contiene un mapa de claves: %s", ruta)
        sys.exit(1)
    return datos


def log_provisional():
    """Log minimo a consola para los errores anteriores a la lectura del
    YAML, que es donde se declara la ruta del log definitivo."""
    log = logging.getLogger("wpb_tesis_s03_pre")
    if not log.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        log.addHandler(sh)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


# =========================================================================
# LECTURA DEL CORPUS
# =========================================================================

def detectar_separador(ruta):
    """Detecta el separador del CSV a partir de la primera linea (regla E.5).

    Un archivo abierto y vuelto a guardar en Excel o Numbers puede salir con
    tabulaciones o punto y coma en lugar de comas. Asumir la coma produce una
    unica columna con todo dentro, y el error aparece mas tarde como columnas
    obligatorias ausentes.
    """
    with open(ruta, "r", encoding="utf-8-sig") as f:
        cabecera = f.readline()
    candidatos = {",": cabecera.count(","),
                  ";": cabecera.count(";"),
                  "\t": cabecera.count("\t")}
    sep = max(candidatos, key=candidatos.get)
    return sep if candidatos[sep] > 0 else ","


def extraer_iteracion(ruta_csv, log):
    """Deriva el identificador de corrida del NOMBRE del CSV de entrada
    (regla C.6). No se declara en este YAML: la iteracion la fija S01, y
    declararla en cada etapa obligaria a mantener sitios sincronizados.

    Patron esperado:  WPB_TESIS_{iter}_{dicc}_S0N.csv
    """
    base = os.path.basename(ruta_csv)
    m = re.search(r"WPB_TESIS_(\d+)_", base)
    if m:
        log.info("Iteracion derivada del nombre del CSV: %s", m.group(1))
        return m.group(1)
    log.warning("No se pudo derivar la iteracion del nombre '%s'. Se usa "
                "'000'. Los outputs quedaran etiquetados con esa iteracion, "
                "que puede no corresponder a la de S01 (regla C.6).", base)
    return "000"


def extraer_diccionario(ruta_csv):
    """Deriva el tipo de diccionario del nombre del CSV, si esta presente."""
    base = os.path.basename(ruta_csv)
    m = re.search(r"WPB_TESIS_\d+_([A-Za-z]+)_S0", base)
    return m.group(1) if m else "sin_dicc"


def leer_corpus(ruta, log):
    """Lee el CSV de entrada detectando separador y absorbiendo el BOM
    (regla E.5), y comprueba las columnas obligatorias ANTES de usarlas.

    Devuelve (lista de dicts, lista de columnas).
    """
    if not os.path.isfile(ruta):
        log.error("No existe el CSV de entrada: %s", ruta)
        log.error("Se esperaba la salida de S01 (o de S02 cuando exista).")
        sys.exit(1)

    sep = detectar_separador(ruta)
    log.info("Corpus: %s (separador detectado: %r)", ruta, sep)

    # El campo de resumen puede superar el limite por defecto de csv.
    try:
        csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
    except OverflowError:
        csv.field_size_limit(2 ** 31 - 1)

    with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=sep)
        columnas = lector.fieldnames or []
        faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in columnas]
        if faltan:
            log.error("Al CSV le faltan columnas obligatorias.")
            log.error("  Esperadas:   %s", ", ".join(COLUMNAS_OBLIGATORIAS))
            log.error("  Encontradas: %s", ", ".join(columnas))
            sys.exit(1)
        filas = list(lector)

    if not filas:
        log.error("El CSV no tiene ninguna fila. Se aborta en lugar de "
                  "generar exports vacios (regla F.3).")
        sys.exit(1)

    log.info("Filas leidas: %d", len(filas))

    ausentes = [c for c in COLUMNAS_OPCIONALES if c not in columnas]
    if ausentes:
        log.warning("Columnas opcionales ausentes. Se OMITEN los analisis "
                    "que dependen de ellas; no se emiten numeros plausibles "
                    "en su lugar (regla D.6):")
        for c in sorted(set(ausentes)):
            log.warning("  falta '%s'  ->  se omite: %s",
                        c, COLUMNAS_OPCIONALES[c])
    return filas, columnas


# =========================================================================
# PARSEO DE CAMPOS ANIDADOS
# =========================================================================

def parsear_personas(valor):
    """Deshace el aplanado de S01 conservando la correspondencia (regla B.5).

    Entrada:  Nom~Prenom~PPN|Nom2~Prenom2~PPN2
    Salida:   [{'nom':..., 'prenom':..., 'ppn':...}, ...]

    S01 emite SIN deduplicar, tal como viene de la API. La decision de si una
    persona repetida cuenta una o dos veces es analitica y corresponde a este
    script: se deduplica por PPN dentro de cada tesis antes de contar, porque
    los roles pueden solaparse (un ponente suele sentarse en el tribunal).
    """
    personas = []
    if not valor:
        return personas
    for pieza in str(valor).split(SEP_ELEMENTO):
        pieza = pieza.strip()
        if not pieza:
            continue
        partes = pieza.split(SEP_CAMPO)
        while len(partes) < 3:
            partes.append("")
        personas.append({"nom": partes[0].strip(),
                         "prenom": partes[1].strip(),
                         "ppn": partes[2].strip()})
    return personas


def nombre_persona(p):
    """Etiqueta legible para informes y para los nodos del grafo.

    ATENCION: es solo etiqueta. El cotejo va siempre por PPN, porque nombre y
    apellido aparecen invertidos en parte de los registros de theses.fr
    (Aboucaya & Jasim, 2026). Ver LIMITES CONOCIDOS en la cabecera.
    """
    nom = (p.get("nom") or "").strip()
    pre = (p.get("prenom") or "").strip()
    etiqueta = ", ".join(x for x in (nom, pre) if x)
    return etiqueta or (p.get("ppn") or "sin identificar")


def parsear_organismos(valor):
    """Nom~PPN~Tipo|... -> [{'nom':..., 'ppn':..., 'tipo':...}, ...]"""
    orgs = []
    if not valor:
        return orgs
    for pieza in str(valor).split(SEP_ELEMENTO):
        pieza = pieza.strip()
        if not pieza:
            continue
        partes = pieza.split(SEP_CAMPO)
        while len(partes) < 3:
            partes.append("")
        orgs.append({"nom": partes[0].strip(),
                     "ppn": partes[1].strip(),
                     "tipo": partes[2].strip()})
    return orgs


# Formatos de fecha observados en la salida de S01.
#
# VERIFICADO 2026-08-31 sobre WPB_TESIS_001_keywords_S01.csv (1294 filas):
# theses.fr devuelve DD/MM/AAAA, no ISO. Ejemplos: 23/10/2018, 14/11/2025,
# 30/11/2021. Se acepta tambien el ISO por si el data dump o una version
# futura de la API lo emiten (regla B.2: el formato se verifico contra el
# output real, no contra la documentacion).
#
# La ambiguedad DD/MM vs MM/DD no afecta al anho, que es el ultimo
# componente en ambas lecturas. Solo importaria para es_primero_de_enero,
# donde 01/01 es identico en las dos.
RE_FECHA_ISO = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})")
RE_FECHA_BARRAS = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})")


def partes_fecha(fecha):
    """Devuelve (anho, mes, dia) o None si la cadena no es una fecha
    reconocible. Acepta AAAA-MM-DD y DD/MM/AAAA.

    Origen (regla B.3): la primera version solo aceptaba ISO, porque asumi el
    formato en lugar de verificarlo. Sobre el corpus real ninguna fecha
    parseaba y el script abortaba por corpus sin fechas -- el sintoma
    apuntaba al dato, y el fallo estaba en el parseo.
    """
    if not fecha:
        return None
    texto = str(fecha)
    m = RE_FECHA_ISO.match(texto)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = RE_FECHA_BARRAS.match(texto)
    if m:
        return int(m.group(3)), int(m.group(2)), int(m.group(1))
    return None


def anho_de(fecha):
    """Extrae el anho de una fecha. Devuelve None si no hay dato utilizable.

    None NO es lo mismo que 0: las filas sin fecha se excluyen de las series
    temporales y se cuentan aparte, en lugar de acumularse en un anho ficticio.
    """
    partes = partes_fecha(fecha)
    return partes[0] if partes else None


def diagnosticar_fechas(filas, columna, log, muestra=5):
    """Informa cuantas fechas parsean y muestra ejemplos de las que no.

    Sin la muestra, un fallo de formato se manifiesta como "el corpus no
    tiene fechas", que apunta al dato cuando el problema puede estar en el
    parseo. Es lo que paso al correr v0.1 contra el corpus real.
    """
    valores = [f.get(columna) for f in filas]
    no_parsean = [v for v in valores if str(v or "").strip()
                  and partes_fecha(v) is None]
    vacias = sum(1 for v in valores if not str(v or "").strip())
    parsean = len(valores) - len(no_parsean) - vacias

    log.info("Fechas en '%s': %d utilizables, %d vacias, %d con formato no "
             "reconocido.", columna, parsean, vacias, len(no_parsean))
    if no_parsean:
        log.warning("  Formatos aceptados: AAAA-MM-DD y DD/MM/AAAA.")
        log.warning("  Ejemplos de lo que no parsea: %s",
                    ", ".join(repr(v) for v in no_parsean[:muestra]))
    return parsean, vacias, no_parsean


def es_primero_de_enero(fecha):
    """Detecta el 1 de enero, que la Abes usa cuando de una tesis impresa
    solo se conoce el anho. Ver limite (d) de la cabecera."""
    partes = partes_fecha(fecha)
    return bool(partes) and partes[1] == 1 and partes[2] == 1


def normalizar_para_archivo(texto):
    """Convierte un concepto en un fragmento de nombre de archivo seguro.

    IMPORTANTE (regla G.7): esto se usa SOLO para nombrar archivos. El cotejo
    con el CSV se hace siempre contra el valor original de keyword_origen. En
    BIBLM, normalizar el keyword y luego cruzar por el valor normalizado dejo
    sin metricas justo a los terminos de mas de una palabra, en silencio.
    """
    txt = unicodedata.normalize("NFKD", str(texto))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"[^A-Za-z0-9]+", "_", txt).strip("_").lower()
    return txt or "sin_concepto"


# =========================================================================
# SELECCION DE FILAS
# =========================================================================

def es_validado(valor, aceptados):
    """Comprueba la columna validado sin distinguir mayusculas ni espacios."""
    return str(valor or "").strip().lower() in {str(a).strip().lower()
                                                for a in aceptados}


def filtrar_por_modo(filas, modo, aceptados, columnas, log):
    """Selecciona las filas segun entrada.modo.

    ADVERTENCIA que no es de tamanho de muestra: la curacion cambia lo que
    MIDEN las metricas de persistencia, no solo cuantas filas entran. "Ya
    habia aparecido antes" es relativo al universo que se analiza. Una jurado
    que estuvo en tres tesis descartadas y aparece en una validada cuenta
    como nueva en modo 'validados' y como recurrente en modo 'candidatos'.
    Ninguna lectura es mas correcta; responden preguntas distintas.

    Todo descarte se reporta con su conteo (regla D.4).
    """
    if modo == "candidatos":
        log.info("Modo 'candidatos': se analizan las %d filas, curadas o no.",
                 len(filas))
        return filas

    if "validado" not in columnas:
        log.error("entrada.modo = '%s' requiere la columna 'validado', que "
                  "el CSV no tiene. Se aborta: correr en modo 'candidatos' "
                  "sin decirlo produciria un informe que declara un universo "
                  "distinto del que uso.", modo)
        sys.exit(1)

    validadas = [f for f in filas if es_validado(f.get("validado"), aceptados)]
    log.info("Modo '%s': %d filas validadas de %d (%d descartadas).",
             modo, len(validadas), len(filas), len(filas) - len(validadas))

    if not validadas:
        log.error("Ninguna fila tiene un valor afirmativo en 'validado'. Se "
                  "aborta en lugar de generar exports vacios (regla F.3).")
        log.error("  Valores aceptados como afirmativos: %s",
                  ", ".join(str(a) for a in aceptados))
        sys.exit(1)
    return validadas


def recortar_periodo(filas, anho_inicio, anho_fin, log):
    """Recorta el corpus de ANALISIS y reporta cuanto descarto (regla D.4).

    ALCANCE (regla A.4): esto redefine el corpus sobre el que se calculan
    TODAS las metricas, no la ventana del grafico. No equivale al recorte de
    S01, que actua antes de descargar. Y cambia el significado de la
    persistencia: una jurado que participo antes del recorte y reaparece
    dentro cuenta como nueva, porque su aparicion previa quedo fuera del
    universo.
    """
    if anho_inicio is None and anho_fin is None:
        return filas, 0, 0

    dentro, fuera, sin_fecha = [], 0, 0
    for f in filas:
        a = anho_de(f.get("dateSoutenance"))
        if a is None:
            sin_fecha += 1
            continue
        if anho_inicio is not None and a < int(anho_inicio):
            fuera += 1
            continue
        if anho_fin is not None and a > int(anho_fin):
            fuera += 1
            continue
        dentro.append(f)

    log.warning("RECORTE TEMPORAL ACTIVO: %s a %s.",
                anho_inicio if anho_inicio is not None else "sin limite",
                anho_fin if anho_fin is not None else "sin limite")
    log.warning("  descartadas por quedar fuera del periodo: %d", fuera)
    log.warning("  descartadas por no tener fecha de defensa: %d", sin_fecha)
    log.warning("  quedan: %d", len(dentro))
    log.warning("  Las metricas de esta corrida NO son comparables con las "
                "de una corrida sin recorte (regla A.4).")

    if not dentro:
        log.error("El recorte deja el corpus vacio. Se aborta (regla F.3).")
        sys.exit(1)
    return dentro, fuera, sin_fecha


# =========================================================================
# PERIODOS
# =========================================================================

def construir_periodos(anhos, granularidad, tramo, log):
    """Devuelve (lista de etiquetas de periodo, funcion anho -> etiqueta).

    granularidad 'anual'   un punto por anho.
    granularidad 'tramos'  bloques de 'tramo' anhos. Con corpus pequenhos un
                           anho con una sola tesis produce porcentajes de 0 o
                           100 que no describen nada.

    Los tramos se anclan en el primer anho con datos, no en multiplos de la
    decada. Anclar en multiplos partiria el primer tramo por la mitad y el
    numero de tesis del primer bloque no seria comparable con el de los demas.
    """
    if not anhos:
        return [], (lambda a: None)

    if granularidad == "anual":
        etiquetas = [str(a) for a in range(min(anhos), max(anhos) + 1)]
        return etiquetas, (lambda a: str(a) if a is not None else None)

    if granularidad != "tramos":
        log.warning("temporal.granularidad = %r no reconocida. Valores "
                    "validos: 'anual' | 'tramos'. Se usa 'anual'.",
                    granularidad)
        etiquetas = [str(a) for a in range(min(anhos), max(anhos) + 1)]
        return etiquetas, (lambda a: str(a) if a is not None else None)

    tramo = max(1, int(tramo))
    inicio, fin = min(anhos), max(anhos)

    def etiqueta_de(a):
        if a is None:
            return None
        desde = inicio + ((a - inicio) // tramo) * tramo
        return "%d-%d" % (desde, desde + tramo - 1)

    etiquetas = []
    desde = inicio
    while desde <= fin:
        etiquetas.append("%d-%d" % (desde, desde + tramo - 1))
        desde += tramo
    log.info("Granularidad 'tramos' de %d anhos, anclada en %d: %d periodos.",
             tramo, inicio, len(etiquetas))
    return etiquetas, etiqueta_de


# =========================================================================
# METRICAS POR CONCEPTO
# =========================================================================

def personas_de_fila(fila, roles_activos):
    """Miembros de tribunal de una tesis, deduplicados por PPN.

    Los roles pueden solaparse -- en la practica francesa un ponente suele
    sentarse en el tribunal -- y no se ha verificado si Abes lo registra en
    los dos campos o solo en uno. Se deduplica por PPN dentro de la tesis
    ANTES de contar, de modo que una misma persona en dos roles cuente una vez.

    Devuelve (dict ppn -> nombre, n_personas_sin_ppn).
    """
    por_ppn = {}
    sin_ppn = 0
    for columna in roles_activos:
        for p in parsear_personas(fila.get(columna)):
            ppn = (p.get("ppn") or "").strip()
            if ppn:
                por_ppn.setdefault(ppn, nombre_persona(p))
            else:
                sin_ppn += 1
    return por_ppn, sin_ppn


def calcular_series(filas, etiquetas, etiqueta_de, roles_activos, cfg, log):
    """Series por periodo para un subconjunto de filas (un concepto o el
    corpus completo).

    persistencia_tribunal: para cada periodo, que proporcion de los miembros
    de tribunal de ese periodo YA habia aparecido en un periodo ANTERIOR del
    mismo subconjunto. Es la inversa de newcomers_pct de WPB_BIBLM_S02, que
    calcula el porcentaje de autores que aparecen por primera vez:

        persistencia = 100 - newcomers

    Se emite la persistencia porque es lo que responde la pregunta de quien
    sostiene una linea tematica en el tiempo.

    El PRIMER periodo con datos no tiene periodo anterior, de modo que su
    persistencia no esta definida. Se emite vacio, no 0: un 0 se leeria como
    "nadie repetia", que es una afirmacion sobre el mundo, y aqui no hay
    afirmacion posible.

    El identificador es el PPN de persona. Quien no lo trae queda fuera de
    esta metrica: sin identificador estable no hay desambiguacion posible, y
    cotejar por nombre no es alternativa (Aboucaya & Jasim, 2026). Lo que
    esta metrica puede cubrir lo mide cobertura_ppn.
    """
    activas = [m for m in ("n_tesis_anual", "n_tesis_acumulado",
                           "n_personas_distintas", "persistencia_tribunal")
               if cfg.get("metricas." + m, True)]

    por_periodo = defaultdict(list)
    sin_fecha = 0
    for f in filas:
        et = etiqueta_de(anho_de(f.get("dateSoutenance")))
        if et is None:
            sin_fecha += 1
            continue
        por_periodo[et].append(f)

    series = {"periodo": list(etiquetas)}
    for m in activas:
        series[m] = []

    acumulado = 0
    ppn_previos = set()
    hubo_periodo_con_datos = False

    for et in etiquetas:
        del_periodo = por_periodo.get(et, [])
        n_tesis = len(del_periodo)
        acumulado += n_tesis

        ppn_periodo = set()
        for f in del_periodo:
            por_ppn, _ = personas_de_fila(f, roles_activos)
            ppn_periodo.update(por_ppn.keys())

        if "n_tesis_anual" in series:
            series["n_tesis_anual"].append(n_tesis)
        if "n_tesis_acumulado" in series:
            series["n_tesis_acumulado"].append(acumulado)
        if "n_personas_distintas" in series:
            series["n_personas_distintas"].append(len(ppn_periodo))

        if "persistencia_tribunal" in series:
            if not ppn_periodo or not hubo_periodo_con_datos:
                # Sin personas identificadas, o sin periodo anterior con el
                # que comparar: no calculable. Vacio, nunca 0 ni 100.
                series["persistencia_tribunal"].append(SIN_DATO)
            else:
                repetidos = ppn_periodo & ppn_previos
                series["persistencia_tribunal"].append(
                    round(len(repetidos) / len(ppn_periodo) * 100, 1))

        if ppn_periodo:
            hubo_periodo_con_datos = True
        ppn_previos.update(ppn_periodo)

    if sin_fecha:
        log.debug("  %d filas sin fecha de defensa quedaron fuera de las "
                  "series temporales.", sin_fecha)
    return series, sin_fecha


# =========================================================================
# RANKINGS
# =========================================================================

def ranking_personas(filas, roles_activos, top_n):
    """Personas mas recurrentes, en NUMERO DE TESIS.

    La unidad es la tesis, no la aparicion: una persona que figura como
    ponente y como examinadora de la misma tesis cuenta UNA vez, porque
    personas_de_fila deduplica por PPN dentro de la fila. Contar apariciones
    daria un numero distinto y mediria otra cosa -- el error que en BIBLM
    hizo que el docstring anunciara documentos y el codigo contara
    afiliaciones (regla G.3).

    Devuelve [(ppn, nombre, n_tesis), ...] de mayor a menor.
    """
    conteo = Counter()
    etiquetas = {}
    for f in filas:
        por_ppn, _ = personas_de_fila(f, roles_activos)
        for ppn, nombre in por_ppn.items():
            conteo[ppn] += 1
            etiquetas.setdefault(ppn, nombre)
    return [(ppn, etiquetas.get(ppn, ppn), n)
            for ppn, n in conteo.most_common(top_n)]


def ranking_instituciones(filas, top_n):
    """Instituciones de defensa mas frecuentes, en numero de tesis.

    ATENCION a que mide: es la institucion DE DEFENSA, es decir donde se
    defendieron las tesis. NO es la institucion de los miembros del tribunal,
    que el registro de la tesis no contiene. Una profesora de Lyon en un
    tribunal de Paris aparece bajo Paris si se confunden las dos cosas.

    La adscripcion declarada de cada jurado esta en IdRef, servicio distinto y
    sin verificar. Fuera del alcance de esta version.
    """
    conteo = Counter()
    for f in filas:
        nombre = (f.get("etabSoutenanceN") or "").strip()
        if nombre:
            conteo[nombre] += 1
    return conteo.most_common(top_n)


def ranking_disciplinas(filas, top_n):
    """Disciplinas mas frecuentes.

    El campo es texto libre segun la especificacion TEF: habra variantes
    ortograficas que NO se agrupan. Dos formas de escribir la misma
    disciplina cuentan como dos. No se normaliza aqui porque cualquier
    agrupacion seria una decision analitica no verificada; queda anotado como
    desarrollo futuro en el YAML.
    """
    conteo = Counter()
    for f in filas:
        d = (f.get("discipline") or "").strip()
        if d:
            conteo[d] += 1
    return conteo.most_common(top_n)


# =========================================================================
# SOLAPAMIENTO Y DESCRIPCION DEL CORPUS
# =========================================================================

def clave_tesis(fila):
    """Identificador de la tesis para deduplicar y cruzar conceptos.

    Se prefiere nnt; si falta -- las tesis en preparacion no lo tienen -- se
    cae a id, que es el identificador del registro en el indice.
    """
    return (fila.get("nnt") or "").strip() or (fila.get("id") or "").strip()


def deduplicar_por_tesis(filas, log=None):
    """Deja una fila por tesis distinta, conservando la primera aparicion.

    POR QUE ES NECESARIO: el CSV de S01 tiene UNA FILA POR (tesis, concepto).
    Una tesis recuperada por dos terminos del diccionario aparece dos veces.
    Eso es correcto para las metricas POR CONCEPTO -- pertenece a los dos
    subcorpus, y por eso la suma de los subcorpus supera el corpus -- pero
    NO para las metricas del corpus completo: contarla dos veces infla el
    conteo de tesis, los rankings de personas e instituciones, el peso de las
    aristas del grafo y la cobertura de PPN.

    Origen (regla G.3): la primera version contaba filas en todas las
    metricas globales. El docstring de ranking_personas anunciaba "numero de
    tesis" y el codigo contaba filas. La discrepancia no aparecio al probar
    con datos sinteticos sin repeticiones; solo al calcular a mano el valor
    esperado de una persona presente en una tesis que dos conceptos habian
    recuperado.

    QUE PASA CON LOS CONCEPTOS DE LAS FILAS DESCARTADAS: no se pierden. La
    fila que sobrevive recibe TODOS los conceptos que recuperaron esa tesis:

      keyword_origen      buen vivir|decolonial
      conceptos_origen    buen vivir~A~exact|decolonial~B~default
                          |  separa conceptos
                          ~  une concepto, nucleo y tipo_busqueda

    Conservar un solo keyword_origen -- el de la primera aparicion, elegido
    por el orden del archivo -- dejaria un dato verdadero a medias: quien lo
    leyera obtendria un concepto real, sin senhal alguna de que habia otros.
    Es el fallo silencioso y plausible que las reglas evitan.

    nucleo y tipo_busqueda son valores POR CONCEPTO, uno cada uno. Emitirlos
    como listas paralelas a la de keyword_origen equivaldria a la estructura
    original solo garantizando el mismo orden y la misma longitud, que es lo
    que la regla B.5 prohibe: la correspondencia se conserva anidada en
    conceptos_origen, en un solo campo. Las columnas nucleo y tipo_busqueda
    se dejan intactas para no romper a quien las lea, pero con mas de un
    concepto NO son fiables por si solas: la fuente es conceptos_origen.

    Las filas sin identificador de tesis se conservan todas: sin clave no hay
    forma de saber si son la misma o distintas, y descartarlas en silencio
    seria peor que contarlas de mas.

    NO muta las filas de entrada: devuelve copias.
    """
    # Todos los conceptos de cada tesis, en orden de aparicion y sin repetir.
    conceptos_de = defaultdict(list)
    for f in filas:
        clave = clave_tesis(f)
        if not clave:
            continue
        pieza = SEP_CAMPO.join([
            (f.get("keyword_origen") or "").strip(),
            (f.get("nucleo") or "").strip(),
            (f.get("tipo_busqueda") or "").strip(),
        ])
        if pieza not in conceptos_de[clave]:
            conceptos_de[clave].append(pieza)

    vistas = set()
    unicas = []
    sin_clave = 0
    multiconcepto = 0
    for f in filas:
        clave = clave_tesis(f)
        if not clave:
            sin_clave += 1
            copia = dict(f)
            copia["conceptos_origen"] = SEP_CAMPO.join([
                (f.get("keyword_origen") or "").strip(),
                (f.get("nucleo") or "").strip(),
                (f.get("tipo_busqueda") or "").strip()])
            unicas.append(copia)
            continue
        if clave in vistas:
            continue
        vistas.add(clave)

        piezas = conceptos_de[clave]
        copia = dict(f)
        copia["conceptos_origen"] = SEP_ELEMENTO.join(piezas)
        copia["keyword_origen"] = SEP_ELEMENTO.join(
            p.split(SEP_CAMPO)[0] for p in piezas)
        if len(piezas) > 1:
            multiconcepto += 1
        unicas.append(copia)

    if log is not None:
        log.info("Filas: %d  ->  tesis distintas: %d (%d filas eran la misma "
                 "tesis recuperada por varios conceptos).",
                 len(filas), len(unicas), len(filas) - len(unicas))
        if multiconcepto:
            log.info("  %d tesis fueron recuperadas por mas de un concepto. "
                     "En la fila deduplicada, keyword_origen los lleva todos "
                     "separados por '%s', y conceptos_origen conserva la "
                     "correspondencia con nucleo y tipo_busqueda (regla B.5).",
                     multiconcepto, SEP_ELEMENTO)
        if sin_clave:
            log.warning("  %d filas sin nnt ni id: se conservan todas, porque "
                        "sin clave no se puede saber si son la misma tesis.",
                        sin_clave)
    return unicas


def matriz_solapamiento(filas, conceptos):
    """Cuantas tesis comparte cada par de conceptos.

    Una misma tesis puede haber sido recuperada por varios terminos del
    diccionario, de modo que la suma de los subcorpus SUPERA el tamanho del
    corpus. Eso es correcto y el informe lo declara.

    Devuelve (matriz {a: {b: n}}, n_tesis_en_mas_de_un_concepto).
    """
    conceptos_por_tesis = defaultdict(set)
    for f in filas:
        clave = clave_tesis(f)
        if clave:
            conceptos_por_tesis[clave].add((f.get("keyword_origen") or "").strip())

    matriz = {a: {b: 0 for b in conceptos} for a in conceptos}
    multiples = 0
    for conjunto in conceptos_por_tesis.values():
        presentes = [c for c in conjunto if c in matriz]
        if len(presentes) > 1:
            multiples += 1
        for a in presentes:
            for b in presentes:
                matriz[a][b] += 1
    return matriz, multiples


def describir_corpus(filas, conceptos, log):
    """Descripcion del corpus por termino: cuantas tesis cumplen el criterio
    de busqueda y que anhos cubre.

    'unicas' cuenta las tesis que SOLO ese concepto recupero. Retroalimenta
    el diccionario de S01: un termino cuyas tesis vienen todas por otra via
    no esta aportando nada propio.
    """
    conceptos_por_tesis = defaultdict(set)
    for f in filas:
        clave = clave_tesis(f)
        if clave:
            conceptos_por_tesis[clave].add((f.get("keyword_origen") or "").strip())

    descripcion = []
    for c in conceptos:
        del_concepto = [f for f in filas
                        if (f.get("keyword_origen") or "").strip() == c]
        anhos = [a for a in (anho_de(f.get("dateSoutenance"))
                             for f in del_concepto) if a is not None]
        claves = {clave_tesis(f) for f in del_concepto if clave_tesis(f)}
        unicas = sum(1 for k in claves
                     if len(conceptos_por_tesis.get(k, ())) == 1)
        descripcion.append({
            "concepto": c,
            # Tesis DISTINTAS, no filas: si el mismo termino recupero la
            # misma tesis dos veces, cuenta una.
            "n_tesis": len(claves) if claves else len(del_concepto),
            "n_tesis_unicas": unicas,
            "anho_primero": min(anhos) if anhos else SIN_DATO,
            "anho_ultimo": max(anhos) if anhos else SIN_DATO,
            "sin_fecha": len(del_concepto) - len(anhos),
        })
    return descripcion


# =========================================================================
# RED DE CO-PARTICIPACION
# =========================================================================

def construir_grafo(filas, roles_activos, log):
    """Nodos = personas (por PPN de persona). Arista = haber estado en el
    mismo tribunal.

    Devuelve (grafo, n_tesis_aportadas) o (None, 0) si falta networkx.

    El tribunal de cada tesis es un CLIQUE completo: todos con todos. Es una
    propiedad del dato, no una eleccion, y condiciona la lectura de cualquier
    metrica de estructura calculada encima.
    """
    try:
        import networkx as nx
    except ImportError:
        log.warning("networkx no esta instalado: se OMITEN la red de "
                    "co-participacion y sus metricas (regla F.2).")
        log.warning("  Consecuencia analitica: el informe no dira nada sobre "
                    "como se agrupan los miembros de tribunal. El resto del "
                    "analisis no se ve afectado.")
        log.warning("  Instalar con: python3 -m pip install networkx")
        return None, 0

    g = nx.Graph()
    aportadas = 0
    for f in filas:
        por_ppn, _ = personas_de_fila(f, roles_activos)
        ppns = list(por_ppn.keys())
        if not ppns:
            continue
        aportadas += 1
        for ppn in ppns:
            if ppn not in g:
                g.add_node(ppn, label=por_ppn[ppn])
        for i in range(len(ppns)):
            for j in range(i + 1, len(ppns)):
                a, b = ppns[i], ppns[j]
                if g.has_edge(a, b):
                    g[a][b]["weight"] += 1
                else:
                    g.add_edge(a, b, weight=1)
    return g, aportadas


def analizar_red(g, umbral_modularidad, log):
    """Metricas de la red total y particion en comunidades (Louvain).

    Louvain esta en networkx desde la version 2.7, como
    nx.community.louvain_communities.

    LECTURA CON CORPUS PEQUENHOS: si las tesis casi no comparten jurados, el
    grafo es un conjunto de cliques casi disjuntos y Louvain devuelve una
    comunidad por tesis. En ese caso la particion refleja cuantas tesis hubo,
    no estructura de campo. La modularidad alta es la senhal: se avisa por
    log y en el pie de la figura.
    """
    import networkx as nx

    if g.number_of_nodes() == 0:
        log.warning("La red no tiene ningun nodo: ninguna tesis del corpus "
                    "trae miembros de tribunal con PPN. Se omite.")
        return None

    componentes = list(nx.connected_components(g))
    mayor = max(componentes, key=len)

    try:
        comunidades = nx.community.louvain_communities(g, seed=42)
        modularidad = nx.community.modularity(g, comunidades)
    except Exception as e:                      # noqa: BLE001
        log.warning("Fallo la deteccion de comunidades (%s). Se emiten las "
                    "metricas basicas sin particion (regla F.2).", e)
        comunidades, modularidad = [set(g.nodes())], 0.0

    grados = dict(g.degree())
    resultado = {
        "n_nodos": g.number_of_nodes(),
        "n_aristas": g.number_of_edges(),
        "n_componentes": len(componentes),
        "componente_mayor_n": len(mayor),
        "componente_mayor_pct": round(len(mayor) / g.number_of_nodes() * 100, 1),
        "grado_medio": round(sum(grados.values()) / len(grados), 2),
        "n_comunidades": len(comunidades),
        "modularidad": round(modularidad, 3),
        "comunidades": comunidades,
        "grados": grados,
        "particion_poco_informativa": modularidad >= float(umbral_modularidad),
    }

    if resultado["particion_poco_informativa"]:
        log.warning("MODULARIDAD %.3f, por encima del umbral %.2f.",
                    modularidad, float(umbral_modularidad))
        log.warning("  El grafo esta cerca de ser un conjunto de componentes "
                    "disjuntos. El tribunal de cada tesis es un clique, de "
                    "modo que con pocas tesis compartiendo jurados la "
                    "particion reproduce las tesis, no comunidades del campo.")
        log.warning("  Los clusters de la figura NO deben leerse como grupos "
                    "academicos mientras esto se cumpla.")
    return resultado


def etiquetas_de_comunidad(g, comunidades, grados, minimo_nodos):
    """Etiqueta cada comunidad con la persona de mayor grado DENTRO de ella.

    Se etiqueta a quien mas conexiones tiene en su propia comunidad, no en el
    grafo entero: la etiqueta describe el cluster, no el corpus.

    Las comunidades por debajo de minimo_nodos no se etiquetan, para que la
    figura no quede cubierta de nombres de grupos de dos personas.
    """
    etiquetas = {}
    for i, com in enumerate(comunidades):
        if len(com) < minimo_nodos:
            continue
        central = max(com, key=lambda n: grados.get(n, 0))
        etiquetas[i] = (central,
                        g.nodes[central].get("label", central),
                        len(com))
    return etiquetas


# =========================================================================
# COMPLETITUD Y CONSISTENCIA
# =========================================================================

def completitud_por_columna(filas, columnas):
    """Proporcion rellena de cada columna sobre el corpus analizado.

    NO mide si theses.fr tiene lagunas -- eso depende de que cada institucion
    haya depositado, y no se puede comprobar desde la API. Mide que analisis
    se pueden hacer sobre ESTE corpus.
    """
    total = len(filas)
    resultado = []
    for c in columnas:
        llenas = sum(1 for f in filas if str(f.get(c) or "").strip())
        resultado.append((c, llenas, round(llenas / total * 100, 1) if total else 0.0))
    return sorted(resultado, key=lambda x: x[2])


def cobertura_ppn(filas, roles_activos):
    """Proporcion de miembros de tribunal que traen PPN de persona.

    Es el TECHO de cualquier metrica de persistencia o recurrencia: sin PPN
    no hay desambiguacion posible y la persona no entra en el conteo.

    La cobertura NO es aleatoria. La composicion del tribunal falta de forma
    sistematica en el material antiguo (Aboucaya & Jasim, 2026), de modo que
    lo que falta se concentra en un extremo del periodo.

    Devuelve (n_con_ppn, n_sin_ppn, pct, {periodo_o_anho: pct}).
    """
    con, sin = 0, 0
    por_anho = defaultdict(lambda: [0, 0])
    for f in filas:
        por_ppn, sin_ppn = personas_de_fila(f, roles_activos)
        con += len(por_ppn)
        sin += sin_ppn
        a = anho_de(f.get("dateSoutenance"))
        if a is not None:
            por_anho[a][0] += len(por_ppn)
            por_anho[a][1] += sin_ppn
    total = con + sin
    pct = round(con / total * 100, 1) if total else 0.0
    por_anho_pct = {a: round(v[0] / (v[0] + v[1]) * 100, 1)
                    for a, v in sorted(por_anho.items()) if (v[0] + v[1])}
    return con, sin, pct, por_anho_pct


def consistencia(filas, columnas, log):
    """Contradicciones internas del registro. Cada una se reporta con su
    conteo (regla D.4); ninguna se corrige.

      - status defendida sin NNT
      - fecha de defensa anterior a la de primera inscripcion en el doctorado
      - tesis sin autor
    """
    incidencias = {
        "defendida_sin_nnt": 0,
        "defensa_antes_de_inscripcion": 0,
        "sin_autor": 0,
        "sin_fecha_defensa": 0,
    }
    omitidas = []

    if "status" not in columnas or "nnt" not in columnas:
        omitidas.append("defendida_sin_nnt (falta status o nnt)")
    if "datePremiereInscriptionDoctorat" not in columnas:
        omitidas.append("defensa_antes_de_inscripcion (falta la fecha de "
                        "primera inscripcion)")
    if "auteurs" not in columnas:
        omitidas.append("sin_autor (falta la columna auteurs)")

    # Una columna PRESENTE pero vacia en todo el corpus no permite comprobar
    # nada, y un contador en cero se leeria como "no hay contradicciones"
    # cuando lo cierto es "no se pudo mirar". Son cosas distintas: la primera
    # es un resultado, la segunda una laguna.
    #
    # Origen: datePremiereInscriptionDoctorat esta al 0% en el corpus (el
    # endpoint de busqueda no parece devolverlo) y al 1,6% en el indice. La
    # comprobacion de orden de fechas no puede dispararse nunca, y v0.2
    # reportaba un cero tranquilizador.
    sin_datos = set()
    for columna, etiqueta in (("datePremiereInscriptionDoctorat",
                               "defensa_antes_de_inscripcion"),
                              ("auteurs", "sin_autor"),
                              ("nnt", "defendida_sin_nnt")):
        if columna in columnas and not any(
                str(f.get(columna) or "").strip() for f in filas):
            sin_datos.add(etiqueta)
            omitidas.append("%s (la columna '%s' esta presente pero VACIA en "
                            "todo el corpus: no es que no haya "
                            "contradicciones, es que no se puede comprobar)"
                            % (etiqueta, columna))

    for f in filas:
        if "status" in columnas and "nnt" in columnas:
            estado = str(f.get("status") or "").strip().lower()
            if estado.startswith("soutenue") and not str(f.get("nnt") or "").strip():
                incidencias["defendida_sin_nnt"] += 1

        if "datePremiereInscriptionDoctorat" in columnas:
            defensa = anho_de(f.get("dateSoutenance"))
            inscripcion = anho_de(f.get("datePremiereInscriptionDoctorat"))
            if defensa is not None and inscripcion is not None and defensa < inscripcion:
                incidencias["defensa_antes_de_inscripcion"] += 1

        if "auteurs" in columnas and not parsear_personas(f.get("auteurs")):
            incidencias["sin_autor"] += 1

        if anho_de(f.get("dateSoutenance")) is None:
            incidencias["sin_fecha_defensa"] += 1

    for etiqueta in sin_datos:
        incidencias[etiqueta] = SIN_DATO

    for o in omitidas:
        log.warning("Comprobacion de consistencia omitida: %s (regla D.6).", o)
    return incidencias, omitidas


def sesgo_primero_enero(filas):
    """Proporcion del corpus con fecha de defensa el 1 de enero.

    Las tesis impresas de las que solo se conoce el anho se registran como
    AAAA-01-01, lo que produce una acumulacion artificial en esa fecha,
    concentrada en el material antiguo. Esto NO corrige nada: mide cuanto
    pesa el artefacto para poder juzgar la granularidad de las fechas.
    """
    con_fecha = [f for f in filas if f.get("dateSoutenance")]
    marcadas = [f for f in con_fecha if es_primero_de_enero(f.get("dateSoutenance"))]
    pct = round(len(marcadas) / len(con_fecha) * 100, 1) if con_fecha else 0.0
    por_decada = Counter()
    for f in marcadas:
        a = anho_de(f.get("dateSoutenance"))
        if a is not None:
            por_decada["%ds" % (a // 10 * 10)] += 1
    return len(marcadas), len(con_fecha), pct, dict(sorted(por_decada.items()))


# =========================================================================
# COMPARACION CONTRA EL INDICE COMPLETO
# =========================================================================

def cabeceras(cfg):
    contacto = cfg.get("api.contacto", "")
    return {"User-Agent": "WPB_TESIS_S03/%s (mailto:%s)" % (VERSION, contacto),
            "Accept": "application/json"}


def peticion(url, cfg, log):
    """GET con reintentos y espera creciente.

    Devuelve (json, codigo_de_error). El codigo es None si todo fue bien.
    Ante fallo devuelve (None, codigo) y NUNCA una estructura vacia que
    pudiera confundirse con un resultado legitimo (regla F.2).
    """
    try:
        import requests
    except ImportError:
        log.warning("requests no esta instalado: se omite la comparacion "
                    "contra el indice (regla F.2).")
        return None, "sin_requests"

    reintentos = int(cfg.get("api.reintentos", 3))
    backoff = float(cfg.get("api.backoff_factor", 2.0))
    timeout = int(cfg.get("api.timeout_segundos", 30))
    heads = cabeceras(cfg)

    for intento in range(1, reintentos + 1):
        try:
            r = requests.get(url, headers=heads, timeout=timeout)
        except requests.RequestException as e:
            log.warning("Fallo de red (intento %d/%d): %s",
                        intento, reintentos, e)
            if intento < reintentos:
                time.sleep(backoff ** intento)
            continue
        if r.status_code == 503:
            log.warning("HTTP 503: el servicio puede estar en mantenimiento. "
                        "Se omite la comparacion contra el indice.")
            return None, 503
        if r.status_code == 200:
            try:
                return r.json(), None
            except json.JSONDecodeError as e:
                log.warning("Respuesta no es JSON valido: %s", e)
                return None, 200
        if 500 <= r.status_code < 600:
            if intento < reintentos:
                time.sleep(backoff ** intento)
            continue
        log.warning("HTTP %d en la consulta al indice. URL: %s",
                    r.status_code, url)
        return None, r.status_code
    return None, None


def contar_en_indice(q, cfg, log):
    """Devuelve el totalHits de una consulta, sin descargar registros.

    totalHits y una lista vacia NO son lo mismo: un 0 legitimo significa que
    la consulta se interpreto y no hay tesis que la cumplan; un fallo
    devuelve None y se propaga como tal.
    """
    base = cfg.get("api.base_url", "https://theses.fr/api/v1/theses/recherche/")
    url = base + "?" + urlencode({"q": q, "debut": 0, "nombre": 1},
                                 quote_via=quote)
    datos, err = peticion(url, cfg, log)
    time.sleep(float(cfg.get("api.pausa_segundos", 1.0)))
    if err is not None or datos is None:
        return None
    return datos.get("totalHits")


def comparar_con_indice(filas, cfg, log):
    """Compara la completitud del corpus con la del indice de theses.fr.

    POR QUE: un 60% de resumenes no dice lo mismo si el indice esta al 85%
    que si esta al 62%. En el primer caso el corpus esta peor que la media y
    hay algo que entender; en el segundo esta en la media. El mismo numero,
    conclusiones opuestas.

    LIMITE 1: _exists_ dice si el campo esta presente, no si el contenido
    sirve. Un resumen de diez palabras cuenta igual que uno de mil.

    LIMITE 2: el acotado por rango de anhos NO esta verificado. Se comprueba
    en tiempo de ejecucion comparando el total acotado con el total del
    indice: si coinciden, la restriccion se esta ignorando y la comparacion
    es contra el indice ENTERO. En ese caso se avisa y se dice contra que se
    comparo de verdad, en lugar de presentar como acotado algo que no lo esta
    (reglas B.3 y F.2).
    """
    anhos = [a for a in (anho_de(f.get("dateSoutenance")) for f in filas)
             if a is not None]
    if not anhos:
        log.warning("El corpus no tiene ninguna fecha de defensa utilizable: "
                    "se omite la comparacion contra el indice.")
        return None

    desde, hasta = min(anhos), max(anhos)
    restriccion = "dateSoutenance:[%d-01-01 TO %d-12-31]" % (desde, hasta)

    log.info("Comparacion contra el indice de theses.fr (%d-%d).", desde, hasta)

    total_indice = contar_en_indice("*", cfg, log)
    total_acotado = contar_en_indice(restriccion, cfg, log)

    if total_indice is None or total_acotado is None:
        log.warning("No se pudo obtener el total del indice. Se omite la "
                    "comparacion y se emite el resto del informe (regla F.2).")
        return None

    acotado_efectivo = True
    if total_acotado == total_indice:
        acotado_efectivo = False
        log.warning("El acotado por anhos NO tuvo efecto: el indice devuelve "
                    "%s registros con y sin restriccion.", f"{total_indice:,}")
        log.warning("  La comparacion es contra el INDICE ENTERO, no contra "
                    "el mismo rango de anhos. Un corpus reciente comparado "
                    "contra todo el indice puede parecer mas completo de lo "
                    "que esta, porque el material antiguo arrastra la media "
                    "del indice hacia abajo.")

    referencia = total_acotado if acotado_efectivo else total_indice
    if not referencia:
        log.warning("El total de referencia es 0: se omite la comparacion.")
        return None

    resultado = {
        "desde": desde,
        "hasta": hasta,
        "acotado_efectivo": acotado_efectivo,
        "total_referencia": referencia,
        "total_indice": total_indice,
        "campos": [],
    }

    n_corpus = len(filas)
    for campo, columna in CAMPOS_INDICE.items():
        q = "_exists_:%s" % campo
        if acotado_efectivo:
            q += " AND " + restriccion
        n = contar_en_indice(q, cfg, log)
        if n is None:
            log.warning("  %s: la consulta fallo, se omite este campo.", campo)
            continue
        pct_indice = round(n / referencia * 100, 1)
        llenas = sum(1 for f in filas if str(f.get(columna) or "").strip())
        pct_corpus = round(llenas / n_corpus * 100, 1) if n_corpus else 0.0

        # GUARDIA DE IMPOSIBILIDAD ARITMETICA. El corpus es un SUBCONJUNTO
        # del indice: ningun campo puede estar presente en el corpus y
        # ausente en el indice. Si eso ocurre, el nombre del campo no es el
        # interrogable y la consulta devolvio 0 sin fallar (HTTP 200).
        #
        # Se omite del informe en lugar de imprimir el numero: un 58,7%
        # frente a 0,0% se leeria como una diferencia enorme a favor del
        # corpus, que es lo contrario de lo que pasa. Es el fallo que v0.2
        # tuvo con sujetsLibelle.
        if n == 0 and llenas > 0:
            log.error("  %s: el indice devuelve 0 registros con el campo, "
                      "pero el corpus lo tiene relleno en %d filas (%.1f%%).",
                      campo, llenas, pct_corpus)
            log.error("    Es imposible: el corpus es un subconjunto del "
                      "indice. El nombre '%s' no es el interrogable, y la "
                      "consulta devolvio 0 sin fallar (reglas B.1 y B.3).",
                      campo)
            log.error("    Se OMITE del informe. Verificar el nombre contra "
                      "CAMPOS_PALABRAS_CLAVE de S01 antes de volver a "
                      "declararlo aqui.")
            continue

        resultado["campos"].append({
            "campo": campo,
            "columna": columna,
            "pct_corpus": pct_corpus,
            "pct_indice": pct_indice,
            "diferencia": round(pct_corpus - pct_indice, 1),
        })
        log.info("  %-32s corpus %5.1f%%   indice %5.1f%%",
                 campo, pct_corpus, pct_indice)
    return resultado


# =========================================================================
# VISUALIZACION
# =========================================================================

def preparar_matplotlib(log):
    """Importa matplotlib en modo sin ventana. Devuelve el modulo o None."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        log.warning("matplotlib no esta instalado: se OMITEN todas las "
                    "figuras. Las series y el informe se emiten igual "
                    "(regla F.2).")
        return None


def colores_por_concepto(conceptos, paleta, log):
    """Un color fijo por concepto, el mismo en todas las figuras.

    Si hay mas conceptos que colores, la paleta se repite ciclicamente y se
    deja constancia: dos conceptos compartiran color y la comparativa deja de
    distinguirlos sin leer la leyenda.
    """
    if not paleta:
        paleta = ["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]
    if len(conceptos) > len(paleta):
        log.warning("Hay %d conceptos y %d colores en la paleta: se repite "
                    "ciclicamente y habra conceptos con el mismo color.",
                    len(conceptos), len(paleta))
    return {c: paleta[i % len(paleta)] for i, c in enumerate(conceptos)}


def figura_concepto(concepto, series, color, rutas, cfg, plt, log):
    """Barras de tesis por periodo (eje izquierdo) y lineas de acumulado y
    persistencia (eje derecho, 0-100 para el porcentaje).

    Los periodos sin persistencia calculable se dibujan como hueco, no como
    cero: la linea se interrumpe donde no hay dato.
    """
    periodos = series["periodo"]
    n_tesis = series.get("n_tesis_anual", [])
    acumulado = series.get("n_tesis_acumulado", [])
    persistencia = series.get("persistencia_tribunal", [])

    fig, ax = plt.subplots(figsize=(float(cfg.get("visualizacion.figura_ancho", 14)),
                                    float(cfg.get("visualizacion.figura_alto", 6))))
    if n_tesis:
        ax.bar(periodos, n_tesis, color=color, alpha=0.75, label="tesis")
    if acumulado:
        ax.plot(periodos, acumulado, color=color, linewidth=2,
                linestyle="--", label="acumulado")
    ax.set_ylabel("numero de tesis")
    ax.set_xlabel("periodo")

    if persistencia:
        ax2 = ax.twinx()
        y = [v if v != SIN_DATO else float("nan") for v in persistencia]
        ax2.plot(periodos, y, color="#333333", linewidth=1.8, marker="o",
                 markersize=4, label="persistencia del tribunal (%)")
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("persistencia del tribunal (%)")
        lineas, etiquetas = ax.get_legend_handles_labels()
        l2, e2 = ax2.get_legend_handles_labels()
        ax.legend(lineas + l2, etiquetas + e2, loc="upper left", fontsize=9)
    else:
        ax.legend(loc="upper left", fontsize=9)

    ax.set_title("%s -- tesis por periodo y persistencia del tribunal"
                 % concepto)
    if len(periodos) > 12:
        plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    fig.tight_layout()
    guardar_figura(fig, rutas, cfg, plt, log)


def figura_comparativa(series_por_concepto, colores, rutas, cfg, plt, log):
    """Todos los conceptos superpuestos, en numero de tesis por periodo."""
    fig, ax = plt.subplots(figsize=(float(cfg.get("visualizacion.figura_ancho", 14)),
                                    float(cfg.get("visualizacion.figura_alto", 6))))
    for concepto, series in series_por_concepto.items():
        if not series.get("n_tesis_anual"):
            continue
        ax.plot(series["periodo"], series["n_tesis_anual"],
                label=concepto, color=colores.get(concepto), linewidth=2,
                marker="o", markersize=3)
    ax.set_xlabel("periodo")
    ax.set_ylabel("numero de tesis")
    ax.set_title("Tesis por periodo, todos los conceptos")
    ax.legend(fontsize=9)
    primer = next(iter(series_por_concepto.values()), {"periodo": []})
    if len(primer["periodo"]) > 12:
        plt.setp(ax.get_xticklabels(), rotation=90, fontsize=7)
    fig.tight_layout()
    guardar_figura(fig, rutas, cfg, plt, log)


def figura_solapamiento(matriz, conceptos, rutas, cfg, plt, log):
    """Tabla de doble entrada codificada por color.

    La diagonal es el tamanho de cada subcorpus, de modo que domina la escala
    y aplasta el resto. Se enmascara para que el color mida el SOLAPAMIENTO,
    que es lo que la tabla quiere mostrar; el valor de la diagonal se escribe
    igual en la celda.
    """
    n = len(conceptos)
    valores = [[matriz[a][b] for b in conceptos] for a in conceptos]
    fuera_diagonal = [valores[i][j] for i in range(n) for j in range(n) if i != j]
    tope = max(fuera_diagonal) if fuera_diagonal else 1

    fig, ax = plt.subplots(figsize=(max(6, n * 1.2), max(5, n * 1.0)))
    datos = [[(valores[i][j] if i != j else tope) for j in range(n)]
             for i in range(n)]
    im = ax.imshow(datos, cmap="YlGnBu", vmin=0, vmax=max(tope, 1))

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(conceptos, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(conceptos, fontsize=8)

    for i in range(n):
        for j in range(n):
            v = valores[i][j]
            ax.text(j, i, str(v), ha="center", va="center", fontsize=8,
                    color="white" if (i == j or v > tope * 0.6) else "black")

    ax.set_title("Tesis compartidas entre conceptos\n"
                 "(diagonal = tamanho del subcorpus, fuera de escala)",
                 fontsize=10)
    fig.colorbar(im, ax=ax, shrink=0.8, label="tesis en comun")
    fig.tight_layout()
    guardar_figura(fig, rutas, cfg, plt, log)


def figura_red(g, analisis, etiquetas, rutas, cfg, plt, log):
    """Dibuja la red total con los nodos coloreados por comunidad.

    Las etiquetas son la persona de mayor grado dentro de cada comunidad. Se
    etiquetan solo las comunidades por encima del minimo, para que la figura
    siga siendo legible.

    Si la modularidad supero el umbral, el pie de la figura lo declara: sin
    ese aviso, un lector veria clusters nitidos y los leeria como grupos
    academicos cuando pueden ser simplemente tesis distintas.
    """
    import networkx as nx

    comunidad_de = {}
    for i, com in enumerate(analisis["comunidades"]):
        for nodo in com:
            comunidad_de[nodo] = i

    paleta = cfg.get("visualizacion.paleta", []) or ["#264653"]
    colores = [paleta[comunidad_de.get(n, 0) % len(paleta)] for n in g.nodes()]
    grados = analisis["grados"]
    tamanhos = [60 + 40 * grados.get(n, 0) for n in g.nodes()]

    fig, ax = plt.subplots(figsize=(float(cfg.get("visualizacion.figura_ancho", 14)),
                                    float(cfg.get("visualizacion.figura_ancho", 14)) * 0.7))
    pos = nx.spring_layout(g, seed=42, k=None)
    nx.draw_networkx_edges(g, pos, ax=ax, alpha=0.25, width=0.6)
    nx.draw_networkx_nodes(g, pos, ax=ax, node_color=colores,
                           node_size=tamanhos, linewidths=0.4,
                           edgecolors="white")

    # La etiqueta se desplaza hacia arriba para no tapar el nodo que nombra:
    # centrada encima del nodo, el recuadro blanco lo ocultaba.
    if pos:
        alturas = [y for _, y in pos.values()]
        desplazamiento = (max(alturas) - min(alturas)) * 0.04 or 0.04
    else:
        desplazamiento = 0.04
    for i, (ppn, etiqueta, tam) in etiquetas.items():
        if ppn in pos:
            x, y = pos[ppn]
            ax.text(x, y + desplazamiento, "%s\n(%d)" % (etiqueta, tam),
                    fontsize=8, ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                              alpha=0.75, linewidth=0))

    ax.set_axis_off()
    ax.set_title("Red de co-participacion en tribunales -- corpus completo\n"
                 "%d personas, %d vinculos, %d comunidades (modularidad %.3f)"
                 % (analisis["n_nodos"], analisis["n_aristas"],
                    analisis["n_comunidades"], analisis["modularidad"]),
                 fontsize=11)

    pie = ("Nodo = miembro de tribunal (por PPN de persona). Vinculo = haber "
           "estado en el mismo tribunal.\n"
           "Etiqueta = persona de mayor grado dentro de su comunidad; entre "
           "parentesis, el tamanho de la comunidad.")
    if analisis["particion_poco_informativa"]:
        pie += ("\nAVISO: modularidad %.3f. El grafo esta cerca de ser un "
                "conjunto de componentes disjuntos: los clusters pueden "
                "reproducir las tesis, no comunidades del campo."
                % analisis["modularidad"])
    fig.text(0.01, 0.01, pie, fontsize=7, va="bottom", color="#444444")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    guardar_figura(fig, rutas, cfg, plt, log)


def guardar_figura(fig, rutas, cfg, plt, log):
    """Escribe la figura en el formato declarado y cierra el objeto.

    rutas es la ruta SIN extension: la extension la fija visualizacion.formato.
    """
    formato = str(cfg.get("visualizacion.formato", "png")).lower()
    if formato not in ("png", "pdf", "svg"):
        log.warning("visualizacion.formato = %r no reconocido. Valores "
                    "validos: png | pdf | svg. Se usa png.", formato)
        formato = "png"
    destino = "%s.%s" % (rutas, formato)
    fig.savefig(destino, dpi=int(cfg.get("visualizacion.dpi", 150)),
                format=formato, bbox_inches="tight")
    plt.close(fig)
    log.info("  figura: %s", destino)


# =========================================================================
# SALIDAS
# =========================================================================

def nombres_salida(cfg, iteracion, diccionario):
    """Rutas de salida a partir del patron.

    El identificador de corrida aparece en el nombre para que dos corridas
    con distinta iteracion no se pisen (regla C.5). La iteracion NO se
    declara en este YAML: se deriva del nombre del CSV de entrada (regla C.6).
    """
    directorio = cfg.get("output.directorio", "salidas/analisis/")
    patron = cfg.get("output.patron_nombre", "WPB_TESIS_{iter}_S03")
    base = patron.format(iter=iteracion, dicc=diccionario)
    os.makedirs(directorio, exist_ok=True)
    return {
        "dir": directorio,
        "base": base,
        "informe": os.path.join(directorio, base + "_informe.txt"),
        "config": os.path.join(directorio, base + "_config_usado.yaml"),
        "solapamiento_csv": os.path.join(directorio, base + "_solapamiento.csv"),
        "corpus_csv": os.path.join(directorio, base + "_descripcion_corpus.csv"),
        "red_gexf": os.path.join(directorio, base + "_red.gexf"),
        "fig_red": os.path.join(directorio, base + "_red"),
        "fig_comparativa": os.path.join(directorio, base + "_comparativa"),
        "fig_solapamiento": os.path.join(directorio, base + "_solapamiento"),
    }


def ruta_serie(rutas, concepto):
    return os.path.join(rutas["dir"], "%s_serie_%s.csv"
                        % (rutas["base"], normalizar_para_archivo(concepto)))


def ruta_figura_concepto(rutas, concepto):
    return os.path.join(rutas["dir"], "%s_concepto_%s"
                        % (rutas["base"], normalizar_para_archivo(concepto)))


def confirmar_sobrescritura(rutas, cfg, force, log):
    """Detecta archivos existentes que coincidan con el patron, los lista y
    pide confirmacion antes de escribir (regla C.1).

    --force salta la confirmacion y GANA sobre el YAML. El override efectivo
    se registra en el log y se anota en la copia archivada de la
    configuracion (regla A.5).

    Sin terminal interactiva y sin --force, ABORTA en lugar de esperar
    (regla C.2): un input() sin salvaguarda cuelga indefinidamente en
    notebook, cron o pipeline encadenado.

    S03 NO elimina archivos huerfanos de corridas previas (regla C.4): si
    cambia el diccionario de conceptos entre corridas con la misma iteracion,
    las series de la corrida anterior sobreviven junto a las nuevas.
    """
    patron = re.compile(re.escape(rutas["base"]))
    existentes = []
    if os.path.isdir(rutas["dir"]):
        for nombre in sorted(os.listdir(rutas["dir"])):
            if patron.match(nombre) and not nombre.endswith(".log"):
                existentes.append(os.path.join(rutas["dir"], nombre))
    if not existentes:
        return

    if force:
        log.warning("OVERRIDE: --force declarado en la linea de comandos. "
                    "Gana sobre output.confirmar_sobrescritura. Se "
                    "sobrescriben %d archivos sin preguntar.", len(existentes))
        for p in existentes:
            log.warning("  se sobrescribe: %s", p)
        return

    if not cfg.get("output.confirmar_sobrescritura", True):
        log.warning("output.confirmar_sobrescritura = false. Se sobrescriben "
                    "%d archivos sin preguntar.", len(existentes))
        return

    print("\nATENCION: ya existen estos archivos de salida:")
    for p in existentes:
        print("  %s" % p)

    if not sys.stdin.isatty():
        log.error("No hay terminal interactiva y no se declaro --force. Se "
                  "aborta en lugar de esperar una confirmacion que nadie "
                  "puede dar (regla C.2).")
        sys.exit(1)

    resp = input("Sobrescribir? [s/N]: ").strip().lower()
    if resp not in ("s", "si", "y", "yes"):
        log.info("Cancelado por el usuario. No se escribio nada.")
        sys.exit(0)


def archivar_config(ruta_yaml, destino, overrides, log):
    """Copia el YAML tal como fue leido, junto a los outputs (regla D.1).

    El original se sigue editando; la copia congela el estado que produjo
    estos datos. Los overrides de linea de comandos se anotan APARTE, al
    final del archivo: la copia debe reflejar el estado que produjo los
    datos, y un flag que pisa un valor del YAML no queda registrado copiando
    el YAML sin mas (regla A.5).
    """
    try:
        shutil.copyfile(ruta_yaml, destino)
    except OSError as e:
        log.warning("No se pudo archivar la configuracion: %s", e)
        return
    if overrides:
        try:
            with open(destino, "a", encoding="utf-8") as f:
                f.write("\n\n# " + "=" * 68 + "\n")
                f.write("# OVERRIDES DE LINEA DE COMANDOS EN ESTA CORRIDA\n")
                f.write("# " + "=" * 68 + "\n")
                f.write("# Estos valores PISARON lo declarado arriba "
                        "(regla A.5).\n")
                for clave, valor in overrides:
                    f.write("#   %s -> %s\n" % (clave, valor))
        except OSError as e:
            log.warning("No se pudo anotar el override en la copia: %s", e)
    log.info("Configuracion archivada: %s", destino)


def escribir_serie_csv(ruta, series):
    """Una serie por concepto, para poder rehacer los graficos aparte."""
    columnas = [c for c in ("periodo", "n_tesis_anual", "n_tesis_acumulado",
                            "n_personas_distintas", "persistencia_tribunal")
                if c in series]
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        for i in range(len(series["periodo"])):
            w.writerow([series[c][i] for c in columnas])


def escribir_solapamiento_csv(ruta, matriz, conceptos):
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["concepto"] + conceptos)
        for a in conceptos:
            w.writerow([a] + [matriz[a][b] for b in conceptos])


def escribir_corpus_csv(ruta, descripcion):
    columnas = ["concepto", "n_tesis", "n_tesis_unicas", "anho_primero",
                "anho_ultimo", "sin_fecha"]
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        for fila in descripcion:
            w.writerow(fila)


def escribir_gexf(g, analisis, ruta, log):
    """Emite la red en GEXF, que es el formato que consume Retina
    (https://retina.cortext.net/, OuestWare y CNRS CIS).

    Se escribe la comunidad y el grado como atributos de nodo, de modo que
    Retina pueda colorear y dimensionar sin recalcular nada.
    """
    import networkx as nx

    comunidad_de = {}
    for i, com in enumerate(analisis["comunidades"]):
        for nodo in com:
            comunidad_de[nodo] = i
    for nodo in g.nodes():
        g.nodes[nodo]["comunidad"] = comunidad_de.get(nodo, -1)
        g.nodes[nodo]["grado"] = analisis["grados"].get(nodo, 0)
        g.nodes[nodo]["ppn"] = nodo
    try:
        nx.write_gexf(g, ruta, encoding="utf-8")
        log.info("  red en GEXF: %s", ruta)
        log.info("  se puede abrir en https://retina.cortext.net/ sin "
                 "conversion previa.")
    except (OSError, TypeError) as e:
        log.warning("No se pudo escribir el GEXF: %s", e)


# =========================================================================
# INFORME
# =========================================================================

def escribir_informe(ruta, ctx):
    """Informe de texto. Declara SIEMPRE en que modo corrio y con que
    universo, porque las metricas de persistencia no significan lo mismo
    segun el modo (ver filtrar_por_modo).
    """
    L = []
    ap = L.append

    ap("=" * 74)
    ap("WPB_TESIS_S03 -- INFORME DE ANALISIS")
    ap("=" * 74)
    ap("")
    ap("Corrida:            %s" % ctx["corrida"])
    ap("Script:             WPB_TESIS_S03_analisis.py v%s" % VERSION)
    ap("Configuracion:      %s" % ctx["ruta_config"])
    ap("CSV de entrada:     %s" % ctx["ruta_csv"])
    ap("Iteracion:          %s (derivada del nombre del CSV, regla C.6)" % ctx["iteracion"])
    ap("Origen de los datos: API de busqueda de theses.fr (no el data dump")
    ap("                     Etalab ni el dataset Aboucaya & Jasim 2026).")
    ap("")
    ap("-" * 74)
    ap("UNIVERSO ANALIZADO")
    ap("-" * 74)
    ap("Modo:               %s" % ctx["modo"])
    if ctx["modo"] == "candidatos":
        ap("  Se analizan todas las filas, curadas o no.")
    else:
        ap("  Se analizan solo las filas con 'validado' afirmativo.")
    ap("")
    ap("  La curacion cambia lo que MIDEN las metricas de persistencia, no")
    ap("  solo cuantas filas entran. 'Ya habia aparecido antes' es relativo")
    ap("  al universo analizado: una jurado que estuvo en tres tesis")
    ap("  descartadas y aparece en una validada cuenta como nueva en modo")
    ap("  'validados' y como recurrente en modo 'candidatos'.")
    ap("")
    ap("Filas en el CSV:    %d" % ctx["n_filas_csv"])
    ap("Filas analizadas:   %d" % ctx["n_filas"])
    ap("Tesis distintas:    %d" % ctx["n_tesis_unicas"])
    ap("  El CSV tiene una fila por (tesis, concepto): una tesis recuperada")
    ap("  por dos terminos aparece dos veces. Las metricas POR CONCEPTO usan")
    ap("  las filas de ese concepto; las del CORPUS COMPLETO usan las tesis")
    ap("  distintas, para no contarla dos veces.")
    ap("Descartadas por el modo:     %d" % ctx["descartadas_modo"])
    if ctx["recorte_activo"]:
        ap("Recorte temporal:   %s a %s  (ACTIVO)"
           % (ctx["anho_inicio"], ctx["anho_fin"]))
        ap("  descartadas fuera del periodo:   %d" % ctx["descartadas_periodo"])
        ap("  descartadas sin fecha:           %d" % ctx["descartadas_sin_fecha"])
        ap("  Las metricas NO son comparables con una corrida sin recorte.")
    else:
        ap("Recorte temporal:   sin recorte")
    ap("Granularidad:       %s%s"
       % (ctx["granularidad"],
          " de %d anhos" % ctx["tramo"] if ctx["granularidad"] == "tramos" else ""))
    ap("")

    ap("-" * 74)
    ap("DESCRIPCION DEL CORPUS POR TERMINO")
    ap("-" * 74)
    ap("n_tesis        filas que ese termino recupero")
    ap("unicas         de ellas, las que NINGUN otro termino recupero")
    ap("cobertura      primer y ultimo anho con tesis de ese termino")
    ap("")
    ap("%-28s %8s %8s %14s %8s" % ("termino", "n_tesis", "unicas",
                                   "cobertura", "s/fecha"))
    for d in ctx["descripcion"]:
        cobertura = ("%s-%s" % (d["anho_primero"], d["anho_ultimo"])
                     if d["anho_primero"] != SIN_DATO else "sin fechas")
        ap("%-28s %8d %8d %14s %8d"
           % (d["concepto"][:28], d["n_tesis"], d["n_tesis_unicas"],
              cobertura, d["sin_fecha"]))
    ap("")

    if ctx.get("matriz") is not None:
        ap("-" * 74)
        ap("SOLAPAMIENTO ENTRE TERMINOS")
        ap("-" * 74)
        ap("Tesis recuperadas por mas de un termino: %d" % ctx["multiples"])
        ap("La suma de los subcorpus SUPERA el tamanho del corpus, y es")
        ap("correcto: una tesis pertenece a todos los terminos que la")
        ap("recuperaron.")
        ap("La tabla completa esta en %s" % os.path.basename(ctx["ruta_solapamiento"]))
        ap("")

    ap("-" * 74)
    ap("PERSONAS MAS RECURRENTES -- CORPUS COMPLETO")
    ap("-" * 74)
    ap("Unidad: NUMERO DE TESIS. Una persona que figura en dos roles de la")
    ap("misma tesis cuenta UNA vez (deduplicada por PPN dentro de la fila).")
    ap("Identificador: PPN de persona en IdRef, resoluble en idref.fr/{ppn}.")
    ap("Roles contados: %s" % ", ".join(ctx["roles_activos"]))
    ap("")
    ap("%-38s %-12s %6s" % ("persona", "PPN", "tesis"))
    for ppn, nombre, n in ctx["top_personas_global"]:
        ap("%-38s %-12s %6d" % (nombre[:38], ppn, n))
    ap("")

    for concepto, top in ctx["top_personas_concepto"].items():
        if not top:
            continue
        ap("  [%s]" % concepto)
        for ppn, nombre, n in top:
            ap("    %-36s %-12s %4d" % (nombre[:36], ppn, n))
        ap("")

    if ctx.get("top_instituciones_global") is not None:
        ap("-" * 74)
        ap("INSTITUCIONES DE DEFENSA")
        ap("-" * 74)
        ap("Es la institucion DONDE SE DEFENDIO la tesis. NO es la")
        ap("institucion de los miembros del tribunal, que el registro no")
        ap("contiene.")
        ap("")
        for nombre, n in ctx["top_instituciones_global"]:
            ap("  %-58s %4d" % (nombre[:58], n))
        ap("")
        for concepto, top in ctx["top_instituciones_concepto"].items():
            if not top:
                continue
            ap("  [%s]" % concepto)
            for nombre, n in top:
                ap("    %-56s %4d" % (nombre[:56], n))
            ap("")

    if ctx.get("top_disciplinas_concepto") is not None:
        ap("-" * 74)
        ap("DISCIPLINAS")
        ap("-" * 74)
        ap("Texto libre segun la especificacion TEF: las variantes")
        ap("ortograficas NO se agrupan y cuentan por separado.")
        ap("")
        for concepto, top in ctx["top_disciplinas_concepto"].items():
            if not top:
                continue
            ap("  [%s]" % concepto)
            for nombre, n in top:
                ap("    %-56s %4d" % (nombre[:56], n))
            ap("")

    if ctx.get("red") is not None:
        r = ctx["red"]
        ap("-" * 74)
        ap("RED DE CO-PARTICIPACION EN TRIBUNALES -- CORPUS COMPLETO")
        ap("-" * 74)
        ap("Nodo = miembro de tribunal (PPN de persona).")
        ap("Vinculo = haber estado en el mismo tribunal.")
        ap("Tesis que aportaron al grafo: %d de %d"
           % (ctx["red_tesis_aportadas"], ctx["n_filas"]))
        ap("")
        ap("  personas (nodos):        %d" % r["n_nodos"])
        ap("  vinculos (aristas):      %d" % r["n_aristas"])
        ap("  componentes:             %d" % r["n_componentes"])
        ap("  componente mayor:        %d personas (%.1f%%)"
           % (r["componente_mayor_n"], r["componente_mayor_pct"]))
        ap("  grado medio:             %.2f" % r["grado_medio"])
        ap("  comunidades (Louvain):   %d" % r["n_comunidades"])
        ap("  modularidad:             %.3f" % r["modularidad"])
        ap("")
        if r["particion_poco_informativa"]:
            ap("  AVISO: la modularidad supera el umbral configurado.")
            ap("  El tribunal de cada tesis es un clique completo. Si las")
            ap("  tesis casi no comparten jurados, el grafo es un conjunto de")
            ap("  cliques casi disjuntos y las comunidades reproducen las")
            ap("  tesis, no agrupamientos del campo. Los clusters de la")
            ap("  figura no deben leerse como grupos academicos mientras")
            ap("  esto se cumpla.")
            ap("")
        ap("  Comunidades por encima del minimo, etiquetadas con la persona")
        ap("  de mayor grado dentro de cada una:")
        for i, (ppn, etiqueta, tam) in ctx["etiquetas_comunidad"].items():
            ap("    %-38s %-12s %4d personas" % (etiqueta[:38], ppn, tam))
        ap("")

    ap("-" * 74)
    ap("COMPLETITUD")
    ap("-" * 74)
    ap("Mide que analisis se pueden hacer sobre ESTE corpus. NO mide si")
    ap("theses.fr tiene lagunas: eso depende de que cada institucion haya")
    ap("depositado y no se puede comprobar desde la API.")
    ap("")

    if ctx.get("cobertura_ppn") is not None:
        con, sin, pct, por_anho = ctx["cobertura_ppn"]
        ap("Cobertura de PPN en miembros de tribunal:")
        ap("  con PPN:  %d" % con)
        ap("  sin PPN:  %d" % sin)
        ap("  cobertura: %.1f%%" % pct)
        ap("")
        ap("  Es el TECHO de las metricas de persistencia: quien no trae PPN")
        ap("  no entra en el conteo, y cotejar por nombre no es alternativa")
        ap("  porque nombre y apellido aparecen invertidos en parte de los")
        ap("  registros de theses.fr (Aboucaya & Jasim, 2026).")
        ap("")
        ap("  La cobertura NO es aleatoria: la composicion del tribunal falta")
        ap("  de forma sistematica en el material antiguo. Cobertura por anho:")
        for a, p in sorted(por_anho.items()):
            ap("    %d  %5.1f%%" % (a, p))
        ap("")

    if ctx.get("completitud_columnas") is not None:
        ap("Proporcion rellena por columna (de menor a mayor):")
        for c, llenas, pct in ctx["completitud_columnas"]:
            ap("  %-38s %6d  %5.1f%%" % (c, llenas, pct))
        ap("")

    if ctx.get("consistencia") is not None:
        inc, omitidas = ctx["consistencia"]
        ap("Contradicciones internas del registro:")
        ap("  Un valor 'sin datos' NO significa que no haya contradicciones,")
        ap("  sino que la columna necesaria esta vacia en todo el corpus y la")
        ap("  comprobacion no se pudo hacer.")
        ap("")

        def _v(clave):
            valor = inc.get(clave)
            return "sin datos" if valor == SIN_DATO else str(valor)

        ap("  status defendida sin NNT:              %s" % _v("defendida_sin_nnt"))
        ap("  defensa anterior a la inscripcion:     %s"
           % _v("defensa_antes_de_inscripcion"))
        ap("  tesis sin autor:                       %s" % _v("sin_autor"))
        ap("  tesis sin fecha de defensa:            %s" % _v("sin_fecha_defensa"))
        for o in omitidas:
            ap("  OMITIDA: %s" % o)
        ap("")

    if ctx.get("sesgo_enero") is not None:
        marcadas, con_fecha, pct, por_decada = ctx["sesgo_enero"]
        ap("Sesgo de la fecha 1 de enero:")
        ap("  tesis con fecha 01-01:  %d de %d (%.1f%%)"
           % (marcadas, con_fecha, pct))
        ap("  Las tesis impresas de las que solo se conoce el anho se")
        ap("  registran como AAAA-01-01. Esto no corrige nada: mide cuanto")
        ap("  pesa el artefacto al leer la granularidad de las fechas.")
        if por_decada:
            ap("  Por decada:")
            for d, n in por_decada.items():
                ap("    %-8s %4d" % (d, n))
        ap("")

    if ctx.get("indice") is not None:
        ind = ctx["indice"]
        ap("-" * 74)
        ap("COMPARACION CONTRA EL INDICE DE THESES.FR")
        ap("-" * 74)
        if ind["acotado_efectivo"]:
            ap("Referencia: el indice acotado a %d-%d (%s registros)."
               % (ind["desde"], ind["hasta"], f"{ind['total_referencia']:,}"))
        else:
            ap("AVISO: el acotado por anhos NO tuvo efecto. El indice devolvio")
            ap("el mismo total con y sin restriccion, de modo que la")
            ap("referencia es el INDICE ENTERO (%s registros), no el mismo"
               % f"{ind['total_referencia']:,}")
            ap("rango de anhos que el corpus.")
            ap("Un corpus reciente comparado contra todo el indice puede")
            ap("parecer mas completo de lo que esta.")
        ap("")
        ap("_exists_ dice si el campo esta presente, no si el contenido")
        ap("sirve: un resumen de diez palabras cuenta igual que uno de mil.")
        ap("")
        ap("%-32s %8s %8s %8s" % ("campo", "corpus", "indice", "dif."))
        for c in ind["campos"]:
            ap("%-32s %7.1f%% %7.1f%% %+7.1f" % (c["campo"], c["pct_corpus"],
                                                 c["pct_indice"], c["diferencia"]))
        ap("")

    ap("-" * 74)
    ap("NOTA SOBRE DATOS PERSONALES")
    ap("-" * 74)
    ap("Los rankings de personas y la red de co-participacion son datos")
    ap("personales de personas identificables. La red revela relaciones que")
    ap("ninguna ficha individual contiene: es informacion NUEVA sobre gente")
    ap("concreta, no una reorganizacion de lo publicado.")
    ap("")
    ap("Abes publica los nombres al amparo del articulo 89.1 del RGPD. Eso")
    ap("cubre la fuente, no necesariamente lo que se derive de ella.")
    ap("Sustituir nombres por PPN no anonimiza: el PPN es publico y")
    ap("resoluble en idref.fr.")
    ap("")
    ap("Licencia de los datos: Licence Ouverte / Open Licence 2.0 (Etalab).")
    ap("Atribucion exigida: Agence bibliographique de l'enseignement superieur.")
    ap("")
    ap("=" * 74)
    ap("FIN DEL INFORME")
    ap("=" * 74)

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# =========================================================================
# MAIN
# =========================================================================

def main():
    ap = argparse.ArgumentParser(
        description="WPB_TESIS S03 -- analisis del corpus de tesis.")
    ap.add_argument("--config", default="WPB_TESIS_S03_analisis.yaml",
                    help="Archivo de configuracion (mismo nombre base que "
                         "este script, regla D.5).")
    ap.add_argument("--csv", default=None,
                    help="CSV de entrada. GANA sobre entrada.ruta del YAML; "
                         "el override se anota en el log y en la copia "
                         "archivada de la configuracion (regla A.5).")
    ap.add_argument("--force", action="store_true",
                    help="Sobrescribe sin pedir confirmacion. Se declara en "
                         "cada invocacion y NO se hereda del entorno "
                         "(regla C.3).")
    args = ap.parse_args()

    pre = log_provisional()
    datos = cargar_config(args.config, pre)

    log = configurar_log(
        (datos.get("log") or {}).get("ruta",
                                     "salidas/analisis/WPB_TESIS_S03_analisis.log"),
        (datos.get("log") or {}).get("nivel", "INFO"))
    cfg = Config(datos, log)

    corrida = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    log.info("Proyecto: %s", cfg.get("metadata.proyecto", "sin declarar"))
    log.info("Config: %s", args.config)
    log.info("Identificador de corrida: %s", corrida)

    # Coherencia de versiones (regla D.3). La version del script y la del
    # YAML declaran que uno se escribio para el otro. No es identificador de
    # corrida: eso es la iteracion, y viaja en el nombre de los archivos.
    v_yaml = cfg.get("metadata.version_config", "?")
    if str(v_yaml) != VERSION:
        log.warning("La version del script (%s) y la del YAML (%s) no "
                    "coinciden. Puede haber claves que el script espera y el "
                    "archivo no declara, o al reves.", VERSION, v_yaml)

    # Claves marcadas como NO IMPLEMENTADAS: se leen para avisar si alguien
    # las enciende creyendo que hacen algo (regla A.1).
    for clave, motivo in (
            ("no_implementado.institucion_jurado",
             "el registro de la tesis no contiene la adscripcion del jurado"),
            ("no_implementado.trayectoria_personas",
             "requiere el endpoint de personas; fuera de alcance"),
            ("no_implementado.tfidf",
             "pendiente de decidir en que etapa se calcula"),
            ("no_implementado.venn",
             "ilegible a partir de cuatro conjuntos; se emite la tabla")):
        if cfg.get(clave, False):
            log.warning("'%s' esta en true pero NO esta implementado: %s.",
                        clave, motivo)

    # --- entrada, con el override de --csv registrado (regla A.5) ---
    overrides = []
    ruta_csv = cfg.get("entrada.ruta", obligatorio=True)
    if args.csv:
        log.warning("OVERRIDE: --csv gana sobre entrada.ruta del YAML.")
        log.warning("  YAML:  %s", ruta_csv)
        log.warning("  usado: %s", args.csv)
        overrides.append(("entrada.ruta", args.csv))
        ruta_csv = args.csv

    filas_csv, columnas = leer_corpus(ruta_csv, log)
    iteracion = extraer_iteracion(ruta_csv, log)
    diccionario = extraer_diccionario(ruta_csv)

    rutas = nombres_salida(cfg, iteracion, diccionario)
    confirmar_sobrescritura(rutas, cfg, args.force, log)

    # --- seleccion de filas ---
    modo = str(cfg.get("entrada.modo", "candidatos")).strip().lower()
    aceptados = cfg.get("entrada.valores_validado_si", ["1", "si", "true"])
    if modo not in ("candidatos", "validados", "ambos"):
        log.warning("entrada.modo = %r no reconocido. Valores validos: "
                    "candidatos | validados | ambos. Se usa 'candidatos'.",
                    modo)
        modo = "candidatos"
    if modo == "ambos":
        log.warning("entrada.modo = 'ambos' aun no esta implementado en "
                    "v0.1: se analiza como 'candidatos' y se declara asi en "
                    "el informe. No se emite la comparacion entre los dos "
                    "universos (regla F.2).")
        modo = "candidatos"

    filas = filtrar_por_modo(filas_csv, modo, aceptados, columnas, log)
    descartadas_modo = len(filas_csv) - len(filas)

    # Diagnostico de fechas ANTES de calcular nada: si el formato no es el
    # esperado, el sintoma seria "el corpus no tiene fechas" y apuntaria al
    # dato en lugar de al parseo.
    diagnosticar_fechas(filas, "dateSoutenance", log)

    # --- recorte temporal ---
    anho_inicio = cfg.get("temporal.anho_inicio", None)
    anho_fin = cfg.get("temporal.anho_fin", None)
    recorte_activo = anho_inicio is not None or anho_fin is not None
    filas, desc_periodo, desc_sin_fecha = recortar_periodo(
        filas, anho_inicio, anho_fin, log)

    # --- periodos ---
    anhos = [a for a in (anho_de(f.get("dateSoutenance")) for f in filas)
             if a is not None]
    if not anhos:
        log.error("Ninguna fila tiene fecha de defensa utilizable: no hay "
                  "serie temporal posible. Se aborta (regla F.3).")
        muestra = [f.get("dateSoutenance") for f in filas[:5]]
        log.error("  Valores de dateSoutenance en las primeras filas: %s",
                  ", ".join(repr(v) for v in muestra))
        log.error("  Formatos aceptados: AAAA-MM-DD y DD/MM/AAAA. Si el "
                  "corpus usa otro, hay que anhadirlo a partes_fecha().")
        sys.exit(1)
    granularidad = str(cfg.get("temporal.granularidad", "anual")).strip().lower()
    tramo = cfg.get("temporal.tramo_anhos", 5)
    etiquetas, etiqueta_de = construir_periodos(anhos, granularidad, tramo, log)

    # --- roles de tribunal ---
    roles_activos = [c for c in COLUMNAS_PERSONA
                     if cfg.get("metricas.roles_tribunal." + c, False)
                     and c in columnas]
    faltantes = [c for c in COLUMNAS_PERSONA
                 if cfg.get("metricas.roles_tribunal." + c, False)
                 and c not in columnas]
    for c in faltantes:
        log.warning("El rol '%s' esta activo en el YAML pero la columna no "
                    "esta en el CSV: se omite (regla D.6).", c)
    if not roles_activos:
        log.warning("Ningun rol de tribunal activo o disponible: las "
                    "metricas de personas, la persistencia y la red quedan "
                    "sin calcular (regla F.2).")
    log.info("Roles contados como tribunal: %s",
             ", ".join(roles_activos) or "ninguno")

    # --- corpus completo vs. filas ---
    # El CSV tiene una fila por (tesis, concepto). Las metricas POR CONCEPTO
    # usan las filas de ese concepto; las metricas DEL CORPUS COMPLETO usan
    # las tesis distintas, para no contar dos veces la que dos terminos
    # recuperaron (ver deduplicar_por_tesis).
    filas_unicas = deduplicar_por_tesis(filas, log)

    # --- conceptos ---
    conceptos = sorted({(f.get("keyword_origen") or "").strip()
                        for f in filas
                        if (f.get("keyword_origen") or "").strip()})
    log.info("Conceptos presentes en el corpus: %d", len(conceptos))

    # --- series por concepto y para el corpus completo ---
    series_por_concepto = {}
    for c in conceptos:
        # El cruce va contra el VALOR ORIGINAL de keyword_origen. Normalizar
        # aqui dejaria sin metricas a los terminos de mas de una palabra, en
        # silencio, que es lo que paso en BIBLM (regla G.7).
        del_concepto = [f for f in filas
                        if (f.get("keyword_origen") or "").strip() == c]
        series, _ = calcular_series(del_concepto, etiquetas, etiqueta_de,
                                    roles_activos, cfg, log)
        series_por_concepto[c] = series
    series_global, _ = calcular_series(filas_unicas, etiquetas, etiqueta_de,
                                       roles_activos, cfg, log)

    if cfg.get("output.exportar_series_csv", True):
        for c, s in series_por_concepto.items():
            escribir_serie_csv(ruta_serie(rutas, c), s)
        escribir_serie_csv(ruta_serie(rutas, "_CORPUS_COMPLETO"), series_global)
        log.info("Series exportadas: %d archivos.", len(series_por_concepto) + 1)

    # --- rankings ---
    top_n_personas = int(cfg.get("metricas.top_personas", 5))
    top_n_inst = int(cfg.get("metricas.top_instituciones", 3))
    top_n_disc = int(cfg.get("metricas.top_disciplinas", 10))

    top_personas_global = ranking_personas(filas_unicas, roles_activos,
                                           top_n_personas)
    top_personas_concepto = {
        c: ranking_personas([f for f in filas
                             if (f.get("keyword_origen") or "").strip() == c],
                            roles_activos, top_n_personas)
        for c in conceptos}

    if "etabSoutenanceN" in columnas:
        top_inst_global = ranking_instituciones(filas_unicas, top_n_inst)
        top_inst_concepto = {
            c: ranking_instituciones([f for f in filas
                                      if (f.get("keyword_origen") or "").strip() == c],
                                     top_n_inst)
            for c in conceptos}
    else:
        top_inst_global, top_inst_concepto = None, None

    if "discipline" in columnas:
        top_disc_concepto = {
            c: ranking_disciplinas([f for f in filas
                                    if (f.get("keyword_origen") or "").strip() == c],
                                   top_n_disc)
            for c in conceptos}
    else:
        top_disc_concepto = None

    # --- solapamiento y descripcion del corpus ---
    matriz, multiples = (None, 0)
    if cfg.get("metricas.solapamiento_conceptos", True) and len(conceptos) > 1:
        matriz, multiples = matriz_solapamiento(filas, conceptos)  # sobre filas: cruza conceptos
        escribir_solapamiento_csv(rutas["solapamiento_csv"], matriz, conceptos)
        log.info("Tesis recuperadas por mas de un concepto: %d", multiples)
    elif len(conceptos) <= 1:
        log.info("Solo hay %d concepto: no hay solapamiento que calcular.",
                 len(conceptos))

    descripcion = []
    if cfg.get("metricas.rendimiento_conceptos", True):
        descripcion = describir_corpus(filas, conceptos, log)
        escribir_corpus_csv(rutas["corpus_csv"], descripcion)

    # --- red total ---
    red, etiquetas_com, grafo, tesis_aportadas = None, {}, None, 0
    if cfg.get("metricas.red_total", True) and roles_activos:
        grafo, tesis_aportadas = construir_grafo(filas_unicas, roles_activos, log)
        if grafo is not None:
            red = analizar_red(
                grafo, cfg.get("metricas.red_total_umbral_modularidad", 0.85),
                log)
            if red is not None:
                etiquetas_com = etiquetas_de_comunidad(
                    grafo, red["comunidades"], red["grados"],
                    int(cfg.get("metricas.red_total_minimo_etiqueta", 3)))
                if cfg.get("metricas.red_total_gexf", True):
                    escribir_gexf(grafo, red, rutas["red_gexf"], log)

    if cfg.get("metricas.componente_mayor", False):
        log.warning("metricas.componente_mayor esta en true. La red POR "
                    "PERIODO no esta implementada en v0.1: solo la red total "
                    "(metricas.red_total). Se omite (regla A.1).")

    # --- completitud ---
    comp_columnas = (completitud_por_columna(filas_unicas, columnas)
                     if cfg.get("completitud.por_columna", True) else None)
    cob_ppn = (cobertura_ppn(filas_unicas, roles_activos)
               if cfg.get("completitud.cobertura_ppn", True) and roles_activos
               else None)
    consist = (consistencia(filas_unicas, columnas, log)
               if cfg.get("completitud.consistencia", True) else None)
    sesgo = (sesgo_primero_enero(filas_unicas)
             if cfg.get("temporal.reportar_sesgo_1_enero", True) else None)
    indice = (comparar_con_indice(filas_unicas, cfg, log)
              if cfg.get("completitud.comparar_con_indice", False) else None)

    # --- figuras ---
    if cfg.get("visualizacion.generar_graficos", True):
        plt = preparar_matplotlib(log)
        if plt is not None:
            colores = colores_por_concepto(
                conceptos, cfg.get("visualizacion.paleta", []), log)
            if cfg.get("visualizacion.figura_por_concepto", True):
                for c in conceptos:
                    figura_concepto(c, series_por_concepto[c], colores[c],
                                    ruta_figura_concepto(rutas, c), cfg, plt, log)
            if cfg.get("visualizacion.figura_comparativa", True) and len(conceptos) > 1:
                figura_comparativa(series_por_concepto, colores,
                                   rutas["fig_comparativa"], cfg, plt, log)
            if matriz is not None:
                figura_solapamiento(matriz, conceptos,
                                    rutas["fig_solapamiento"], cfg, plt, log)
            if red is not None:
                figura_red(grafo, red, etiquetas_com, rutas["fig_red"],
                           cfg, plt, log)

    # --- informe ---
    if cfg.get("output.exportar_informe", True):
        escribir_informe(rutas["informe"], {
            "corrida": corrida,
            "ruta_config": args.config,
            "ruta_csv": ruta_csv,
            "iteracion": iteracion,
            "modo": modo,
            "n_filas_csv": len(filas_csv),
            "n_filas": len(filas),
            "descartadas_modo": descartadas_modo,
            "recorte_activo": recorte_activo,
            "anho_inicio": anho_inicio,
            "anho_fin": anho_fin,
            "descartadas_periodo": desc_periodo,
            "descartadas_sin_fecha": desc_sin_fecha,
            "granularidad": granularidad,
            "tramo": tramo,
            "roles_activos": roles_activos,
            "descripcion": descripcion,
            "matriz": matriz,
            "multiples": multiples,
            "ruta_solapamiento": rutas["solapamiento_csv"],
            "top_personas_global": top_personas_global,
            "top_personas_concepto": top_personas_concepto,
            "top_instituciones_global": top_inst_global,
            "top_instituciones_concepto": top_inst_concepto,
            "top_disciplinas_concepto": top_disc_concepto,
            "red": red,
            "red_tesis_aportadas": tesis_aportadas,
            "n_tesis_unicas": len(filas_unicas),
            "etiquetas_comunidad": etiquetas_com,
            "completitud_columnas": comp_columnas,
            "cobertura_ppn": cob_ppn,
            "consistencia": consist,
            "sesgo_enero": sesgo,
            "indice": indice,
        })
        log.info("Informe: %s", rutas["informe"])

    # --- trazabilidad ---
    if cfg.get("log.archivar_config", True):
        archivar_config(args.config, rutas["config"], overrides, log)

    if cfg.defaults_usados:
        log.warning("Se usaron valores por defecto para %d claves ausentes "
                    "del YAML: %s", len(cfg.defaults_usados),
                    ", ".join(sorted(set(cfg.defaults_usados))))

    log.info("Corrida terminada. Salidas en %s", rutas["dir"])


if __name__ == "__main__":
    main()