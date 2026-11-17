# **Guía de arranque: antes de escribir código**

Esta guía detalla lo que hay que dejar resuelto antes de la primera línea de código del asistente de análisis de portafolio, y dice en qué equipo se hace cada cosa para no repetir trabajo. Se estima en uno o dos días, y la parte que depende del socio formador se pide el primer día para trabajar mientras llega.

## **Dónde se hace cada cosa**

La regla es sencilla: la laptop sirve para todo lo que no necesita el modelo, incluido trabajar con el cubo de datos; la estación de la universidad (por SSH) se usa solo para lo que necesita la GPU. El código vive en GitHub.

| Lugar | Para qué sirve | Qué se hace ahí |
| ----- | ----- | ----- |
| Laptop | Corre Python y DuckDB sin problema con el cubo sintético; no tiene potencia para el modelo | Explorar el cubo con DuckDB, desarrollar y probar las consultas y las gráficas (Plotly), armar el diccionario de datos y el Golden Dataset, diseñar el contrato de las herramientas, redactar documentos y revisar las plantillas |
| Estación de la universidad (por SSH) | Tiene la RTX A4500 y los 20 GB de VRAM | Instalar Ollama y el modelo, probar el modelo y el JSON de herramientas, medir VRAM y velocidad, correr el agente completo |
| GitHub | Guarda el código de forma segura y sincroniza los dos equipos | Repositorio privado, clonado en la laptop y en la estación |

**Para no hacer doble trabajo**

* El modelo se instala una sola vez, en la estación. No se descarga nada de Ollama en la laptop.  
* El código vive en un repositorio privado de GitHub, clonado en la laptop y en la estación. Se sincroniza con push y pull, y lo que se cambie directo en la estación se sube antes de cerrar la sesión.  
* Como el cubo es sintético, se trabaja con él en la laptop y se copia a la estación solo cuando haga falta para correr el agente completo. Confirma con el socio formador que se puede subir a un repositorio privado; si no, déjalo fuera de Git y cópialo aparte.  
* Las herramientas del cubo (consultas y gráficas) se desarrollan y prueban en la laptop, sin el modelo. La estación solo las usa cuando el agente las llama.  
* Cada documento (diccionario de datos, Golden Dataset, contrato de herramientas) se escribe una vez y se guarda dentro del repositorio, no en notas sueltas.

## **Orden sugerido**

* **Día 1:** tareas 1 a 4\. Las tareas 1 y 2 piden cosas a otras personas, así que se mandan primero y las demás avanzan mientras responden.  
* **Día 2:** tareas 5 a 9\.

## **Tarea 1 · Pedir al supervisor lo que depende del banco**

**Dónde:** laptop.

**Para qué sirve:** es lo que más tarda en llegar y con un plazo de 3 semanas no se puede esperar a necesitarlo para pedirlo.

**Qué pedir:**

* Entre 2 y 3 documentos de apetito de riesgo, en PDF o Markdown, por ejemplo el límite de pérdida neta esperada por segmento. Alimentan la memoria institucional.  
* Las plantillas del banco para el memorándum (.docx) y la presentación (.pptx).  
* El diccionario de columnas del cubo, o a alguien que pueda explicarlas.  
* Un puñado de preguntas reales que un analista haría, para armar el Golden Dataset.  
* Confirmación de que el archivo sintético se puede subir a un repositorio privado de GitHub, o si debe quedarse fuera de Git.

**Listo cuando:** el mensaje está enviado y hay una fecha acordada para recibir cada cosa. Si algo no llega a tiempo, el plan sigue: sin políticas, el agente declara que no pudo contrastar contra política.

## **Tarea 2 · Revisar la estación por SSH**

**Dónde:** estación.

**Para qué sirve:** confirmar que el hardware y el software cumplen lo que el proyecto supone, antes de instalar nada.

**Qué revisar:**

