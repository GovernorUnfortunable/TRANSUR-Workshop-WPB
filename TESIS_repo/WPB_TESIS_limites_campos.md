==========================================================================
LIMITES DE LOS CAMPOS INTERROGABLES  --  API de busqueda de theses.fr
==========================================================================

Documento de referencia para WPB_TESIS. Recoge lo que se verifico
empiricamente sobre el comportamiento de cada campo, y que consecuencias
tiene sobre como se escriben los diccionarios y como se lee el corpus.

Fecha de verificacion: 2026-08-29
Metodo: consultas de conteo contra https://theses.fr/api/v1/theses/recherche/
        Scripts WPB_TESIS_S00_diagnostico.py (v0.1) a _diagnostico5.py (v0.5).
        Logs conservados junto a los scripts.

Motivo de la verificacion: el mapeo del indice Elasticsearch NO es publico.
No figura en abes-esr/theses-api-recherche ni en abes-esr/theses-api-indexation
(este ultimo solo define el indice 'referencement', que es otro). El
comportamiento de los campos solo se puede establecer por observacion, y
puede cambiar sin aviso si la Abes reindexa. Por eso se registra la fecha
(regla B.4).

--------------------------------------------------------------------------
1. TABLA DE COMPORTAMIENTO
--------------------------------------------------------------------------

Tres propiedades por campo:
  ACENTOS  el campo trata decolonial y décolonial como el mismo termino
  STEMMING el campo colapsa las flexiones de un mismo lema
           (décolonial / décoloniale / décoloniaux)
  FRASE    las comillas imponen orden de palabras

campo                  ACENTOS   STEMMING   FRASE
---------------------  --------  ---------  --------
titres.*                  si        si        si
resumes.*                 si        si        si
sujetsLibelle             si        NO        si
titrePrincipal            NO        NO        si
sujetsRameauLibelle      s/d       s/d        si
discipline               s/d       s/d       s/d

  si  = verificado
  NO  = verificado, la propiedad no se cumple
  s/d = sin datos; ver seccion 4

--------------------------------------------------------------------------
2. DATOS QUE SUSTENTAN LA TABLA
--------------------------------------------------------------------------

Familia morfologica de prueba, sin comillas. Cuatro formas del mismo lema
frances: base sin tilde, base con tilde, femenino singular, masculino plural.

campo                  decolonial  décolonial  décoloniale  décoloniaux
---------------------  ----------  ----------  -----------  -----------
titres.fr                      44          44           44           44
titrePrincipal                  5           3           25            4
sujetsLibelle                  63          63           29            0
sujetsRameauLibelle             0           0            0            0
resumes.fr                    165         165          165          165
discipline                      0           0            0            0

Orden de frase, con comillas: "buen vivir" frente a "vivir buen".

campo                  directo  invertido
---------------------  -------  ---------
titres.fr                    3          0
titrePrincipal               4          0
sujetsLibelle                7          0
sujetsRameauLibelle          4          0
resumes.fr                  15          0
discipline                   0          0

--------------------------------------------------------------------------
3. LIMITES POR CAMPO Y CONSECUENCIAS
--------------------------------------------------------------------------

3.0  titres.* y resumes.* -- EL ASTERISCO VA ESCAPADO

Es el limite que mas caro sale si se ignora, porque el sintoma es un HTTP 400
que tumba la consulta entera, incluidos los campos que si son validos.

    titres.*    HTTP 400   la consulta no se interpreta
    titres.\*   HTTP 200   51 resultados
    titres      HTTP 200   0 resultados

El asterisco figura en la lista de caracteres significativos de Elasticsearch
que la documentacion de Abes manda escapar, y ese requisito alcanza al NOMBRE
DEL CAMPO, no solo al valor. La barra invertida que aparece en la
documentacion de Abes -- resumes.\*:(XXX) -- es sintaxis literal, no escapado
de Markdown. Lo mismo vale para resumes: 400, 180 y 0 respectivamente.

  El campo base merece atencion aparte. titres:(x) y resumes:(x) devuelven
  HTTP 200 con total 0: no fallan, simplemente no existen. Es el caso que la
  regla B.3 describe. Un script que usara esa forma correria entero y
  devolveria un corpus vacio sin un solo error en el log.

  El comodin recupera mas que el subcampo de idioma -- 51 frente a los 44 de
  titres.fr, 180 frente a los 165 de resumes.fr -- y la diferencia son
  registros cuyo titulo o resumen esta en otra lengua. Es la forma correcta,
  no un adorno.

  Corolario para la lectura de errores: un 400 y un 0 son resultados
  distintos. El primero significa que la consulta no se interpreto; el
  segundo, que no hay tesis que la cumplan. Los scripts de diagnostico
  posteriores a la ronda 4 informan el codigo HTTP por eso.

