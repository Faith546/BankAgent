# Guía: usar el servidor remoto con GPU (estación del Tec)

Cómo conectar el proyecto a la estación con GPU de la universidad, que funciona como servidor del modelo. Resultados medidos: [`benchmark_servidor_remoto_issue13.md`](../contexto/benchmark_servidor_remoto_issue13.md).

> En esta guía, `<usuario>` es tu usuario en la estación e `<ip-servidor>` su dirección (te las da quien administra la estación). Son marcadores: no los escribas literalmente.

---

## 1. Cómo encajan las piezas

```text
 Tu laptop                                     Estación del Tec (servidor)
 ┌──────────────────────────┐   túnel SSH      ┌──────────────────────────┐
 │ Código del proyecto      │ ───────────────► │ Ollama (modelo en GPU)   │
 │ DuckDB + ChromaDB (local)│  11435 → 11434   │ RTX A4500, 20 GB VRAM    │
 │ Streamlit (opcional)     │                  │ Modelos qwen3.5 / qwen3.8│
 └──────────────────────────┘                  └──────────────────────────┘
```

* **Solo el modelo vive en el servidor.** Las consultas a los datos (DuckDB) y las políticas (ChromaDB) corren donde ejecutas el código. Si usas el modelo remoto desde tu laptop, tu laptop necesita la base DuckDB construida (sección 7).
* No necesitas GPU ni mucha RAM en tu laptop: el modelo corre en el servidor.
* Todo es red interna: no hay APIs en la nube ni salida a internet.

---

## 2. Requisitos

1. Estar en la red de la universidad o con la VPN activa (hay que alcanzar `<ip-servidor>`).
2. Una cuenta SSH en la estación.
3. En tu laptop: `uv` instalado, el repo clonado y `uv sync` ejecutado.
4. Cliente `ssh`: en Windows ya viene en PowerShell.

---

## 3. Modo recomendado: túnel SSH desde tu laptop

No requiere configurar nada en el servidor. Necesitas **dos terminales en tu laptop** (en PowerShell, el prompt empieza con `PS C:\...`).

**Terminal 1: el túnel (déjala abierta mientras trabajes):**

```powershell
ssh -L 11435:localhost:11434 <usuario>@<ip-servidor>
```

Usa el puerto local `11435` para no chocar con un Ollama que ya corra en tu laptop (`11434`). Si el primer intento da `Connection timed out`, repítelo.

**Terminal 2: en la carpeta del proyecto:**

```powershell
$env:OLLAMA_BASE_URL="http://localhost:11435"
uv run python -m tests.check_ollama_connection
```

En Mac o Linux: `OLLAMA_BASE_URL=http://localhost:11435 uv run python -m tests.check_ollama_connection`.

Si la lista de modelos que aparece es la del servidor (por ejemplo `qwen3.8:latest`), el túnel funciona. Ya puedes correr cualquier comando del proyecto en esa terminal (smoke test, benchmark, Streamlit).

En lugar de la variable de terminal puedes usar un archivo `.env` (sección 5).

---

## 4. Otros modos

**B. Correr todo dentro del servidor.** Entra por SSH, clona el repo ahí y ejecuta los comandos en la sesión del servidor. Usa `tmux` para que la sesión sobreviva si se corta la conexión:

```bash
ssh <usuario>@<ip-servidor>
tmux new -s bench          # volver después: tmux attach -t bench
cd ~/BankAgent
OLLAMA_MODEL=qwen3.8:latest uv run python -m tests.smoke_test_agent --benchmark
```

Para salir de `tmux` sin detener el proceso: `Ctrl+B`, soltar y luego `D`.

---

## 5. Configuración con `.env`

El proyecto lee un archivo `.env` en la raíz (está en `.gitignore`). Cópialo de la plantilla y ajústalo:

```powershell
Copy-Item .env.example .env
```

```env
OLLAMA_BASE_URL=http://localhost:11435   # túnel SSH; http://localhost:11434 si Ollama es local
OLLAMA_MODEL=qwen3.5:9b                  # en el servidor puedes usar qwen3.8:latest (27B)
OLLAMA_NUM_CTX=16384
```

* Las variables definidas en la terminal ganan sobre el `.env`.
* `OLLAMA_BASE_URL` solo acepta `http://host[:puerto]` (Ollama no usa TLS). Con `https://`, sin esquema o con ruta, el proyecto falla al arrancar con un mensaje que indica cómo corregirla.

---

## 6. Modelos y contexto recomendados

