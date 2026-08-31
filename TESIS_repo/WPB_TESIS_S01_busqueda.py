#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
WPB_TESIS_S01_busqueda.py  --  v0.6

Etapa 1 del pipeline WPB_TESIS. Corre UN diccionario de terminos contra la
API de busqueda de theses.fr y emite una lista de candidatos para revision
manual. NO recupera el corpus completo: eso es S02, y solo sobre lo validado.

FLUJO DEL PIPELINE
    S01 (este script)  ->  curacion manual  ->  S02
    S01 escribe un CSV con las columnas validado, motivo y notas vacias.
    La persona las rellena. S02 lee solo las filas con validado afirmativo.

CONFIGURACION
    WPB_TESIS_S01_busqueda.yaml, mismo nombre base (regla D.5).
    Toda clave del YAML se lee aqui o esta marcada como NO IMPLEMENTADA
    en el bloque no_implementado (regla A.2).

LIMITES VERIFICADOS DE LA API
    Ver WPB_TESIS_limites_campos.md. Resumen de lo que condiciona este
    script, verificado el 2026-08-29:

    - titres.* y resumes.* pliegan acentos y lematizan.
    - sujetsLibelle pliega acentos pero NO lematiza: las flexiones de genero
      y numero deben ir como sinonimos explicitos en el diccionario.
    - titrePrincipal no lematiza ni pliega acentos, y recupera ~1/9 de lo que
      recupera titres.*. Apagado por defecto.
    - Las comillas imponen orden de frase en los cinco campos medidos: el
      subcampo .exact esta operativo y tipo_busqueda=exact es una distincion
      real.
    - Los espacios fuera de comillas se convierten en AND. Un termino
      multipalabra sin comillas se ejecuta como la conjuncion de sus palabras.
    - dateInsertionDansES no verificado: el modo incremental queda fuera de
      alcance. S01 corre siempre completo y marca las filas nuevas comparando
      contra el CSV anterior.

LICENCIA DE LOS DATOS RECUPERADOS
    Licence Ouverte / Open Licence 2.0 (Etalab).
    Atribucion exigida: "Agence bibliographique de l'enseignement superieur".

DATOS PERSONALES
    La salida contiene nombres de autoras, directoras y miembros de tribunal.
    Ver la nota al final del YAML antes de depositar o publicar.

DEPENDENCIAS EXTERNAS
    requests, pyyaml

EJECUCION
    macOS/Linux:  python3 WPB_TESIS_S01_busqueda.py --config WPB_TESIS_S01_busqueda.yaml
    Windows:      py WPB_TESIS_S01_busqueda.py --config WPB_TESIS_S01_busqueda.yaml
    Ver el bloque LINEAS DE EJECUCION POR PLATAFORMA del YAML.

REGISTRO DE CAMBIOS
    v0.6  2026-08-29  El sondeo informa su coste y su progreso.
                      v0.5 no imprimia nada entre el aviso de inicio y el
                      informe final: con 6 filas, 52 terminos y 4 campos son
                      266 consultas y unos 6 minutos de silencio, en los que
                      una corrida normal es indistinguible de un cuelgue.
                      Ahora estima consultas y minutos antes de empezar, y
                      emite una linea por fila y otra por termino con el
                      contador [hechas/totales].
                      Tambien corrige un NameError introducido en v0.5 al
                      retirar el criterio de fraccion: se elimino la linea que
                      definia n, que seguia usandose al construir el resultado.
                      El archivo parseaba, de modo que ast.parse lo daba por
                      bueno y el fallo solo aparecia al ejecutar (regla G.6).

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): ninguno.

    v0.5  2026-08-29  Se retira tambien el criterio de fraccion de la fila,
                      por la misma razon que el relativo de v0.4: medir un
                      termino contra sus vecinos supone que los sinonimos
                      deberian aportar cantidades parecidas, y eso contradice
                      el proposito del diccionario. Los sinonimos estan para
                      capturar variaciones.
                      Quedan dos avisos: volumen bruto y cero resultados.
                      Clave sondeo.umbral_fraccion eliminada del YAML.

                      LO QUE SE PIERDE, para tenerlo presente al fijar el
                      umbral: en la prueba con los totales del 2026-08-29, el
                      termino 'convivialite' (420 resultados, 85% de su fila)
                      solo saltaba por fraccion. Con umbral_volumen en 1000
                      ya no se senala, pese a ser un caso real: la fila
                      'conviviality' devolvio 494 candidatos. Se compensa
                      bajando umbral_volumen en relacion con el tamanho de
                      corpus buscado.

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): ninguno.

    v0.4  2026-08-29  Se retira el criterio de dominancia relativa del sondeo.
                      Senalaba los terminos que aportaban mas de 4 veces su
                      parte uniforme dentro de la fila (4/n_terminos). Sobre
                      los datos reales del 2026-08-29 no senalaba ninguno que
                      los otros dos criterios no senalaran ya, y para leer el
                      aviso habia que entender de donde salia el umbral.
                      Quedan tres reglas de una linea cada una: fraccion de la
                      fila, volumen bruto, y cero resultados.
                      Clave sondeo.umbral_factor eliminada del YAML.

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): ninguno.
                      El sondeo no toca la recuperacion ni las columnas.

    v0.3  2026-08-29  Fase de sondeo previa a la descarga.

                      La corrida de v0.2 recupero 4441 candidatos para un
                      corpus que se esperaba de menos de cien, y el hecho solo
                      se supo tras 74 minutos de descarga de resumenes. El
                      contador totalHits llega en la primera peticion de cada
                      consulta, de modo que el tamanho de la cosecha se podia
                      conocer en segundos.

                      sondear_terminos() mide el aporte de cada termino sin
                      descargar registros, y senala los que dominan su fila
                      segun tres criterios (relativo al numero de terminos,
                      fraccion de la fila, volumen bruto) mas los que aportan
                      cero. Con sondeo.por_campo desglosa por campo, que es lo
                      que permite ver si el volumen viene de resumes.

                      Flag --sondeo: solo mide e informa, no descarga.
                      Si hay avisos o se supera sondeo.maximo_candidatos, se
                      pide confirmacion antes de descargar; sin terminal y sin
                      --force, aborta.

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): ninguno.
                      No cambia como se construyen las consultas ni que
                      columnas se emiten. Es una fase anhadida antes de la
                      descarga.

    v0.2  2026-08-29  Correccion del nombre de los campos con comodin.
                      CAMPOS_PALABRAS_CLAVE declaraba titres.* y resumes.*,
                      formas que la API rechaza con HTTP 400. La forma valida
                      lleva el asterisco escapado: titres.\* y resumes.\*.
                      La barra invertida que aparece en la documentacion de
                      Abes es sintaxis literal, no escapado de Markdown.

                      EFECTO SOBRE DATOS YA EXPORTADOS (regla D.6): ninguno.
                      Con v0.1 las seis consultas devolvian 400 y el script
                      abortaba por corpus vacio sin escribir salida. No hay
                      CSV ni JSON previos que revisar. Es un dato ausente, no
                      un dato incorrecto.

                      Verificado 2026-08-29, ronda 5 del diagnostico:
                          titres.*   HTTP 400
                          titres.\*  HTTP 200, 51 resultados
                          titres     HTTP 200, 0 resultados (campo inexistente)
                      El comodin recupera mas que el subcampo de idioma
                      (51 frente a 44 en titres, 180 frente a 165 en resumes):
                      la diferencia son registros en otras lenguas.

                      Ademas: peticion() y buscar() devuelven ahora el codigo
                      HTTP del fallo por separado, y un 400 en la primera
                      consulta aborta la corrida. Antes se lanzaban las seis
                      pese a compartir la sintaxis invalida, y el aviso
                      quedaba sepultado bajo la URL codificada de cada una.

    v0.1  2026-08-29  Version inicial.

FUENTES
    Abes (2026). Le moteur de recherche theses.fr. Documentation.
        https://documentation.abes.fr/aidethesesfr/index.html
    abes-esr/theses-api-recherche, rama develop. Consultado 2026-08-28.
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
from datetime import datetime
from urllib.parse import urlencode, quote

