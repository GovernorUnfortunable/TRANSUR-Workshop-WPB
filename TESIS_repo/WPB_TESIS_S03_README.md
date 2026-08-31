# WPB_TESIS_S03 — Análisis del corpus de tesis

Etapa de análisis del pipeline WPB_TESIS (v0.3). Lee el CSV de candidatos que produce S01 y emite una primera aproximación al corpus: series temporales, rankings, solapamiento entre términos, red de co-participación en tribunales e informe de completitud.

Es una **aproximación exploratoria, no un resultado**. Sirve para identificar candidatas a entrevista cualitativa, detectar instituciones y temas que concentran actividad, y ver la forma del corpus antes de invertir trabajo en validarlo.

## Posición en el pipeline

```
S01 --> S03              análisis preliminar sobre candidatos sin curar
S01 --> S02 --> S03      análisis sobre el corpus validado y enriquecido
```

S02 todavía no existe. S03 detecta qué recibió mirando las columnas del CSV y omite los análisis para los que falten datos, dejando constancia en el log. No emite números plausibles a partir de columnas ausentes (regla D.6).

La curación manual entre S01 y S03 es **opcional**: `entrada.modo` permite correr sobre los candidatos sin validar.

## Archivos

| Archivo | Descripción |
|---|---|
| `WPB_TESIS_S03_analisis.py` | Script principal (v0.1) |
| `WPB_TESIS_S03_analisis.yaml` | Configuración. Mismo nombre base que el script (regla D.5) |

## Requisitos

```bash
pip install pandas matplotlib pyyaml requests networkx
```

`networkx` solo hace falta para la red de co-participación. Si no está instalado, esa parte se omite con un WARNING que explicita qué se pierde; el resto del análisis no se ve afectado.

## Ejecución

**macOS / Linux**
```bash
cd /ruta/al/proyecto
python3 WPB_TESIS_S03_analisis.py --config WPB_TESIS_S03_analisis.yaml
```

**Windows (PowerShell o CMD)**
```powershell
cd C:/ruta/al/proyecto
py -X utf8 WPB_TESIS_S03_analisis.py --config WPB_TESIS_S03_analisis.yaml
```

`-X utf8` en Windows no es opcional: el corpus contiene caracteres franceses que cp1252 no representa.

| Flag | Efecto |
|---|---|
| `--csv RUTA` | Apunta a otro CSV de entrada. **Gana** sobre `entrada.ruta`; el override se anota en el log y en la copia archivada de la configuración (regla A.5) |
| `--force` | Sobrescribe sin pedir confirmación. Se declara en cada invocación y no se hereda del entorno (regla C.3) |

Sin terminal interactiva y sin `--force`, el script **aborta** en lugar de esperar una confirmación que nadie puede dar (regla C.2).

Las rutas relativas se resuelven contra el **directorio de trabajo**, no contra la ubicación del `.py` (regla E.4). El `cd` inicial no es opcional.

## Fuente de los datos

El corpus proviene de la **API de búsqueda de theses.fr**, consultada por S01. Conviene no confundir tres artefactos distintos que circulan en la literatura sobre theses.fr:

| Artefacto | Qué es | Nombres de campo |
|---|---|---|
| **API theses.fr** | Lo que consulta S01 | `dateSoutenance`, `examinateurs`, `sujetsRameau` |
| **data dump Etalab** | Volcado JSON de theses.fr en data.gouv.fr (2024-01-08) | campos originales de la plataforma |
| **dataset Aboucaya & Jasim (2026)** | Derivado del data dump, enriquecido con IdRef | `defense_date`, `jury_member.{i}.idref`, `rameau_topics` |

Los tres tienen nombres de campo distintos y **no son intercambiables**. S03 lee únicamente columnas de la primera.

Licencia de los datos: Licence Ouverte / Open Licence 2.0 (Etalab). Atribución exigida en cualquier reutilización: *Agence bibliographique de l'enseignement supérieur*.

