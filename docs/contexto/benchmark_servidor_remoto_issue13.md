# Issue 13 · Benchmark local vs. servidor remoto (GPU)

**Fecha de las pruebas:** 2026-11-27 · **Comando:** `uv run python -m tests.smoke_test_agent --benchmark` (Golden Dataset de 10 casos, `temperature=0.0`, `reasoning=False`, `num_ctx=16384`).

Cómo conectarse al servidor y reproducir estas pruebas: [`guia_servidor_remoto.md`](../guias/guia_servidor_remoto.md).

---

## 1. Resumen

| Hallazgo | Detalle |
| :--- | :--- |
| **El servidor remoto funciona** | Una laptop con el código y los datos locales usando el modelo del servidor por túnel SSH obtiene el **mismo resultado** que correr todo en el servidor (7/10 y los mismos casos). |
| **El 27B es más preciso** | `qwen3.8:latest` (27B) sube de **7/10 a 9/10**, con un tiempo total parecido al del 9B en el mismo servidor. |
| **El servidor es ~2x más rápido que la laptop con RTX 4070** | Mismo modelo 9B: ~143 s en el servidor contra ~288 s en la laptop. En casos simples la diferencia llega a ~4x. |
| **El 27B cabe, pero justo** | Con `num_ctx=16384` usa 19,227 de 20,470 MiB (94 %) y corre 100 % en GPU. Subir el contexto probablemente lo pasaría a RAM. |
| **16384 de contexto sí hace falta** | GD-09 consume ~10.4 mil tokens, más de lo que cabe en 8192. |

---

## 2. Configuraciones probadas

| Configuración | Modelo | Dónde corre el modelo | Dónde corre el código y DuckDB | Commit |
| :--- | :--- | :--- | :--- | :--- |
| **A. 9B en servidor** | `qwen3.5:9b` | Servidor (RTX A4500, 20 GB) | Servidor | `main` `fc588ad` |
| **B. 9B laptop → servidor** | `qwen3.5:9b` | Servidor (RTX A4500, 20 GB) | Laptop del equipo, por túnel SSH | hash no registrado |
| **C. 27B en servidor** | `qwen3.8:latest` (27B, Q4_K_M) | Servidor (RTX A4500, 20 GB) | Servidor | `841d443` |
| **D. 9B local** | `qwen3.5:9b` | Laptop (RTX 4070 Laptop, 8 GB, Windows) | Misma laptop | rama `featFabrizio` `841d443` |

Hardware del servidor: NVIDIA RTX A4500 (20 GB VRAM), 62 GB de RAM, Fedora, Ollama en `localhost:11434`.
Una laptop con GTX 1650 (4 GB) no pudo usarse como "local": el modelo de 6.6 GB no cabe en su VRAM. Por lo cual,
se hicieron pruebas con una laptop RTX4070 (8GB), la cual se uso como local.

---

## 3. Resultados globales

| | A. 9B servidor | B. 9B laptop→servidor | C. 27B servidor | D. 9B local (4070) |
| :--- | :-: | :-: | :-: | :-: |
| **Score del Golden Dataset** | 7/10 (70 %) | 7/10 (70 %) | **9/10 (90 %)** | 8/10 (80 %) ¹ |
| **Tiempo total (10 casos)** | 142.6 s | 94.7 s | 157.5 s | 287.6 s |
| **Tiempo promedio por caso** | 14.3 s | 9.5 s | 15.8 s | 28.8 s |
| **Tokens de contexto usados (prom. / máx.)** | 5,241 / 10,397 | 5,186 / 10,396 | 4,690 / 5,903 | 4,819 / 8,422 |
| **Primera respuesta del smoke test (incluye carga del modelo)** | 2.3 s | 2.5 s | 9.6 s | 4.8 s |
| **VRAM usada con el modelo cargado** | no medida | no medida (corre en el servidor) | **19,227 / 20,470 MiB (94 %)** | 7,113 / 8,188 MiB (87 %) |
| **`ollama ps`** | no registrado | no registrado | `17 GB · 100% GPU · contexto 16384` | pendiente |

¹ El 8/10 incluye un **falso fallo** (GD-04, ver sección 6). Con el formato de cifras aceptado, el resultado real sería 9/10.

Los "tokens de contexto" son los tokens del último prompt de cada caso (`ctx=N/16384` en la salida del benchmark), no tokens generados.

---

## 4. Detalle por caso

Formato: resultado y tiempo. `guardrail=False` significa que el verificador de cifras rechazó algún número de la respuesta.