import requests
import yaml

VERSION = "0.6"

# =========================================================================
# CONSTANTES DE MAPEO
# =========================================================================
# Los nombres de campo de la API se escriben UNA SOLA VEZ, aqui, nunca
# inline (regla B.1). En BIBLM, escribirlos inline produjo una columna
# invalida en todas las exportaciones previas.

# Campos interrogables para diccionarios de palabras clave.
# Clave = nombre en el YAML. Valor = nombre real en el indice.
#
# ATENCION al comodin escapado de titres y resumes. VERIFICADO 2026-08-29
# (ronda 5 del diagnostico):
#     titres.*   -> HTTP 400
#     titres.\*  -> HTTP 200, 51 resultados
#     titres     -> HTTP 200, 0 resultados  <- el campo base NO existe
# El asterisco figura en la lista de caracteres significativos de
# Elasticsearch que la documentacion de Abes manda escapar, y eso alcanza al
# NOMBRE DEL CAMPO, no solo al valor. La barra invertida que aparece en la
# documentacion (resumes.\*:(XXX)) es sintaxis literal, no escapado de
# Markdown.
#
# El campo base merece una nota aparte: devuelve HTTP 200 con total 0. Es el
# caso que la regla B.3 advierte, porque no falla: si se hubiera escrito esa
# forma, S01 correria entero y devolveria un corpus vacio sin un solo error.
CAMPOS_PALABRAS_CLAVE = {
    "titres": r"titres.\*",
    "resumes": r"resumes.\*",
    "sujetsLibelle": "sujetsLibelle",
    "sujetsRameauLibelle": "sujetsRameauLibelle",
    "discipline": "discipline",
    "titrePrincipal": "titrePrincipal",
}

# Roles de persona. Cada uno tiene una variante PN ademas de la NP.
# La convencion PARECE ser nom-prenom frente a prenom-nom, pero Abes no las
# documenta: es inferencia sobre el nombre del campo, no verificacion
# (regla B.2).
CAMPOS_PERSONAS = {
    "auteursNP": "auteursNP",
    "directeursNP": "directeursNP",
    "presidentJuryNP": "presidentJuryNP",
    "rapporteursNP": "rapporteursNP",
    "membresJuryNP": "membresJuryNP",
}
# Sufijo de la variante de orden inverso del nombre.
VARIANTE_PN = {k: k.replace("NP", "PN") for k in CAMPOS_PERSONAS}

CAMPOS_INSTITUCIONES = {
    "etabSoutenanceN": "etabSoutenanceN",
    "etabsCotutelleN": "etabsCotutelleN",
    "ecolesDoctoralesN": "ecolesDoctoralesN",
    "partenairesRechercheN": "partenairesRechercheN",
}

# Campos de filtro global.
CAMPO_STATUS = "status"
CAMPO_ACCESIBLE = "accessible"
CAMPO_FECHA = "dateSoutenance"
CAMPO_LANGUES = "langues"
CAMPO_OAISET = "oaiSetNames"
CAMPO_CODEETAB = "codeEtab"

# Caracteres que Elasticsearch trata como significativos. Si aparecen en un
# termino del diccionario sin escapar, la consulta no se interpreta.
# Fuente: documentacion de Abes, seccion "Caracteres a echapper".
CARACTERES_ESPECIALES = r'+-&|!(){}[]^"~*?:\\'

# Columnas obligatorias del diccionario, en los tres tipos.
COLUMNAS_DICCIONARIO = ["keyword", "tipo_busqueda", "nucleo", "seleccionado"]

# Separadores del campo anidado de personas (regla B.5: una relacion 1:N no
# se aplana a listas paralelas).
#   |  separa personas
#   ~  une nom, prenom y ppn de una misma persona
SEP_PERSONA = "|"
SEP_CAMPO_PERSONA = "~"


# =========================================================================
# CONFIGURACION Y LOG
# =========================================================================

def cargar_config(ruta):
    """Lee el YAML. Ante error de formato aborta con archivo, linea, columna
    y fragmento senhalado (regla F.4). NUNCA cae a valores por defecto: eso
    produciria una corrida completa y plausible con parametros que el usuario
    no eligio."""
    if not os.path.isfile(ruta):
        print(f"ERROR: no existe el archivo de configuracion: {ruta}",
              file=sys.stderr)
        sys.exit(1)
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"ERROR: el archivo de configuracion tiene formato invalido.",
              file=sys.stderr)
        print(f"  Archivo: {ruta}", file=sys.stderr)
        mark = getattr(e, "problem_mark", None)
        if mark is not None:
            print(f"  Linea {mark.line + 1}, columna {mark.column + 1}",
                  file=sys.stderr)
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    lineas = f.readlines()
                print(f"  > {lineas[mark.line].rstrip()}", file=sys.stderr)
                print("  > " + " " * mark.column + "^", file=sys.stderr)
            except (IOError, IndexError):
                pass
        if getattr(e, "problem", None):
            print(f"  Problema: {e.problem}", file=sys.stderr)
        sys.exit(1)


def configurar_log(ruta, nivel):
    """Log a archivo y consola.

    encoding='utf-8' explicito (regla E.1): logging.FileHandler no lo declara
    por defecto y en Windows aborta con UnicodeEncodeError ante caracteres no
    representables en cp1252, que el corpus frances y portugues contiene.

    Modo append con separador de timestamp al inicio (regla D.2): sin el, dos
    corridas quedan indistinguibles en el mismo archivo.
    """
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    fh = logging.FileHandler(ruta, mode="a", encoding="utf-8")
    sh = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    log = logging.getLogger("wpb_tesis")
    log.setLevel(getattr(logging, str(nivel).upper(), logging.INFO))
    log.handlers = []
    log.addHandler(fh)
    log.addHandler(sh)
    log.propagate = False
    log.info("=" * 70)
    log.info("WPB_TESIS_S01_busqueda v%s -- inicio de corrida", VERSION)
    return log


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


# =========================================================================
# LECTURA DEL DICCIONARIO
# =========================================================================

def detectar_separador(ruta):
    """Detecta el separador del CSV a partir de la primera linea (regla E.5).

    Un archivo preparado a mano en Excel o Numbers puede salir con
    tabulaciones o punto y coma en lugar de comas. Asumir la coma produce una
    unica columna con todo el contenido dentro, y el error se manifiesta mas
    tarde como columnas obligatorias ausentes.
    """
    with open(ruta, "r", encoding="utf-8-sig") as f:
        cabecera = f.readline()
    candidatos = {",": cabecera.count(","),
                  ";": cabecera.count(";"),
                  "\t": cabecera.count("\t")}
    sep = max(candidatos, key=candidatos.get)
    return sep if candidatos[sep] > 0 else ","


def leer_diccionario(ruta, log):
    """Lee el diccionario de terminos.

    Abre en utf-8-sig para absorber el BOM (regla E.5): un CSV guardado por
    Excel lo lleva al inicio y contamina el nombre de la primera columna, de
    modo que 'keyword' pasa a llamarse '\\ufeffkeyword' y no se encuentra.

    Comprueba las columnas obligatorias ANTES de usarlas, y ante ausencia
    lista las encontradas frente a las esperadas.

    Devuelve (filas, filas_totales, filas_omitidas).
    """
    if not os.path.isfile(ruta):
        log.error("No existe el diccionario: %s", ruta)
        sys.exit(1)

    sep = detectar_separador(ruta)
    log.info("Diccionario: %s (separador detectado: %r)", ruta, sep)

    with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=sep)
        columnas = lector.fieldnames or []
        faltan = [c for c in COLUMNAS_DICCIONARIO if c not in columnas]
        if faltan:
            log.error("Al diccionario le faltan columnas obligatorias.")
            log.error("  Esperadas:   %s", ", ".join(COLUMNAS_DICCIONARIO))
            log.error("  Encontradas: %s", ", ".join(columnas))
            log.error("  Faltan:      %s", ", ".join(faltan))
            sys.exit(1)
        filas = list(lector)

    total = len(filas)
    activas = []
    for fila in filas:
        if str(fila.get("seleccionado", "")).strip() == "1":
            activas.append(fila)
    omitidas = total - len(activas)

    # Regla D.4: todo filtro que descarte registros reporta cuantos descarto.
    log.info("Diccionario: %d filas totales, %d activas, %d omitidas "
             "(seleccionado != 1)", total, len(activas), omitidas)
    if not activas:
        log.error("Ninguna fila del diccionario tiene seleccionado=1. "
                  "No hay nada que buscar. Se aborta.")
        sys.exit(1)
    return activas, total, omitidas