3.1  titrePrincipal -- NO USAR para busqueda tematica

Devuelve totales distintos para las cuatro formas del mismo lema: no
lematiza ni pliega acentos. Recupera aproximadamente una novena parte de lo
que recupera titres.* para el mismo termino.

La diferencia NO es de cobertura. La sintaxis _exists_ muestra que
titrePrincipal esta poblado en 563.718 de 563.719 registros y titres.fr en
555.485. El campo que menos recupera es el que mas cobertura tiene. La
diferencia esta en como se analiza el contenido, no en que registros lo
tienen.

  Decision: el proyecto usa titres.* para busqueda tematica.
  titrePrincipal queda disponible en el YAML pero apagado por defecto, con
  esta advertencia en su comentario.

  Observacion no verificada: que décoloniale (25) supere a décolonial (3)
  es esperable en frances por concordancia ("pensée décoloniale", "théorie
  décoloniale"), y los 5 de la forma sin tilde son probablemente titulos en
  ingles. Es inferencia sobre el idioma, no medicion. No se apoya ninguna
  decision en ella.

3.2  sujetsLibelle -- pliega acentos pero NO lematiza

Es el limite mas consecuente para los diccionarios, porque es
contraintuitivo: el campo normaliza tildes y mayusculas, de modo que parece
tolerante, pero no colapsa flexiones. décoloniale recupera 29 frente a los
63 de la forma base, y décoloniaux recupera 0.

  Consecuencia: como el proyecto interroga varios campos en la misma
  consulta, el diccionario debe incluir las flexiones de genero y numero
  como sinonimos explicitos. titres.* y resumes.* las colapsarian solas,
  pero sujetsLibelle no, y sin ellas ese campo aporta menos de lo que
  parece.

  Lo que si sobra en el diccionario: las variantes que solo se diferencian
  por tildes o por mayuscula inicial. Los tres campos principales las
  pliegan.

  Cuidado con la simetria falsa: que dos variantes ortograficas sean
  redundantes NO implica que lo sean dos variantes morfologicas. Son
  propiedades independientes y en este campo van en sentidos opuestos.

3.3  titres.* y resumes.* -- comportamiento pleno

Pliegan acentos, lematizan y respetan el orden de frase. Son los campos
sobre los que la busqueda tematica se comporta como cabria esperar.

  Limite propio: resumes.* NO viaja en el registro reducido que devuelve la
  busqueda, ni en el CSV nativo de la API. Se puede interrogar, pero para
  leer el resumen hace falta una llamada adicional a
  /api/v1/theses/these/{id}. Es la razon de que S01 tenga el parametro
  recuperar_resumenes, encendido por defecto.

  Limite de la notacion: titres.* y resumes.* son comodines sobre subcampos
  por idioma. Las mediciones se hicieron sobre titres.fr y resumes.fr. No
  se ha verificado que los subcampos de otros idiomas se analicen igual;
  es plausible que cada uno use el analizador de su lengua, en cuyo caso el
  stemming de resumes.es no tiene por que coincidir con el de resumes.fr.
  Sin verificar.

3.4  Orden de frase -- uniforme en los cinco campos con datos

En titres.fr, titrePrincipal, sujetsLibelle, sujetsRameauLibelle y
resumes.fr, la frase invertida devuelve 0 y la directa no. Las comillas
enrutan al subcampo .exact, tal como hace quoteFieldSuffix(".exact") en el
codigo fuente de la API.

  Consecuencia: tipo_busqueda=exact es una distincion real y se conserva en
  los diccionarios. Aplicada a un termino de una sola palabra no cambia
  nada; su efecto esta en los terminos multipalabra, que son la mayoria del
  diccionario del proyecto.

--------------------------------------------------------------------------
4. CAMPOS SIN DATOS
--------------------------------------------------------------------------

4.1  sujetsRameauLibelle

Las cuatro formas del lema dieron 0, pero la prueba de frase dio 4. El campo
responde: simplemente Rameau es un vocabulario controlado y no contiene ese
descriptor.

  Limite estructural, no de analisis: buscar terminos de autor en un
  vocabulario controlado tiene rendimiento bajo por construccion. Rameau
  recoge la terminologia que la Bibliotheque nationale de France ha
  normalizado, no la que circula en la literatura. Un termino emergente
  puede no tener descriptor.

  Queda disponible y encendido, pero sin medicion de sus propiedades de
  analisis.

4.2  discipline

Dio 0 en las cuatro formas y tambien en la prueba de frase. Ninguna de las
dos sondas era un nombre de disciplina, de modo que la prueba no mide nada:
el campo no esta verificado ni descartado.

  Limite conocido por otra via: segun la especificacion TEF, discipline se
  registra "tal como figura en la portada de la tesis". Es texto libre, no
  vocabulario controlado. Habra variantes ortograficas y de denominacion
  entre instituciones, y no se puede parametrizar por lista cerrada.

--------------------------------------------------------------------------
5. LIMITES QUE NO SON DE CAMPO
--------------------------------------------------------------------------

5.1  Los espacios se convierten en AND

El codigo fuente sustituye cada espacio fuera de comillas por " AND ", y el
operador por defecto tambien es AND. Un termino multipalabra sin comillas se
ejecuta como la conjuncion de sus palabras, no como frase.

  Consecuencia: en un diccionario donde la mayoria de las entradas son
  multipalabra, la eleccion entre exact y default no es un matiz.

5.2  Caracteres que rompen la consulta

Elasticsearch trata como significativos: + - && || ! ( ) { } [ ] ^ " ~ * ? : \
Si aparecen en un termino del diccionario hay que escaparlos con \ (%5C) o
la consulta no se interpreta.

  El script escapa y cuenta cuantas veces intervino (mismo criterio que la
  regla B.6: sanear es aceptable si queda constancia en el log).

  El requisito alcanza tambien a los NOMBRES DE CAMPO, no solo a los valores.
  Ver la seccion 3.0: es la causa del unico fallo de corrida registrado hasta
  ahora.

5.3  Largo de la consulta

Las peticiones son GET con todo codificado en la URL. Con cinco roles de
persona por dos variantes de orden de nombre, o con un diccionario de
sesenta terminos por varios campos, se acumulan centenares de clausulas.
Dos techos, ninguno de los cuales avisa con claridad: el max_clause_count de
Elasticsearch y el largo maximo de la URL. El sintoma puede ser un 400 o,
peor, un resultado truncado.

  Decision: un diccionario por corrida, y una consulta por fila del
  diccionario en lugar de una consulta unica con todas las filas. Mas lento
  y mas peticiones, pero permite saber que termino recupero que, y no se
  acerca a los techos.

5.4  dateInsertionDansES -- no verificado, fuera de alcance

El filtro por rango devolvio el indice completo: 563.719 registros con y sin
restriccion. No se determino si el campo se ignora o si todo el indice se
reconstruyo despues de enero de 2024.

  Consecuencia: S01 NO implementa modo incremental. Corre siempre completo y
  marca las filas nuevas comparando contra los NNT ya conocidos. Queda
  anotado en el YAML como NO IMPLEMENTADO con esta razon.

  Si se implementara sobre este campo sin verificar, cada actualizacion
  recuperaria el corpus entero mientras el log declara que recupero solo lo
  nuevo. Fallo silencioso y plausible.

5.5  El registro de busqueda no es el registro completo

La busqueda devuelve una vista reducida. No trae resumes, langues,
accessible, etabCotutelle, codeEtab, numSujet, titres multilingue ni
mapSujets. Para esos campos hace falta /api/v1/theses/these/{id}, una
llamada por tesis.

5.6  El estado condiciona que se puede pedir despues

Las APIs de difusion (/api/v1/button/{nnt}) y de exportacion aceptan NNT.
Las tesis en curso no tienen NNT: usan numSujet. Y hay un caso intermedio,
tesis ya defendidas pendientes de tratamiento, que conservan numSujet y
todavia no tienen NNT.

  Consecuencia: si se activa status:(enCours) o status:(*), parte del corpus
  no admite las llamadas de acceso ni de exportacion. S02 debe registrarlo
  como exclusion contada, no omitirlo en silencio (regla D.4).

--------------------------------------------------------------------------
6. VIGENCIA DE ESTE DOCUMENTO
--------------------------------------------------------------------------

Todo lo anterior describe el estado del indice el 2026-08-29. El mapeo no es
publico y la Abes puede reindexar sin versionado ni aviso. Si los resultados
del corpus se apartan de lo aqui descrito, el primer paso es volver a correr
los tres scripts de diagnostico y comparar contra las tablas de la seccion 2,
no depurar el script de busqueda.

--------------------------------------------------------------------------
FUENTES
--------------------------------------------------------------------------

Abes (2022). Guide de reutilisation des donnees de theses.fr.
Abes (2026). Le moteur de recherche theses.fr. Documentation.
    https://documentation.abes.fr/aidethesesfr/index.html
abes-esr/theses-api-recherche, rama develop. Consultado 2026-08-28.
abes-esr/theses-api-diffusion, rama develop. Consultado 2026-08-28.
abes-esr/theses-api-indexation, rama develop. Consultado 2026-08-29.
Diagnosticos WPB_TESIS_S00_diagnostico.py a _diagnostico5.py, 2026-08-29.
Especificacion TEF, recomendacion de la Abes.

Datos bajo Licence Ouverte / Open Licence 2.0 (Etalab).
Atribucion exigida: Agence bibliographique de l'enseignement superieur.