| Dónde | Modelo | `num_ctx` | Nota |
| :--- | :--- | :-: | :--- |
| Servidor (20 GB) | `qwen3.8:latest` (27B) | 16384 | 9/10 en el Golden Dataset; usa ~94 % de la VRAM |
| Servidor (20 GB) | `qwen3.5:9b` | 16384 | 7/10; más liviano |
| Laptop con 8 GB | `qwen3.5:9b` | 16384 | Cabe (~87 % de VRAM) pero ~2x más lento que el servidor |
| Laptop con 4 GB | (usar el servidor) | | El 9B pesa 6.6 GB y no cabe en la GPU |

---

## 7. Datos que necesita tu laptop

El CSV (`data/raw/base_cards_sintetica.csv`, ~190 MB) **no está en Git**. Pídeselo a un compañero y colócalo en `data/raw/`. Después, con el túnel abierto y `OLLAMA_BASE_URL` puesta:

```powershell
uv run python -m src.data.init_db
uv run python -c "from src.skills.rag_tools import ingest_policies; print('Chunks:', ingest_policies())"
```

El primer comando construye la base DuckDB y debe terminar con 1,089,833 filas y 64,245 cohortes. El segundo indexa las políticas usando el modelo de embeddings del servidor.

Si falta la base, el agente responde que no encuentra `cubo_banamex.duckdb` y el benchmark da ~1/10.

---

## 8. Verificación

| Qué | Comando |
| :--- | :--- |
| Conexión, modelos instalados y VRAM cargada | `uv run python -m tests.check_ollama_connection` |
| Smoke test (4 pruebas de efecto) | `uv run python -m tests.smoke_test_agent` |
| Benchmark del Golden Dataset | `uv run python -m tests.smoke_test_agent --benchmark` |
| VRAM del servidor en vivo | en el servidor: `watch -n 1 nvidia-smi` |
| Modelo cargado y % en GPU | en el servidor: `ollama ps` (con el modelo cargado, unos 5 min tras usarlo) |

`check_ollama_connection` muestra la GPU de la **máquina donde lo ejecutas**; con túnel eso es tu laptop, no el servidor. La VRAM del servidor sale de `/api/ps` (o de `nvidia-smi` dentro del servidor).

---

## 9. Streamlit en el servidor

```bash
ssh <usuario>@<ip-servidor>
tmux new -s app
cd ~/BankAgent
uv run streamlit run app/streamlit_app.py --server.address localhost
```

Desde tu laptop abre un túnel y entra a `http://localhost:8501`:

```powershell
ssh -L 8501:localhost:8501 <usuario>@<ip-servidor>
```

Para dejarlo corriendo: `Ctrl+B`, `D`. Para detenerlo: `tmux attach -t app` y `Ctrl+C`.

* **Seguridad:** sin `--server.address localhost`, Streamlit escucha en todas las interfaces y la app (sin login) puede quedar accesible desde la red o desde fuera. Usa el túnel.
* **Telemetría:** para que Streamlit no envíe estadísticas de uso a internet, agrega en `.streamlit/config.toml`:

  ```toml
  [browser]
  gatherUsageStats = false
  ```

* El historial de chats vive en `data/state/` del servidor y es compartido; si varias personas usan la misma instancia pueden mezclarse conversaciones.

---

## 10. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
| :--- | :--- | :--- |

| `The authenticity of host ... can't be established` al abrir el túnel | Estás corriendo el comando dentro del servidor (el prompt es `usuario@fedora`) | El túnel se abre desde tu laptop (`PS C:\...`) |
| `Connection timed out` | Red o VPN | Verifica que estás en la red de la universidad y reintenta |
| `check_ollama_connection`: `Connection refused` | El túnel no está abierto o Ollama no corre en el servidor | Revisa la terminal del túnel; en el servidor: `curl http://localhost:11434/api/tags` |
| `channel N: open failed: connect failed: Connection refused` en la terminal del túnel | Algo en tu laptop usa un puerto reenviado y en el servidor no hay nada escuchando (por ejemplo, una pestaña abierta de `localhost:8501` con Streamlit apagado) | Cierra la pestaña o enciende Streamlit |
| `localhost refused to connect` al abrir Streamlit | `localhost` es tu laptop; falta el túnel del puerto 8501 | Abre `ssh -L 8501:localhost:8501 ...` |
| El agente dice que no encuentra `cubo_banamex.duckdb`; benchmark ~1/10 | Falta la base DuckDB en la máquina donde corre el código | Sección 7 |
| `OLLAMA_BASE_URL=... usa https://` o `debe empezar con 'http://'` | URL mal escrita | Usa `http://host:puerto` |
| El puerto `11434` ya está ocupado en tu laptop | Tienes Ollama local | Usa `11435` en el túnel (como en esta guía) |
| `uv: command not found` en el servidor | `uv` no está en el PATH | `export PATH="$HOME/.local/bin:$PATH"` y agrégalo a `~/.bashrc` |