def terminos_de_fila(fila):
    """Extrae el termino principal y sus sinonimos no vacios."""
    terminos = [str(fila.get("keyword", "")).strip()]
    for col, val in fila.items():
        if col and col.startswith("sinonimo_"):
            v = str(val or "").strip()
            if v:
                terminos.append(v)
    return [t for t in terminos if t]


# =========================================================================
# CONSTRUCCION DE LA CONSULTA
# =========================================================================

class ContadorEscapes:
    """Cuenta cuantas veces se escaparon caracteres especiales.

    Escapar altera el termino tal como lo escribio la persona. Es aceptable
    si queda constancia en el log de la corrida; silencioso, no: quien lea
    los resultados no puede distinguir un termino alterado de uno que venia
    asi (mismo criterio que la regla B.6).
    """

    def __init__(self):
        self.intervenciones = 0
        self.terminos = []


def escapar(termino, contador):
    """Escapa los caracteres significativos de Elasticsearch.

    Fuente: documentacion de Abes. Sin escapar, un termino que los contenga
    hace que la consulta no se interprete.
    """
    salida = []
    tocado = False
    for ch in termino:
        if ch in CARACTERES_ESPECIALES:
            salida.append("\\" + ch)
            tocado = True
        else:
            salida.append(ch)
    if tocado:
        contador.intervenciones += 1
        contador.terminos.append(termino)
    return "".join(salida)


def preparar_termino(termino, tipo_busqueda, contador):
    """Escapa y, si procede, entrecomilla.

    tipo_busqueda:
      exact    -> se envuelve en comillas. Verificado 2026-08-29: las comillas
                  enrutan al subcampo .exact e imponen orden de palabras.
      default  -> sin comillas. ATENCION: cada espacio fuera de comillas se
                  convierte en AND, de modo que un termino multipalabra se
                  ejecuta como la conjuncion de sus palabras, no como frase.
    """
    esc = escapar(termino, contador)
    if str(tipo_busqueda).strip().lower() == "exact":
        return f'"{esc}"'
    return esc


def campos_activos(cfg, tipo_diccionario, log):
    """Devuelve la lista de campos del indice sobre los que buscar, segun el
    tipo de diccionario y las claves encendidas en el YAML."""
    if tipo_diccionario == "keywords":
        activos = []
        for clave, campo in CAMPOS_PALABRAS_CLAVE.items():
            if cfg.get(f"campos_busqueda.palabras_clave.{clave}", False):
                activos.append(campo)
        return activos

    if tipo_diccionario == "personas":
        # Precedencia documentada (regla A.5): todos_los_roles gana sobre las
        # claves individuales, y el override efectivo se registra en el log.
        todos = cfg.get("campos_busqueda.personas.todos_los_roles", False)
        activos = []
        if todos:
            log.info("campos_busqueda.personas.todos_los_roles = true: se "
                     "encienden los cinco roles y se IGNORAN las claves "
                     "individuales de este bloque.")
            activos = list(CAMPOS_PERSONAS.values())
        else:
            for clave, campo in CAMPOS_PERSONAS.items():
                if cfg.get(f"campos_busqueda.personas.{clave}", False):
                    activos.append(campo)
        if cfg.get("campos_busqueda.personas.incluir_variantes_PN", False):
            # Variantes de orden del nombre. NO VERIFICADAS: existen en el
            # indice pero Abes no las documenta (regla B.2).
            extra = [VARIANTE_PN[k] for k, v in CAMPOS_PERSONAS.items()
                     if v in activos]
            log.info("incluir_variantes_PN = true: se anhaden %d campos de "
                     "orden inverso del nombre (NO VERIFICADOS).", len(extra))
            activos += extra
        return activos

    if tipo_diccionario == "instituciones":
        activos = []
        for clave, campo in CAMPOS_INSTITUCIONES.items():
            if cfg.get(f"campos_busqueda.instituciones.{clave}", False):
                activos.append(campo)
        return activos

    log.error("diccionario.tipo debe ser keywords, personas o instituciones. "
              "Valor recibido: %r", tipo_diccionario)
    sys.exit(1)


def construir_clausula_terminos(terminos, campos):
    """Une terminos y campos: campo1:(t1 OR t2) OR campo2:(t1 OR t2) ..."""
    bloque = " OR ".join(terminos)
    return " OR ".join(f"{c}:({bloque})" for c in campos)


def sondear_terminos(filas_dicc, campos, filtros, cfg, log):
    """Sondeo previo: mide cuanto aporta cada termino ANTES de descargar nada.

    POR QUE EXISTE
      La corrida del 2026-08-29 recupero 4441 candidatos para un corpus que
      se esperaba de menos de cien, y el hecho solo se supo despues de 74
      minutos de descarga de resumenes. totalHits llega en la primera
      peticion de cada consulta: el tamanho de la cosecha se puede conocer en
      segundos, y decidir con ese dato en la mano.

    QUE MIDE
      Una consulta por termino, con nombre=1 para traer solo el contador.
      Si sondeo.por_campo es true, ademas una por termino y campo, que es lo
      que permite ver si el volumen viene de un campo concreto -- tipicamente
      resumes, donde una mencion de pasada pesa igual que el tema de la tesis.

    QUE SENALA
      Tres avisos, cada uno con una regla de una linea:

      fraccion  el termino aporta mas de la mitad de su fila.
      volumen   el termino devuelve mas de N resultados por si solo.
      cero      el termino no devuelve nada: no esta en el indice y sobra.

      Hubo un cuarto criterio, relativo al numero de terminos de la fila
      (aporta mas de 4 veces 1/n). Se retiro en v0.4: sobre los datos reales
      no senalaba nada que los otros dos no senalaran ya, y exigia entender
      de donde salia el umbral para leer el aviso.

    LIMITE DE LO QUE MIDE
      Los totales por termino NO son aditivos: dos terminos pueden recuperar
      la misma tesis. La suma de la columna excedera el total de la fila
      siempre que haya solapamiento. Sirve para comparar terminos entre si,
      no para descomponer el total.

    Devuelve (lista de resultados, lista de avisos).
    """
    pausa = float(cfg.get("api.pausa_segundos", 1.0))
    por_campo = cfg.get("sondeo.por_campo", True)
    bruto = int(cfg.get("sondeo.umbral_volumen", 1000))
    contador = ContadorEscapes()

    # Estimacion del coste ANTES de empezar. El sondeo no imprime nada por
    # consulta si no se avisa, y son varios minutos de silencio: sin este
    # calculo previo, una corrida normal es indistinguible de un cuelgue.
    n_terminos = sum(len(terminos_de_fila(f)) for f in filas_dicc)
    n_consultas = len(filas_dicc) + n_terminos * (1 + (len(campos) if por_campo else 0))
    log.info("-" * 60)
    log.info("SONDEO PREVIO: se miden los totales sin descargar registros.")
    log.info("  %d filas, %d terminos, %d campos%s",
             len(filas_dicc), n_terminos, len(campos),
             " (con desglose por campo)" if por_campo else "")
    log.info("  %d consultas, ~%.0f minutos a %.1fs de pausa.",
             n_consultas, n_consultas * (pausa + 0.4) / 60, pausa)
    if por_campo:
        log.info("  sondeo.por_campo = false reduciria a %d consultas, pero "
                 "no diria de que campo viene el volumen.",
                 len(filas_dicc) + n_terminos)

    resultados = []
    avisos = []
    hechas = 0

    for fila in filas_dicc:
        crudos = terminos_de_fila(fila)
        tipo_b = fila.get("tipo_busqueda", "default")
        kw = fila.get("keyword", "")
        if not crudos:
            continue

        # Total de la fila completa, con todos sus terminos unidos por OR.
        prep = [preparar_termino(t, tipo_b, contador) for t in crudos]
        q_fila = " AND ".join(
            [f"({construir_clausula_terminos(prep, campos)})"] + filtros)
        _, total_fila, err = buscar_solo_total(q_fila, cfg, log)
        hechas += 1
        if err == 400:
            log.error("El sondeo fallo con 400 en la fila %r. Se aborta.", kw)
            sys.exit(1)
        log.info("  [%d/%d] fila %r: %s resultados, %d terminos por medir",
                 hechas, n_consultas, kw,
                 f"{total_fila:,}" if total_fila is not None else "?",
                 len(crudos))
        time.sleep(pausa)

        # Aporte de cada termino por separado.
        por_termino = []
        for t in crudos:
            pt = preparar_termino(t, tipo_b, contador)
            q = " AND ".join(
                [f"({construir_clausula_terminos([pt], campos)})"] + filtros)
            _, tot, _ = buscar_solo_total(q, cfg, log)
            hechas += 1
            time.sleep(pausa)

            desglose = {}
            if por_campo:
                for c in campos:
                    q_c = " AND ".join(
                        [f"({construir_clausula_terminos([pt], [c])})"] + filtros)
                    _, tc, _ = buscar_solo_total(q_c, cfg, log)
                    hechas += 1
                    desglose[c] = tc
                    time.sleep(pausa)
            # Una linea por termino: es el grano al que el usuario puede
            # reaccionar, y evita varios minutos sin salida.
            log.info("  [%d/%d]   %-28s %s", hechas, n_consultas, t[:28],
                     f"{tot:,}" if tot is not None else "?")
            por_termino.append((t, tot or 0, desglose))

        for t, tot, desglose in por_termino:
            # El porcentaje se sigue mostrando como contexto, pero NO se usa
            # como criterio de aviso. Ver el docstring.
            share = (tot / total_fila) if total_fila else 0.0
            motivos = []
            if tot > bruto:
                motivos.append("devuelve %s resultados por si solo (umbral %s)"
                               % (f"{tot:,}", f"{bruto:,}"))
            if tot == 0:
                motivos.append("no aparece en el indice: el sinonimo sobra")
            if motivos:
                avisos.append((kw, t, tot, share, motivos, desglose))
        resultados.append((kw, total_fila or 0, len(crudos), por_termino))

    return resultados, avisos