* GPU y driver con `nvidia-smi`: debe verse la RTX A4500 con 20 GB, driver 535 o superior y CUDA 12.1 o 12.4. Revisa también si otras personas están usando la GPU y cuánta VRAM está libre de verdad, porque la estación es de la universidad y puede ser compartida.  
* Sistema operativo (Ubuntu 22.04 o 24.04, o Windows 11 con WSL2).  
* Espacio en disco con `df -h`, y si hay cuota por usuario: el modelo y sus versiones pesan varios gigabytes.  
* Memoria con `free -h` y núcleos con `nproc`.  
* Qué hay instalado: Python, Docker, Ollama.  
* Permisos: si puedes instalar Ollama y paquetes sin ser administrador, y si la estación puede descargar paquetes y modelos.  
* Acceso: si el SSH requiere una VPN de la universidad y quién administra la estación, para saber a quién pedir ayuda si algo falla.

**Listo cuando:** hay una tabla con los valores encontrados frente a lo requerido, y cualquier diferencia está anotada como pendiente.

## **Tarea 3 · Crear el entorno de trabajo**

**Dónde:** laptop y estación.

**Para qué sirve:** que todo el equipo trabaje con las mismas versiones y que el proyecto se pueda reproducir.

**Qué hacer:**

* Crear el repositorio privado en GitHub, con carpetas para los datos, las políticas internas, las salidas y las pruebas.  
* Clonarlo en la laptop y en la estación.  
* Crear el entorno con uv en Python 3.11 en los dos equipos, con el mismo archivo de versiones para que coincidan. En la estación, verificar que uv pueda instalar paquetes.  
* Configurar la conexión cómoda a la estación desde la laptop: VS Code con Remote-SSH, y tmux para que las sesiones largas no se pierdan si se corta la conexión.

**Listo cuando:** el mismo código corre en la laptop y en la estación con un simple git pull, y desde la laptop se puede entrar a la estación por SSH.

## **Tarea 4 · Instalar Ollama y probar el modelo**

**Dónde:** estación.

**Para qué sirve:** confirmar lo antes posible que el modelo elegido funciona en este hardware y con herramientas, porque es lo que más riesgo tiene.

**Qué hacer:**

* Instalar Ollama y descargar Qwen3.5 de 9B. Verifica en la biblioteca de Ollama el nombre exacto de la etiqueta, porque cambia con el tiempo.  
* Mientras el modelo responde, observar `nvidia-smi` para ver cuánta VRAM usa con una ventana de contexto de 16,384 tokens.  
* Medir la velocidad en tokens por segundo (por ejemplo con `ollama run` en modo detallado).  
* Hacer la prueba más importante: pedirle que responda con un JSON de herramienta, como `{"funcion": "consultar_metricas_segmento", "vintage": "202511"}`, y repetirlo unas 10 veces. Qwen3.5 trae el razonamiento activado por defecto, y eso puede estropear el formato.  
* Si falla el formato, anotar cómo falla y probar apagando el razonamiento o ajustando el prompt.

**Listo cuando:** el modelo cabe con holgura en la VRAM con 16k de contexto, la velocidad es cómoda para conversar, y el JSON sale válido en las 10 pruebas (criterio sugerido). Si no se logra, es la señal para probar el Qwen3.5 de 27B o el plan alterno.

## **Tarea 5 · Entender el cubo de datos**

**Dónde:** laptop.

**Para qué sirve:** de aquí salen los filtros permitidos de las herramientas. Si no se conocen los datos, los esquemas de Pydantic se escriben mal y se rehacen.

**Qué hacer:**

* Abrir el CSV con DuckDB (en terminal o en Python) y contar filas.  
* Listar todas las columnas con su tipo.  
* Obtener los valores distintos de VINTAGE, PRODUCT, CHANNEL, AGE\_TAG, STRATEGY\_SEGMENT y el rango de MOB.  
* Verificar que existan y tengan datos las métricas clave: NCLAMTS, REVENUE, EXPENSES\_TOTAL y OVER30AMTS.  
* Buscar valores nulos, cohortes con pocos meses de maduración y valores raros.  
* Calcular a mano un par de cifras sencillas, por ejemplo la pérdida neta total por canal, para usarlas luego como referencia.