## Qué es el PPN

**Pica Production Number**: identificador de registro del sistema Pica de la Abes. Identifica *registros*, y hay registros de tipos distintos, de modo que «PPN» a secas es ambiguo. En este pipeline conviene escribir siempre de qué PPN se habla:

| Dónde aparece | Qué identifica |
|---|---|
| Dentro de `directeurs`, `president`, `rapporteurs`, `examinateurs`, `auteurs` | **PPN de persona** — ficha de autoridad en IdRef, resoluble en `idref.fr/{ppn}` |
| `etabSoutenancePpn`, y el segundo campo de `ecolesDoctorale` y `partenairesDeRecherche` | **PPN de institución** — también en IdRef |
| `ppn` en el dataset Aboucaya & Jasim | **PPN de SUDOC** — identifica el *manuscrito* catalogado. No viaja en el endpoint de búsqueda, de modo que este corpus no lo tiene |

Las métricas de persistencia y los rankings de personas usan el **PPN de persona**, nunca el nombre. El PPN es robusto en el sentido de que lo asigna la catalogación profesional y no se deriva del nombre: dos apariciones con el mismo PPN son la misma persona aunque el nombre esté escrito distinto o invertido. Es robusto **cuando está presente y cuando resuelve**; ver los límites (a) y (c) más abajo.

## Límites conocidos de la fuente

Documentados en Aboucaya & Jasim (2026), citado al final.

**(a) La composición del tribunal falta sistemáticamente en el material antiguo.** theses.fr no la registraba de forma sistemática al inicio de la plataforma. La ausencia **no es aleatoria** y sesga toda métrica de persistencia hacia los años recientes. Lo mide `completitud.cobertura_ppn`, que el informe desglosa por año precisamente para que el sesgo sea visible.

**(b) Nombre y apellido aparecen invertidos en parte de los registros.** Aboucaya & Jasim lo corrigen en su dataset tomando los nombres de IdRef; este pipeline lee theses.fr directo y hereda el problema sin la corrección. Por eso el cotejo de personas se hace siempre por PPN y nunca por nombre.

**(c) Existen identificadores IdRef mal formados o que no resuelven.** Los autores corrigieron 168 a mano sobre unos 560.000 registros. Un PPN roto no rompe el conteo —se comporta como una persona más— pero no es resoluble en idref.fr si después se quiere consultar la ficha. Esa cifra es de *su* dataset, no de este corpus: se registra como orden de magnitud conocido, no como dato propio. Detectarlo en el corpus propio queda pendiente.