def buscar_solo_total(q, cfg, log):
    """Lanza la consulta con nombre=1 y devuelve (None, totalHits, error).

    Pedir un solo registro basta para leer el contador. Traer mas cargaria el
    servicio sin aportar nada al sondeo.
    """
    base = cfg.get("api.base_url", obligatorio=True)
    url = base + "?" + urlencode({"q": q, "debut": 0, "nombre": 1},
                                 quote_via=quote)
    datos, error = peticion(url, cfg, log)
    if datos is None:
        return None, None, error
    return None, datos.get("totalHits", 0), None


def informar_sondeo(resultados, avisos, cfg, log):
    """Imprime el informe del sondeo y devuelve las lineas, para el reporte."""
    lineas = []
    def emitir(t=""):
        print(t)
        lineas.append(t)

    total_bruto = sum(r[1] for r in resultados)
    emitir("")
    emitir("=" * 74)
    emitir("SONDEO PREVIO -- totales por fila del diccionario")
    emitir("=" * 74)
    emitir("%-28s %10s %8s" % ("keyword", "totalHits", "terminos"))
    emitir("-" * 74)
    for kw, total, n, _ in resultados:
        emitir("%-28s %10s %8d" % (kw[:28], f"{total:,}", n))
    emitir("-" * 74)
    emitir("%-28s %10s" % ("suma (con solapamiento)", f"{total_bruto:,}"))
    emitir("")
    emitir("Los totales por fila NO son aditivos: dos filas pueden recuperar")
    emitir("la misma tesis. El total unico se conoce al recuperar.")

    if avisos:
        emitir("")
        emitir("=" * 74)
        emitir("TERMINOS QUE CONVIENE REVISAR (%d)" % len(avisos))
        emitir("=" * 74)
        for kw, t, tot, share, motivos, desglose in avisos:
            emitir("")
            emitir("  [%s] termino: %r" % (kw, t))
            emitir("      %s resultados, %.0f%% de su fila"
                   % (f"{tot:,}", share * 100))
            for m in motivos:
                emitir("      - " + m)
            if desglose:
                partes = ["%s=%s" % (c, v if v is not None else "?")
                          for c, v in desglose.items()]
                emitir("      por campo: " + "  ".join(partes))
        emitir("")
        emitir("-" * 74)
        emitir("QUE HACER CON ESTO")
        emitir("-" * 74)
        emitir("""
Un termino que domina su fila suele ser mas general que el concepto que se
quiere recuperar. Casos tipicos en este corpus:

  - El nombre de un proceso historico usado como sinonimo de una corriente
    teorica. En una base de tesis francesas, 'decolonisation' recupera toda
    la historiografia del imperio, no la teoria decolonial.

  - Una palabra corriente de la lengua usada como termino tecnico.
    'convivialite' es vocabulario comun del frances.

Si el desglose por campo muestra que el volumen viene de resumes, conviene
apagar ese campo para la busqueda: una mencion de pasada en el resumen pesa
igual que el tema de la tesis. Se puede seguir recuperando el resumen para
la validacion sin interrogarlo.

Opciones, de menos a mas invasiva:
  1. Quitar el termino del diccionario.
  2. Moverlo a una fila propia, con su nucleo, para poder validarlo aparte.
  3. Apagar resumes en campos_busqueda.palabras_clave.
  4. Acotar el periodo o la disciplina en filtros.
""")
    else:
        emitir("")
        emitir("Ningun termino supera los umbrales de sondeo.")
    return lineas


def construir_filtros(cfg, log):
    """Construye las clausulas de filtro global.

    ALCANCE (regla A.4): estos filtros recortan ANTES de recuperar, de modo
    que redefinen el corpus de candidatos completo, no solo la vista
    exportada. Dos corridas con filtros distintos no son comparables.

    Se escriben dentro de q con sintaxis campo:(valor). NO se usa el
    parametro filtres de la API (ver no_implementado en el YAML).
    """
    clausulas = []
    aplicados = []

    status = cfg.get("filtros.status", "soutenue")
    clausulas.append(f"{CAMPO_STATUS}:({status})")
    aplicados.append(f"status={status}")
    if status != "soutenue":
        log.warning(
            "filtros.status = %r. Las tesis en curso NO tienen NNT (usan "
            "numSujet), y las APIs de difusion y exportacion solo aceptan "
            "NNT: parte del corpus no admitira esas llamadas en S02.", status)

    if cfg.get("filtros.solo_accesibles", False):
        clausulas.append(f"{CAMPO_ACCESIBLE}:oui")
        aplicados.append("solo_accesibles=true")

    ini = cfg.get("filtros.periodo_inicio", None)
    fin = cfg.get("filtros.periodo_fin", None)
    if ini or fin:
        desde = ini if ini else "*"
        hasta = fin if fin else "*"
        clausulas.append(f"{CAMPO_FECHA}:([{desde} TO {hasta}])")
        aplicados.append(f"periodo={desde}..{hasta}")
        log.warning(
            "Filtro de periodo activo (%s a %s). SESGO CONOCIDO: las tesis "
            "impresas de las que solo se conoce el anho se registran como "
            "AAAA-01-01. Un recorte que empiece un 2 de enero pierde ese "
            "material entero.", desde, hasta)

    for clave, campo in (("filtros.langues", CAMPO_LANGUES),
                         ("filtros.oaiSetNames", CAMPO_OAISET),
                         ("filtros.codeEtab", CAMPO_CODEETAB)):
        valores = cfg.get(clave, []) or []
        if valores:
            bloque = " OR ".join(str(v) for v in valores)
            clausulas.append(f"{campo}:({bloque})")
            aplicados.append(f"{campo}={valores}")

    log.info("Filtros globales aplicados: %s",
             "; ".join(aplicados) if aplicados else "ninguno")
    return clausulas