**Listo cuando:** hay un diccionario de datos de una página con cada columna, su significado, su tipo y los valores válidos de cada filtro.

## **Tarea 6 · Preparar el Golden Dataset inicial**

**Dónde:** laptop.

**Para qué sirve:** es el examen del agente. Con él se sabe si el modelo acierta o inventa, y permite comparar el 9B contra el 27B con datos y no con impresiones.

**Qué hacer:**

* Empezar con unos 10 casos y dejar crecer hasta los 50 del plan original. Una distribución razonable es 4 del Nivel 1, 3 del Nivel 2 y 3 del Nivel 3 (sugerencia).  
* Para cada caso, una fila con: la pregunta, el nivel, los filtros, la cifra esperada, la conclusión esperada y la política aplicable.  
* La cifra esperada se calcula con una consulta directa a DuckDB en la laptop, nunca con el modelo.  
* Guardar el archivo dentro del repositorio.

**Listo cuando:** hay 10 casos con respuesta verificada contra el cubo.

## **Tarea 7 · Definir el contrato de las herramientas**

**Dónde:** laptop.

**Para qué sirve:** es el diseño de las Skills sobre papel. Al escribirlo antes, el código se escribe una sola vez.

**Qué hacer:** una tabla con una fila por herramienta (consultar métricas de un segmento, obtener la curva de maduración, comparar contra el benchmark, generar gráfica), con estas columnas:

* Nombre de la función.  
* Parámetros permitidos y sus valores válidos, tomados del diccionario de datos.  
* Qué devuelve.  
* Qué error devuelve si el filtro no existe o no hay datos.

**Listo cuando:** la tabla está completa y cada parámetro se puede pasar directo a un esquema de Pydantic.

## **Tarea 8 · Definir la estructura de los reportes**

**Dónde:** laptop.

**Para qué sirve:** el Nivel 4 depende de saber qué lleva el memorándum y la presentación.

**Qué hacer:**

* Revisar las plantillas del banco cuando lleguen.  
* Si no llegan, proponer un borrador con las secciones: resumen, evidencia en tabla, gráfica, dictamen, política contrastada y recomendación.  
* Anotar qué dato del cubo alimenta cada sección.

**Listo cuando:** hay una lista de secciones con su fuente de datos, aunque sea provisional.

## **Tarea 9 · Dejar fijo el flujo entre laptop y estación**

**Dónde:** ambos.

**Para qué sirve:** evitar que el trabajo quede repartido en dos lugares.

**Qué acordar:**

* El repositorio privado de GitHub es la única fuente de verdad. Se trabaja con commits pequeños y se sincroniza con push y pull; lo que se cambie directo en la estación se sube antes de cerrar la sesión.  
* Para ver interfaces como Streamlit u Open WebUI desde la laptop, se usa un túnel SSH que reenvía el puerto de la estación.  
* Quién toca cada parte (modelo y orquestador, cubo y gráficas, reportes), para no pisarse.

**Listo cuando:** todos pueden clonar, editar y ejecutar desde su laptop sin pasos manuales.

## **Cómo saber que ya se puede empezar a programar**

* La solicitud al supervisor está enviada, con fechas de entrega.  
* La estación está revisada y sin bloqueos pendientes.  
* El repositorio está en GitHub y el mismo código corre en la laptop y en la estación.  
* El modelo corre en la estación, cabe en la VRAM con 16k de contexto y devuelve JSON válido.  
* El diccionario de datos y el contrato de herramientas están escritos.  
* Hay al menos 10 casos con respuesta verificada en el Golden Dataset.