**(d') Las fechas vienen en `DD/MM/AAAA`, no en ISO.** Verificado el 2026-08-31 sobre un corpus real de 1294 filas: `23/10/2018`, `14/11/2025`, `30/11/2021`. El script acepta también el formato ISO por si el data dump o una versión futura de la API lo emiten, y diagnostica al leer el corpus cuántas fechas parsean, cuántas están vacías y cuántas tienen un formato no reconocido, con ejemplos de estas últimas. La ambigüedad `DD/MM` frente a `MM/DD` no afecta al año, que es el último componente en ambas lecturas.

**(d) Las tesis impresas de las que solo se conoce el año se registran como `AAAA-01-01`.** Produce una acumulación artificial de defensas cada 1 de enero, concentrada en el material antiguo. Lo mide `temporal.reportar_sesgo_1_enero`. No se corrige nada: solo se mide cuánto pesa el artefacto.

## Contrato de entrada

Columnas **obligatorias**. Sin ellas el script aborta:

```
keyword_origen, dateSoutenance
```

Columnas **opcionales**. Su ausencia desactiva un análisis concreto, con aviso en el log:

| Columna | Qué se pierde si falta |
|---|---|
| `etabSoutenanceN` | ranking de instituciones de defensa |
| `discipline` | ranking de disciplinas |
| `nnt`, `status` | comprobación de consistencia status/NNT |
| `datePremiereInscriptionDoctorat` | comprobación de orden de fechas |

| `validado` | modos `validados` y `ambos` |

Los campos 1:N conservan la anidación en un solo campo, tal como los escribe S01 (regla B.5):

```
personas       Nom~Prenom~PPN|Nom2~Prenom2~PPN2
instituciones  Nom~PPN~Tipo|...
materias       Libelle~Clave|...

|  separa elementos          ~  une los datos de un mismo elemento
```

### Una fila por (tesis, concepto)

El CSV de S01 tiene **una fila por cada par (tesis, término del diccionario)**. Una tesis recuperada por dos términos aparece dos veces. Eso es correcto para las métricas **por concepto** —pertenece a los dos subcorpus, y por eso la suma de los subcorpus supera el tamaño del corpus— pero no para las métricas del **corpus completo**, donde contarla dos veces inflaría el conteo de tesis, los rankings, el peso de las aristas del grafo y la cobertura de PPN.

S03 deduplica por tesis (`nnt`, o `id` cuando falta) antes de calcular cualquier métrica global, y el informe declara ambos números: filas analizadas y tesis distintas.

**Los términos que recuperaron la tesis no se pierden al deduplicar.** La fila que sobrevive recibe todos:

```
keyword_origen      buen vivir|decolonial
conceptos_origen    buen vivir~A~exact|decolonial~B~default
                    |  separa conceptos
                    ~  une concepto, núcleo y tipo_busqueda
```

Conservar un solo `keyword_origen` —el de la primera aparición, elegido por el orden del archivo— dejaría un dato verdadero a medias: quien lo leyera obtendría un término real, sin señal alguna de que había otros.

`nucleo` y `tipo_busqueda` son valores **por concepto**, uno cada uno. Emitirlos como listas paralelas a la de `keyword_origen` equivaldría a la estructura original solo garantizando el mismo orden y la misma longitud, que es lo que la regla B.5 prohíbe. La correspondencia se conserva anidada en `conceptos_origen`, en un solo campo. Las columnas `nucleo` y `tipo_busqueda` se dejan intactas para no romper a quien las lea, pero **con más de un concepto no son fiables por sí solas**: la fuente es `conceptos_origen`.

## Salidas

En `output.directorio`, con el patrón `WPB_TESIS_{iter}_S03`. La iteración **no se declara en este YAML**: se deriva del nombre del CSV de entrada (regla C.6). Para analizar otra iteración se apunta `--csv` al archivo correspondiente; no hay ningún número que actualizar a mano.

| Archivo | Contenido |
|---|---|
| `_informe.txt` | Informe completo: universo, rankings, red, completitud, consistencia |
| `_serie_<concepto>.csv` | Serie por período de cada término, más `_serie_corpus_completo.csv` |
| `_descripcion_corpus.csv` | Por término: tesis, tesis únicas, años de cobertura |
| `_solapamiento.csv` | Tabla de doble entrada: tesis compartidas entre términos |
| `_concepto_<x>.png` | Barras de tesis por período + acumulado + persistencia del tribunal |
| `_comparativa.png` | Todos los términos superpuestos |
| `_solapamiento.png` | Heatmap de la tabla de solapamiento |
| `_red.png` | Red de co-participación, nodos coloreados por comunidad |
| `_red.gexf` | La misma red en formato GEXF |
| `_config_usado.yaml` | Copia del YAML tal como fue leído, más los overrides (reglas D.1 y A.5) |

S03 **no elimina archivos huérfanos** de corridas previas (regla C.4). Si cambia el diccionario de términos entre corridas con la misma iteración, las series de la corrida anterior sobreviven junto a las nuevas.

### Visualización interactiva en Retina

El `.gexf` se abre directamente en **[Retina](https://retina.cortext.net/)** —herramienta libre de OuestWare y Tommaso Venturini (CNRS CIS)— sin conversión previa: es el formato que Retina consume para reconstruir la visualización. Los atributos `comunidad` y `grado` viajan en el archivo, de modo que Retina puede colorear y dimensionar los nodos sin recalcular nada. Sirve para explorar la red con zoom y nombres al pasar el cursor, que es lo que una figura estática no da.

## Métricas: qué miden exactamente

### `persistencia_tribunal`

Para cada período: qué proporción de los miembros de tribunal de ese período **ya había aparecido en un período anterior** del mismo término.

Es la inversa de `newcomers_pct` de `WPB_BIBLM_S02`, que calcula el porcentaje de autores que aparecen por primera vez:

```
persistencia = 100 − newcomers
```

Se emite la persistencia porque es lo que responde la pregunta de quién sostiene una línea temática en el tiempo.

El **primer período con datos no tiene período anterior**, de modo que su persistencia no está definida: se emite vacío, nunca 0. Un 0 se leería como «nadie repetía», que es una afirmación sobre el mundo, y ahí no hay afirmación posible. Lo mismo en los períodos sin ninguna persona identificada.

El identificador es el PPN de persona. Quien no lo trae queda fuera de esta métrica; su techo lo mide `cobertura_ppn`.

### Rankings de personas

La unidad es la **tesis**, no la aparición. Una persona que figura como ponente y como examinadora de la misma tesis cuenta **una vez**: se deduplica por PPN dentro de cada tesis antes de contar, porque los roles pueden solaparse y no se ha verificado si Abes lo registra en los dos campos o solo en uno.

### Instituciones

Es la institución **donde se defendió** la tesis. **No** es la institución de los miembros del tribunal, que el registro de la tesis no contiene. Una profesora de Lyon en un tribunal de París aparece bajo París si se confunden las dos cosas. La adscripción declarada de cada jurado está en IdRef, servicio distinto y sin verificar, fuera del alcance de esta versión.

### Disciplinas

Texto libre según la especificación TEF: las variantes ortográficas **no se agrupan** y cuentan por separado. No se normaliza porque cualquier agrupación sería una decisión analítica no verificada.

### Red de co-participación

Nodo = miembro de tribunal (por PPN de persona). Arista = haber estado en el mismo tribunal. Comunidades por Louvain (`nx.community.louvain_communities`, en networkx desde la versión 2.7). Cada comunidad se etiqueta con la **persona de mayor grado dentro de ella**, no del grafo entero: la etiqueta describe el cluster, no el corpus.

**Advertencia estructural:** el tribunal de cada tesis es un *clique* completo, todos con todos. Si las tesis casi no comparten jurados, el grafo es un conjunto de cliques casi disjuntos y las comunidades reproducen las tesis, no agrupamientos del campo. El script calcula la modularidad y, si supera `red_total_umbral_modularidad`, avisa en el log y en el pie de la figura. Mientras ese aviso esté activo, los clusters no deben leerse como grupos académicos.

Por la misma razón, `componente_mayor` —la red calculada *dentro de cada período*— está apagada por defecto: un período con una sola tesis da 100% por construcción.

### Comparación contra el índice

Un 60% de resúmenes no dice lo mismo si el índice está al 85% que si está al 62%. En el primer caso el corpus está peor que la media y hay algo que entender; en el segundo está en la media. El mismo número, conclusiones opuestas.

**El nombre interrogable no siempre coincide con el del objeto de respuesta.** El registro trae `sujets` y `sujetsRameau`; el índice los expone como `sujetsLibelle` y `sujetsRameauLibelle`. Consultar el primero devuelve HTTP 200 con total 0 —no falla— y produce un porcentaje plausible y falso. Los nombres verificados están en `CAMPOS_PALABRAS_CLAVE` de S01; cualquier campo nuevo se toma de ahí, no de la estructura del registro.

Por eso el script incluye una **guardia de imposibilidad aritmética**: el corpus es un subconjunto del índice, así que ningún campo puede estar relleno en el corpus y ausente en el índice. Si eso ocurre, la consulta está rota y el campo se omite del informe con un ERROR que dice qué verificar, en lugar de imprimir una diferencia enorme a favor del corpus.

Dos límites más: `_exists_` dice si el campo está presente, no si el contenido sirve —un resumen de diez palabras cuenta igual que uno de mil—; y el acotado por rango de años **no está verificado**, así que el script lo comprueba en ejecución comparando el total acotado con el total del índice. Si coinciden, la restricción se está ignorando, y el informe lo declara en lugar de presentar como acotado algo que no lo está.

### Cero incidencias frente a comprobación imposible

Una columna **presente pero vacía en todo el corpus** no permite comprobar nada, y un contador en cero se leería como «no hay contradicciones» cuando lo cierto es «no se pudo mirar». El informe emite `sin datos` en ese caso, no `0`.

Afecta hoy a `datePremiereInscriptionDoctorat`: está al 0% en el corpus recuperado y al 1,6% en el índice, de modo que la comprobación «defensa anterior a la inscripción» no puede dispararse. Queda pendiente determinar si el endpoint de búsqueda no devuelve el campo o si es genuinamente así de raro.

## Datos personales

Los rankings de personas y la red de co-participación son datos personales de personas identificables. La red revela relaciones que ninguna ficha individual contiene: es información **nueva** sobre gente concreta, no una reorganización de lo publicado.

Abes publica los nombres al amparo del artículo 89.1 del RGPD y no cabe derecho de supresión sobre el registro de tesis defendidas. Eso cubre la fuente, no necesariamente lo que se derive de ella. Sustituir nombres por PPN **no anonimiza**: el PPN es público y resoluble en idref.fr, y el NNT identifica la tesis, cuya relación con la autora es prácticamente 1:1.

La decisión de qué columnas salen en un depósito público se parametriza aparte y no se resuelve en este archivo.

## Pendientes anotados

- **Enriquecimiento desde el dataset Aboucaya & Jasim (2026).** Aporta lo que la API no trae: PPN de SUDOC del manuscrito, identificador TEL, `accessible`, `embargo`, `phd_by_publication`, género inferido, fechas de nacimiento, `centrality`, edad en la defensa y los IdRef corregidos a mano. Unión por `nnt`; las tesis en preparación no tienen NNT y quedarían fuera del cruce. Su corte es el 2026-03-31. Corresponde a una etapa de enriquecimiento, no a S03: S03 consume, no recupera.
- **Detección de PPN no resolubles** contra idref.fr (límite (c)).
- **Modo `ambos`** de `entrada.modo`: comparación entre el universo curado y el sin curar. Declarado en el YAML, aún no implementado; el script avisa y corre como `candidatos`.
- **Red por período** (`componente_mayor`): declarada, sin implementar. El script avisa si se enciende.
- **Normalización de disciplinas** por lematización o *embeddings*, cuando se conozca mejor qué registra el campo.
- **Calibrar `red_total_umbral_modularidad`.** El 0.85 actual es conservador y no está calibrado contra este corpus.

## Referencias

Aboucaya, W. & Jasim, D. (2026). Doctoral theses in France (1985–2025): A linked dataset of PhDs, academic networks, and institutions. *Data in Brief*, 67, 112947. https://doi.org/10.1016/j.dib.2026.112947

Abes (2026). *Le moteur de recherche theses.fr*. https://documentation.abes.fr/aidethesesfr/index.html

Rule, A., Birmingham, A., Zuniga, C., Altintas, I., Huang, S-C., Knight, R., et al. (2019). Ten simple rules for writing and sharing computational analyses in Jupyter Notebooks. *PLoS Computational Biology*, 15(7), e1007007. https://doi.org/10.1371/journal.pcbi.1007007

Retina — OuestWare, CNRS CIS y Tommaso Venturini. https://retina.cortext.net/ · documentación: https://docs.cortext.net/tools/retina/