# =========================================================================
# LLAMADAS A LA API
# =========================================================================

def cabeceras(cfg):
    """User-Agent identificado con proyecto y contacto. La API no lo exige,
    pero es la practica que corresponde con un servicio publico gratuito:
    permite que la Abes contacte si el volumen resulta problematico."""
    contacto = cfg.get("api.contacto", "sin-contacto-declarado")
    proyecto = cfg.get("metadata.proyecto", "WPB_TESIS")
    return {
        "User-Agent": f"WPB_TESIS/{VERSION} ({proyecto}; {contacto})",
        "Accept": "application/json",
    }


def peticion(url, cfg, log):
    """GET con reintentos y espera creciente.

    Devuelve (json, codigo_de_error). El codigo es None si todo fue bien.
    Ante fallo devuelve (None, codigo) y NUNCA una estructura vacia que
    pudiera confundirse con un resultado legitimo (regla F.2).

    Un 503 aborta en lugar de reintentar: puede indicar mantenimiento del
    servicio, y en ese caso insistir solo agrava la carga.
    """
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
            log.error("HTTP 503: el servicio puede estar en mantenimiento. "
                      "Se aborta en lugar de insistir.")
            sys.exit(1)
        if r.status_code == 200:
            try:
                return r.json(), None
            except json.JSONDecodeError as e:
                log.error("Respuesta no es JSON valido: %s", e)
                return None, 200
        if 500 <= r.status_code < 600:
            log.warning("HTTP %d (intento %d/%d)",
                        r.status_code, intento, reintentos)
            if intento < reintentos:
                time.sleep(backoff ** intento)
            continue

        # 4xx: no se reintenta, el problema esta en la consulta.
        log.error("HTTP %d. URL: %s", r.status_code, url)
        if r.status_code == 400:
            log.error("Un 400 significa que la consulta NO SE INTERPRETO. "
                      "No es un cero: no hay resultado alguno que leer.")
            log.error("Causas frecuentes, por orden: (a) nombre de campo con "
                      "sintaxis invalida -- el comodin va escapado, "
                      "titres.\\* y no titres.*; (b) caracter significativo "
                      "sin escapar en un termino del diccionario; (c) "
                      "consulta demasiado larga. Ver las secciones 3 y 5.3 "
                      "de WPB_TESIS_limites_campos.md.")
        return None, r.status_code

    log.error("Agotados los reintentos. URL: %s", url)
    return None, None


def buscar(q, cfg, log):
    """Recupera todos los registros de una consulta, paginando.

    Devuelve (lista de registros, totalHits, codigo_de_error).
    codigo_de_error es None si todo fue bien, o el codigo HTTP del fallo.
    Se devuelve por separado porque un 400 y un 0 son resultados distintos:
    el primero significa que la consulta no se interpreto, el segundo que no
    hay tesis que la cumplan. Confundirlos hizo que un nombre de campo
    invalido llegara al script sin detectarse.
    """
    base = cfg.get("api.base_url", obligatorio=True)
    por_pagina = int(cfg.get("api.registros_por_pagina", 100))
    pausa = float(cfg.get("api.pausa_segundos", 1.0))

    registros = []
    debut = 0
    total = None

    while True:
        url = base + "?" + urlencode(
            {"q": q, "debut": debut, "nombre": por_pagina}, quote_via=quote)
        datos, error = peticion(url, cfg, log)
        if datos is None:
            log.error("Consulta fallida, se omite: %s", q)
            return registros, total, error
        if total is None:
            total = datos.get("totalHits", 0)
            log.info("  totalHits = %s", total)
        lote = datos.get("theses", []) or []
        registros.extend(lote)
        debut += por_pagina
        if debut >= (total or 0) or not lote:
            break
        time.sleep(pausa)

    return registros, total, None


def recuperar_resumen(id_tesis, cfg, log):
    """Pide el registro completo para leer el resumen.

    El registro que devuelve la busqueda NO trae resumes. Recuperarlo exige
    una llamada por candidato. Devuelve el diccionario de resumenes por
    idioma, o {} si no se pudo.
    """
    base = cfg.get("api.url_detalle", obligatorio=True)
    datos, _ = peticion(base + quote(str(id_tesis)), cfg, log)
    if datos is None:
        return {}
    return datos.get("resumes", {}) or {}


# =========================================================================
# NORMALIZACION DE REGISTROS
# =========================================================================

def sanear(valor, separadores, contador):
    """Sustituye por espacio los caracteres que se usan como separadores.

    Un nombre propio de persona o institucion que contenga alguno de ellos
    romperia el parseo aguas abajo. Sanear altera el dato de origen; es
    aceptable si queda constancia en el log, silencioso no (regla B.6).
    """
    s = str(valor or "")
    tocado = False
    for sep in separadores:
        if sep and sep in s:
            s = s.replace(sep, " ")
            tocado = True
    if tocado:
        contador.intervenciones += 1
    return s.strip()


def aplanar_personas(lista, separadores, contador):
    """Aplana una lista de personas conservando la anidacion (regla B.5).

    Formato:  Nom~Prenom~PPN|Nom2~Prenom2~PPN2
              |  separa personas
              ~  une nom, prenom y ppn de una misma persona

    Dos listas paralelas separadas por | equivaldrian a la estructura
    original solo si se garantizara el mismo orden y la misma longitud. Al
    conservar la anidacion en un solo campo, la correspondencia no se pierde
    y el CSV sigue siendo reconstruible.

    Se emite SIN deduplicar, tal como viene de la API. Si una persona
    repetida debe contar una o dos veces es una decision analitica y
    corresponde al script que consume, no al que extrae.
    """
    if not lista:
        return ""
    if isinstance(lista, dict):     # presidentJury viene como objeto unico
        lista = [lista]
    piezas = []
    for p in lista:
        if not isinstance(p, dict):
            continue
        nom = sanear(p.get("nom"), separadores, contador)
        pre = sanear(p.get("prenom"), separadores, contador)
        ppn = sanear(p.get("ppn"), separadores, contador)
        piezas.append(SEP_CAMPO_PERSONA.join([nom, pre, ppn]))
    return SEP_PERSONA.join(piezas)


def aplanar_organismos(lista, separadores, contador):
    """Igual que aplanar_personas, para OrganismeResponseDto:
    Nom~PPN~Tipo|Nom2~PPN2~Tipo2"""
    if not lista:
        return ""
    if isinstance(lista, dict):
        lista = [lista]
    piezas = []
    for o in lista:
        if not isinstance(o, dict):
            continue
        nom = sanear(o.get("nom"), separadores, contador)
        ppn = sanear(o.get("ppn"), separadores, contador)
        tip = sanear(o.get("type"), separadores, contador)
        piezas.append(SEP_CAMPO_PERSONA.join([nom, ppn, tip]))
    return SEP_PERSONA.join(piezas)


def aplanar_sujetos(lista, separadores, contador):
    """Sujet tiene langue y libelle; SujetsRameau tiene ppn y libelle.
    Se emite  Libelle~Clave  y se conserva la anidacion."""
    if not lista:
        return ""
    piezas = []
    for s in lista:
        if not isinstance(s, dict):
            continue
        lib = sanear(s.get("libelle"), separadores, contador)
        clave = sanear(s.get("langue") or s.get("ppn"), separadores, contador)
        piezas.append(SEP_CAMPO_PERSONA.join([lib, clave]))
    return SEP_PERSONA.join(piezas)