| Caso | Nivel | A. 9B servidor | B. 9B laptop→servidor | C. 27B servidor | D. 9B local (4070) |
| :--- | :-: | :--- | :--- | :--- | :--- |
| GD-01 | N1 | PASS · 3.0 s | PASS · 4.1 s | PASS · 3.3 s | PASS · 12.8 s |
| GD-02 | N1 | PASS · 2.0 s | PASS · 2.8 s | PASS · 5.8 s | PASS · 10.4 s |
| GD-03 | N1 | PASS · 3.8 s | PASS · 4.5 s | PASS · 5.1 s | PASS · 17.3 s |
| GD-04 | N1 | PASS · 2.8 s | PASS · 3.5 s | **FAIL** · 5.6 s ³ | **FAIL** · 11.7 s ¹ |
| GD-05 | N2 | PASS · 3.4 s | PASS · 4.0 s | PASS · 26.1 s | PASS · 21.2 s |
| GD-06 | N2 | **FAIL** · 7.5 s | **FAIL** · 9.1 s | PASS · 6.8 s | PASS · 22.2 s |
| GD-07 | N2 | **FAIL** · 9.7 s (guardrail=False) | **FAIL** · 11.2 s (guardrail=False) | PASS · 15.7 s | **FAIL** · 41.1 s (guardrail=False) |
| GD-08 | N3 | **FAIL** · 30.7 s (guardrail=False) | **FAIL** · 24.0 s (guardrail=False) | PASS · 33.2 s | PASS · 42.8 s |
| GD-09 | N3 | PASS · 55.5 s | PASS · 20.9 s | PASS · 23.0 s | PASS · 72.6 s |
| GD-10 | N3 | PASS · 24.2 s | PASS · 10.6 s | PASS · 32.9 s | PASS · 35.5 s |

³ En GD-04 el 27B aplicó por su cuenta el filtro de cohortes maduras (`MOB >= 6`), que la pregunta no pedía, y entregó cifras distintas a las esperadas (341,591,845 en vez de 349,559,488). Las cifras sí venían de DuckDB; el error es de interpretación, no de invención.

---

## 5. Conectividad

| Prueba (`tests.check_ollama_connection`) | Latencia de `/api/tags` |
| :--- | :-: |
| En el servidor, contra `localhost` | 7 ms |
| Desde la laptop por túnel SSH | 404 a 700 ms |
| En la laptop del compañero, contra `localhost` (primera llamada) | 2,104 ms |

El túnel agrega algo menos de 1 s en los casos simples (A contra B: GD-01 a GD-05 pasan de 2.0 a 3.8 s a 2.8 a 4.5 s). En los casos largos los tiempos varían de una corrida a otra (GD-09 tardó 55.5 s en A y 20.9 s en B con el mismo modelo y servidor), así que no deben usarse para sacar conclusiones finas.

---

## 6. Hallazgos y recomendaciones

1. **Usar el 27B en el servidor.** Resuelve GD-06, GD-07 y GD-08, que el 9B falla en el servidor, con un tiempo total similar. Su único fallo (GD-04, que el 9B sí acierta) es de interpretación y es candidato para la issue 3 (contratos claros que eviten filtros no pedidos).
2. **El 9B queda para equipos con poca VRAM.** En una laptop de 8 GB corre completo, pero va justo y es unas 2 veces más lento que en el servidor.
3. **Mantener `num_ctx=16384` (valor por defecto actual).** En una corrida anterior, con el código previo y `num_ctx=8192`, GD-09 llenó la ventana (8,158/8,192 tokens) y no terminó. Con 16384 termina usando ~10.4 mil.
4. **No subir el contexto del 27B por encima de 16384** sin medir: queda ~1.2 GB de margen en la VRAM.
5. **Corregir el Golden Dataset.** Los casos con `palabras_clave_esperadas` solo en formato con comas (por ejemplo `349,559,488.69`) marcan fallo si el modelo escribe la misma cifra sin comas (`349559488.69`). Conviene aceptar ambos formatos.
6. **Fallos persistentes del 9B (GD-06, GD-07, GD-08).** En GD-07 y GD-08 el guardrail rechaza algún número de la respuesta, probablemente cifras calculadas por el modelo en lugar de copiadas de la herramienta. Falta revisar `guardrail_issues` de cada caso. Se resuelve mejor con las skills deterministas (issue 2) y contratos más estrictos (issue 3).
7. **El túnel no altera el comportamiento del modelo.** A y B dan el mismo resultado y casi los mismos tokens por caso (GD-10 es la excepción: 5,377 contra 4,836).

---

## 7. Limitaciones

* Una sola corrida por configuración. Con `temperature=0.0` el resultado es casi reproducible en la misma máquina, pero hardware distinto puede dar diferencias (GD-06 pasa en la RTX 4070 y falla en la A4500).
* No se midieron tokens por segundo, solo tiempo por caso.
* La VRAM del 9B en el servidor no se registró durante el benchmark.

## 8. Contexto histórico (código y datos distintos, no comparable directamente)

| Situación | Score |
| :--- | :-: |
| Servidor sin la base DuckDB construida (el modelo reportaba que no encontraba el archivo) | 2/10 |
| Base construida, antes del arreglo del guardrail (igual con `num_ctx` 8192 y 16384) | 5/10 |
| `main` con el arreglo del guardrail (configuración A) | 7/10 |

## 9. Pendientes

* [ ] Agregar la salida de `ollama ps` del 9B en la laptop del compañero (RTX 4070).
* [ ] Aceptar ambos formatos numéricos en `tests/golden_dataset.json` (hallazgo 5).
* [ ] Diagnosticar `guardrail_issues` de GD-07 y GD-08.