def elegir_resumen(resumes, idiomas_preferidos):
    """Elige el resumen para la columna del CSV segun el orden de preferencia.

    Devuelve (texto, idioma_usado). En el JSON van todos los idiomas.
    """
    if not resumes:
        return "", ""
    for idioma in idiomas_preferidos:
        if idioma in resumes and resumes[idioma]:
            return str(resumes[idioma]), idioma
    # Ninguno de los preferidos: se toma el primero disponible y se declara
    # cual, para que no quede la duda de en que lengua esta el texto.
    for idioma, texto in resumes.items():
        if texto:
            return str(texto), idioma
    return "", ""


def normalizar(registro, contexto, cfg, contador):
    """Convierte un registro de la API en una fila plana para el CSV.

    contexto trae la procedencia: que fila del diccionario lo recupero.
    """
    sep_csv = cfg.get("output.separador_csv", ",")
    seps = [sep_csv, SEP_PERSONA, SEP_CAMPO_PERSONA, "\n", "\r"]

    fila = {
        # --- procedencia (no viene de la API) ---
        "diccionario": contexto["diccionario"],
        "keyword_origen": contexto["keyword"],
        "nucleo": contexto["nucleo"],
        "tipo_busqueda": contexto["tipo_busqueda"],
        "corrida_origen": contexto["corrida"],

        # --- identificadores ---
        # numSujet NO viaja en el registro reducido: solo hay id. No se ha
        # verificado si id contiene el NNT para las defendidas y el numSujet
        # para las demas. S02 resuelve el identificador definitivo.
        "id": registro.get("id", ""),
        "nnt": registro.get("nnt", "") or "",
        "doi": registro.get("doi", "") or "",

        # --- descripcion ---
        "titrePrincipal": sanear(registro.get("titrePrincipal"), seps, contador),
        "titreEN": sanear(registro.get("titreEN"), seps, contador),
        "discipline": sanear(registro.get("discipline"), seps, contador),
        "status": registro.get("status", "") or "",
        "dateSoutenance": registro.get("dateSoutenance", "") or "",
        "datePremiereInscriptionDoctorat":
            registro.get("datePremiereInscriptionDoctorat", "") or "",

        # --- personas, con la anidacion conservada (regla B.5) ---
        "auteurs": aplanar_personas(registro.get("auteurs"), seps, contador),
        "directeurs": aplanar_personas(registro.get("directeurs"), seps, contador),
        "president": aplanar_personas(registro.get("president"), seps, contador),
        "rapporteurs": aplanar_personas(registro.get("rapporteurs"), seps, contador),
        "examinateurs": aplanar_personas(registro.get("examinateurs"), seps, contador),

        # --- instituciones ---
        "etabSoutenanceN": sanear(registro.get("etabSoutenanceN"), seps, contador),
        "etabSoutenancePpn": registro.get("etabSoutenancePpn", "") or "",
        "ecolesDoctorale": aplanar_organismos(
            registro.get("ecolesDoctorale"), seps, contador),
        "partenairesDeRecherche": aplanar_organismos(
            registro.get("partenairesDeRecherche"), seps, contador),

        # --- materias ---
        "sujets": aplanar_sujetos(registro.get("sujets"), seps, contador),
        "sujetsRameau": aplanar_sujetos(registro.get("sujetsRameau"), seps, contador),

        # --- resumen (se rellena despues si recuperacion.resumenes) ---
        "resumen": "",
        "resumen_idioma": "",

        # --- curacion, vacias para que las rellene la persona ---
        "validado": "",
        "motivo": "",
        "notas": "",
    }
    return fila


# =========================================================================
# SALIDA
# =========================================================================

def nombres_salida(cfg):
    """Construye las rutas de salida a partir del patron.

    El identificador de corrida aparece en el nombre para que dos corridas
    con distinta iteracion o distinto diccionario no se pisen (regla C.5).
    """
    directorio = cfg.get("output.directorio", "salidas/")
    patron = cfg.get("output.patron_nombre", "WPB_TESIS_{iter}_{dicc}_S01")
    base = patron.format(iter=cfg.get("metadata.iteracion", "000"),
                         dicc=cfg.get("diccionario.tipo", "keywords"))
    return {
        "dir": directorio,
        "base": base,
        "csv": os.path.join(directorio, base + ".csv"),
        "json": os.path.join(directorio, base + ".json"),
        "config": os.path.join(directorio, base + "_config_usado.yaml"),
        "stats": os.path.join(directorio, base + "_estadisticas.txt"),
    }


def confirmar_sobrescritura(rutas, cfg, force, log):
    """Detecta archivos existentes que coincidan con el patron, los lista y
    pide confirmacion antes de escribir (regla C.1).

    --force salta la confirmacion y GANA sobre el YAML. El override efectivo
    se registra en el log y se anota en la copia archivada de la
    configuracion (regla A.5).

    Sin terminal interactiva y sin --force, ABORTA en lugar de esperar
    (regla C.2): un input() sin salvaguarda cuelga indefinidamente en
    notebook, cron o pipeline encadenado.
    """
    existentes = [p for p in (rutas["csv"], rutas["json"], rutas["stats"])
                  if os.path.exists(p)]
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
        print(f"  {p}")
    print("\nNota: si curacion.preservar_anotaciones = true, las anotaciones "
          "del CSV anterior se conservan.")

    if not sys.stdin.isatty():
        log.error("No hay terminal interactiva y no se declaro --force. "
                  "Se aborta en lugar de esperar una confirmacion que nadie "
                  "puede dar.")
        sys.exit(1)

    resp = input("Sobrescribir? [s/N]: ").strip().lower()
    if resp not in ("s", "si", "sí", "y", "yes"):
        log.info("Cancelado por el usuario. No se escribio nada.")
        sys.exit(0)


def leer_csv_previo(ruta, cfg, log):
    """Lee las anotaciones del CSV anterior, indexadas por id.

    Lo que se conserva aqui es trabajo manual irrecuperable, no datos que se
    puedan volver a descargar. Por eso la salida es aditiva por defecto.
    """
    if not os.path.exists(ruta):
        return {}
    sep = detectar_separador(ruta)
    previas = {}
    try:
        with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
            for fila in csv.DictReader(f, delimiter=sep):
                clave = fila.get("id") or fila.get("nnt")
                if clave:
                    previas[clave] = {
                        "validado": fila.get("validado", ""),
                        "motivo": fila.get("motivo", ""),
                        "notas": fila.get("notas", ""),
                        "corrida_origen": fila.get("corrida_origen", ""),
                    }
    except (IOError, csv.Error) as e:
        log.error("No se pudo leer el CSV anterior (%s): %s", ruta, e)
        log.error("Se aborta para no perder las anotaciones existentes.")
        sys.exit(1)
    log.info("CSV anterior: %d filas con anotaciones recuperadas.", len(previas))
    return previas


def normalizar_validado(valor, aceptados, log, contador_no_reconocidos):
    """Normaliza la columna validado.

    Un valor no vacio que no este en la lista de aceptados se registra como
    NO RECONOCIDO y la fila NO se da por validada. Tratarlo como 0 en
    silencio convertiria un error de escritura en una exclusion invisible.
    """
    v = str(valor or "").strip().lower()
    if not v:
        return ""
    if v in [str(a).strip().lower() for a in aceptados]:
        return v
    if v in ("0", "no", "n", "false"):
        return v
    contador_no_reconocidos.append(valor)
    log.warning("Valor no reconocido en la columna validado: %r. La fila NO "
                "se da por validada.", valor)
    return v


def escribir_csv(ruta, filas, cfg, log):
    """Escribe el CSV con el modulo csv y comillas.

    Las columnas de curacion son texto libre editado a mano y pueden contener
    el separador, comillas y saltos de linea: partir por comas romperia el
    archivo.
    """
    if not filas:
        log.error("No hay filas que escribir.")
        return
    sep = cfg.get("output.separador_csv", ",")
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()),
                           delimiter=sep, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(filas)
    log.info("CSV escrito: %s (%d filas)", ruta, len(filas))


def escribir_json(ruta, registros, log):
    """Escribe el JSON con la estructura anidada intacta.

    El JSON es la fuente: conserva las relaciones 1:N sin aplanar, de modo
    que no hay perdida irreversible (regla B.5).
    """
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)
    log.info("JSON escrito: %s (%d registros)", ruta, len(registros))


def archivar_config(ruta_origen, ruta_destino, overrides, log):
    """Deja una copia del YAML tal como fue leido, junto a los outputs
    (regla D.1). El original se sigue editando; la copia congela el estado
    que produjo estos datos.

    Los overrides de linea de comandos se anotan por separado al final: la
    copia debe reflejar el estado que produjo los datos, y con flags de
    override ambas cosas solo son compatibles si el override queda registrado
    (regla A.5).
    """
    os.makedirs(os.path.dirname(ruta_destino) or ".", exist_ok=True)
    shutil.copy2(ruta_origen, ruta_destino)
    if overrides:
        with open(ruta_destino, "a", encoding="utf-8") as f:
            f.write("\n\n# " + "=" * 70 + "\n")
            f.write("# OVERRIDES DE LINEA DE COMANDOS EN ESTA CORRIDA\n")
            f.write("# Ganaron sobre lo declarado arriba (regla A.5).\n")
            f.write("# " + "=" * 70 + "\n")
            for o in overrides:
                f.write(f"#   {o}\n")
    log.info("Configuracion archivada: %s", ruta_destino)


def escribir_estadisticas(ruta, stats, log):
    """Reporte de la corrida, incluyendo los conteos de exclusion.

    Todo filtro que descarte registros reporta cuantos descarto, en el log y
    aqui (regla D.4). Un corpus final sin conteo de exclusiones no permite
    auditar el recorte. Corresponde a la Rule 1 de Rule et al. (2019):
    documentar el proceso y no solamente los resultados.
    """
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        for linea in stats:
            f.write(linea + "\n")
    log.info("Estadisticas escritas: %s", ruta)


# =========================================================================
# PRINCIPAL
# =========================================================================

def main():
    ap = argparse.ArgumentParser(
        description="WPB_TESIS S01: busca candidatos en theses.fr para "
                    "curacion manual.")
    ap.add_argument("--config", default="WPB_TESIS_S01_busqueda.yaml",
                    help="Ruta al archivo de configuracion YAML.")
    ap.add_argument("--sondeo", action="store_true",
                    help="Solo sondeo: mide los totales por termino, emite el "
                         "informe y termina sin descargar nada.")
    ap.add_argument("--force", action="store_true",
                    help="Sobrescribe sin pedir confirmacion. Se declara en "
                         "cada invocacion, nunca se hereda del entorno "
                         "(regla C.3).")
    args = ap.parse_args()

    datos = cargar_config(args.config)
    log = configurar_log(
        (datos.get("log") or {}).get("ruta", "salidas/WPB_TESIS_S01.log"),
        (datos.get("log") or {}).get("nivel", "INFO"))
    cfg = Config(datos, log)

    corrida = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    log.info("Config: %s", args.config)
    log.info("Identificador de corrida: %s", corrida)

    # Coherencia de versiones (regla D.3).
    v_yaml = cfg.get("metadata.version_config", "?")
    if str(v_yaml) != VERSION:
        log.warning("La version del script (%s) y la del YAML (%s) no "
                    "coinciden.", VERSION, v_yaml)

    # Claves marcadas como NO IMPLEMENTADAS: se leen para avisar si alguien
    # las enciende creyendo que hacen algo (regla A.1).
    for clave, motivo in (
            ("no_implementado.modo_incremental",
             "dateInsertionDansES no verificado; ver seccion 5.4 de "
             "WPB_TESIS_limites_campos.md"),
            ("no_implementado.usar_parametro_filtres",
             "el parametro filtres es un artefacto de la interfaz web"),
            ("no_implementado.tfidf",
             "pendiente de decidir en que etapa se calcula")):
        if cfg.get(clave, False):
            log.warning("%s = true, pero NO ESTA IMPLEMENTADO y no tendra "
                        "efecto alguno. Razon: %s", clave, motivo)

    # ---- diccionario -----------------------------------------------------
    tipo_dicc = cfg.get("diccionario.tipo", obligatorio=True)
    ruta_dicc = cfg.get("diccionario.ruta", obligatorio=True)
    filas_dicc, dicc_total, dicc_omitidas = leer_diccionario(ruta_dicc, log)

    campos = campos_activos(cfg, tipo_dicc, log)
    if not campos:
        log.error("Ningun campo de busqueda activo para diccionario.tipo=%r. "
                  "No hay donde buscar. Se aborta.", tipo_dicc)
        sys.exit(1)
    log.info("Campos de busqueda activos (%d): %s", len(campos),
             ", ".join(campos))

    filtros = construir_filtros(cfg, log)
    contador_escapes = ContadorEscapes()
    contador_saneo = ContadorEscapes()

    # ---- sondeo previo ---------------------------------------------------
    # Mide el tamanho de la cosecha ANTES de descargar. Ver sondear_terminos().
    lineas_sondeo = []
    if args.sondeo or cfg.get("sondeo.activo", True):
        resultados_s, avisos_s = sondear_terminos(
            filas_dicc, campos, filtros, cfg, log)
        lineas_sondeo = informar_sondeo(resultados_s, avisos_s, cfg, log)
        total_estimado = sum(r[1] for r in resultados_s)

        if args.sondeo:
            log.info("Modo --sondeo: no se descarga nada. Fin.")
            sys.exit(0)

        # Aviso de volumen. El limite no es tecnico sino de curacion: cada
        # candidato lo tiene que mirar una persona.
        maximo = int(cfg.get("sondeo.maximo_candidatos", 500))
        if total_estimado > maximo or avisos_s:
            if total_estimado > maximo:
                log.warning("El sondeo estima hasta %s candidatos, por encima "
                            "de sondeo.maximo_candidatos (%d). Recordar que "
                            "cada candidato lo revisa una persona.",
                            f"{total_estimado:,}", maximo)
            if avisos_s:
                log.warning("%d terminos superan los umbrales de sondeo. "
                            "Ver el informe de arriba.", len(avisos_s))
            if args.force:
                log.warning("OVERRIDE: --force declarado, se continua sin "
                            "preguntar pese a los avisos del sondeo.")
            elif not sys.stdin.isatty():
                log.error("Hay avisos del sondeo y no hay terminal para "
                          "confirmar. Se aborta antes de descargar. Revisar "
                          "el diccionario, o declarar --force.")
                sys.exit(1)
            else:
                r = input("\nContinuar con la descarga? [s/N]: ").strip().lower()
                if r not in ("s", "si", "sí", "y", "yes"):
                    log.info("Cancelado tras el sondeo. No se descargo nada. "
                             "Revisar el diccionario y volver a correr.")
                    sys.exit(0)

    # ---- salidas y sobrescritura ----------------------------------------
    rutas = nombres_salida(cfg)
    overrides = []
    if args.force:
        overrides.append("--force (salta la confirmacion de sobrescritura)")
    confirmar_sobrescritura(rutas, cfg, args.force, log)

    preservar = cfg.get("curacion.preservar_anotaciones", True)
    previas = leer_csv_previo(rutas["csv"], cfg, log) if preservar else {}
    if not preservar:
        log.warning("curacion.preservar_anotaciones = false: si existia un "
                    "CSV anterior, SE PIERDEN sus anotaciones.")

    # ---- busqueda --------------------------------------------------------
    una_por_fila = cfg.get("diccionario.una_consulta_por_fila", True)
    if not una_por_fila:
        log.warning("diccionario.una_consulta_por_fila = false: se lanza una "
                    "sola consulta con todas las filas. No se podra saber que "
                    "termino recupero que, y hay riesgo de truncamiento "
                    "silencioso por largo de URL o max_clause_count.")

    pausa = float(cfg.get("api.pausa_segundos", 1.0))
    crudos = {}          # id -> registro de la API, deduplicado
    procedencia = {}     # id -> contexto de la primera fila que lo recupero
    consultas = 0
    fallidas = 0

    for fila in filas_dicc:
        terminos_crudos = terminos_de_fila(fila)
        tipo_b = fila.get("tipo_busqueda", "default")
        terminos = [preparar_termino(t, tipo_b, contador_escapes)
                    for t in terminos_crudos]
        if not terminos:
            log.warning("Fila sin terminos, se omite: %r", fila.get("keyword"))
            continue

        clausula = construir_clausula_terminos(terminos, campos)
        q = " AND ".join([f"({clausula})"] + filtros)

        log.info("Consulta %d: keyword=%r (%d terminos, tipo=%s)",
                 consultas + 1, fila.get("keyword"), len(terminos), tipo_b)
        registros, total, error = buscar(q, cfg, log)
        consultas += 1
        if error is not None:
            fallidas += 1
            # Un 400 en la PRIMERA consulta no es un tropiezo aislado: la
            # sintaxis mal formada es comun a todas las que vienen detras.
            # Seguir lanzandolas carga el servicio sin sentido y sepulta el
            # aviso bajo pantallas de URL codificada, que fue lo que paso en
            # la corrida del 2026-08-29.
            if error == 400 and consultas == 1:
                log.error("La PRIMERA consulta fallo con 400. Como la "
                          "sintaxis es la misma en todas, se aborta en lugar "
                          "de lanzar las %d restantes.",
                          len(filas_dicc) - 1)
                sys.exit(1)

        contexto = {
            "diccionario": tipo_dicc,
            "keyword": fila.get("keyword", ""),
            "nucleo": fila.get("nucleo", ""),
            "tipo_busqueda": tipo_b,
            "corrida": corrida,
        }
        nuevos = 0
        for reg in registros:
            clave = reg.get("id") or reg.get("nnt")
            if not clave:
                continue
            if clave not in crudos:
                crudos[clave] = reg
                procedencia[clave] = contexto
                nuevos += 1
        log.info("  recuperados %d, nuevos tras deduplicar %d",
                 len(registros), nuevos)
        time.sleep(pausa)

    if not crudos:
        # Regla F.3: una condicion de corpus vacio aborta con mensaje
        # explicito, no continua generando exports vacios.
        log.error("Ninguna consulta devolvio resultados. No se genera salida.")
        log.error("Revisar: terminos del diccionario, campos activos y "
                  "filtros globales.")
        sys.exit(1)

    log.info("Candidatos unicos tras deduplicar: %d", len(crudos))

    # ---- resumenes -------------------------------------------------------
    resumenes = {}
    if cfg.get("recuperacion.resumenes", True):
        log.info("recuperacion.resumenes = true: %d llamadas adicionales, "
                 "una por candidato (~%.1f min a %.1fs de pausa).",
                 len(crudos), len(crudos) * pausa / 60, pausa)
        for i, (clave, reg) in enumerate(crudos.items(), 1):
            resumenes[clave] = recuperar_resumen(reg.get("id"), cfg, log)
            if i % 25 == 0:
                log.info("  resumenes recuperados: %d/%d", i, len(crudos))
            time.sleep(pausa)
    else:
        log.warning("recuperacion.resumenes = false: el CSV de curacion NO "
                    "llevara resumen. Quien valide decidira con titulo, "
                    "disciplina y palabras clave.")

    # ---- normalizacion ---------------------------------------------------
    idiomas = cfg.get("recuperacion.idiomas_resumen_curacion",
                      ["es", "fr", "en"])
    max_car = int(cfg.get("recuperacion.resumen_max_caracteres", 1200))
    aceptados = cfg.get("curacion.valores_validado_si", ["1"])
    no_reconocidos = []

    filas_salida = []
    recuperadas = 0
    for clave, reg in crudos.items():
        fila = normalizar(reg, procedencia[clave], cfg, contador_saneo)
        texto, idioma = elegir_resumen(resumenes.get(clave, {}), idiomas)
        if max_car and len(texto) > max_car:
            texto = texto[:max_car] + " [...]"
        fila["resumen"] = texto.replace("\n", " ").replace("\r", " ")
        fila["resumen_idioma"] = idioma

        # Anotaciones previas: se conservan intactas y la fila mantiene la
        # corrida en que aparecio por primera vez.
        if clave in previas:
            p = previas[clave]
            fila["validado"] = normalizar_validado(
                p["validado"], aceptados, log, no_reconocidos)
            fila["motivo"] = p["motivo"]
            fila["notas"] = p["notas"]
            fila["corrida_origen"] = p["corrida_origen"] or corrida
            recuperadas += 1
        filas_salida.append(fila)

    nuevas = len(filas_salida) - recuperadas
    log.info("Filas: %d totales, %d con anotaciones previas conservadas, "
             "%d nuevas en esta corrida.", len(filas_salida), recuperadas,
             nuevas)

    # ---- escritura -------------------------------------------------------
    if cfg.get("output.formato_csv", True):
        escribir_csv(rutas["csv"], filas_salida, cfg, log)
    if cfg.get("output.formato_json", True):
        escribir_json(rutas["json"], list(crudos.values()), log)
    if cfg.get("log.archivar_config", True):
        archivar_config(args.config, rutas["config"], overrides, log)

    # ---- estadisticas ----------------------------------------------------
    stats = [
        "WPB_TESIS_S01_busqueda v" + VERSION,
        "Corrida: " + corrida,
        "Iteracion: " + str(cfg.get("metadata.iteracion", "?")),
        "Diccionario: %s (%s)" % (tipo_dicc, ruta_dicc),
        "",
        "DICCIONARIO",
        "  filas totales:            %d" % dicc_total,
        "  filas activas:            %d" % len(filas_dicc),
        "  filas omitidas:           %d  (seleccionado != 1)" % dicc_omitidas,
        "",
        "CONSULTAS",
        "  lanzadas:                 %d" % consultas,
        "  fallidas:                 %d" % fallidas,
        "  campos de busqueda:       %s" % ", ".join(campos),
        "  filtros globales:         %s" % (" AND ".join(filtros) or "ninguno"),
        "",
        "RESULTADOS",
        "  candidatos unicos:        %d" % len(crudos),
        "  con anotaciones previas:  %d" % recuperadas,
        "  nuevos en esta corrida:   %d" % nuevas,
        "",
        "INTERVENCIONES SOBRE EL DATO",
        "  terminos escapados:       %d" % contador_escapes.intervenciones,
        "  valores saneados:         %d" % contador_saneo.intervenciones,
        "  validado no reconocido:   %d" % len(no_reconocidos),
        "",
        "DEFAULTS APLICADOS POR CLAVE AUSENTE EN EL YAML",
    ]
    if cfg.defaults_usados:
        stats += ["  " + c for c in cfg.defaults_usados]
    else:
        stats.append("  ninguno")
    if contador_escapes.terminos:
        stats += ["", "TERMINOS QUE REQUIRIERON ESCAPE"]
        stats += ["  " + t for t in contador_escapes.terminos]
    if no_reconocidos:
        stats += ["", "VALORES NO RECONOCIDOS EN validado"]
        stats += ["  " + str(v) for v in no_reconocidos]
    stats += [
        "",
        "ATRIBUCION DE LOS DATOS",
        "  Agence bibliographique de l'enseignement superieur (Abes)",
        "  Licence Ouverte / Open Licence 2.0 (Etalab)",
    ]
    if lineas_sondeo:
        stats += ["", "=" * 60, "INFORME DEL SONDEO PREVIO", "=" * 60]
        stats += lineas_sondeo
    escribir_estadisticas(rutas["stats"], stats, log)

    # Regla B.6: sanear altera el dato de origen; queda constancia en el log.
    if contador_escapes.intervenciones:
        log.warning("Se escaparon caracteres especiales en %d terminos del "
                    "diccionario. Detalle en el reporte de estadisticas.",
                    contador_escapes.intervenciones)
    if contador_saneo.intervenciones:
        log.warning("Se sanearon separadores en %d valores del CSV. El JSON "
                    "conserva los valores sin alterar.",
                    contador_saneo.intervenciones)

    log.info("Fin de la corrida. Siguiente paso: revisar %s y rellenar las "
             "columnas validado, motivo y notas.", rutas["csv"])


if __name__ == "__main__":
    main()
