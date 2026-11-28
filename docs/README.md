# Documentación — BankAgent (Banamex Portfolio Agent)

Índice maestro de la documentación técnica, guías de configuración, contexto vivo y planeación del proyecto.

---

## Orden de Lectura Recomendado

| # | Documento | Carpeta | Para qué sirve |
| :-: | :--- | :--- | :--- |
| 1 | [README principal](../README.md) | Raíz | Centro del proyecto: ejecución, carpetas y consideraciones clave |
| 2 | [Manual de Usuario (Consola Web)](guias/MANUAL_USUARIO.md) | `guias/` | Guía paso a paso para analistas de riesgo (interfaz, chat, políticas y reportes) |
| 3 | [Convenciones Oficiales y Definition of Done](guias/CONVENCIONES.md) | `guias/` | Patrones de diseño, nombrado, fronteras por capa y checklist de PR |
| 4 | [Colaboración y Contexto (Humanos + IA)](guias/COLABORACION_Y_CONTEXTO_IA.md) | `guias/` | Reglas de Git, PRs y dónde dejar actualizaciones/contexto |
| 5 | [Buenas Prácticas de Ingeniería](guias/BUENAS_PRACTICAS.md) | `guias/` | PEP 8, contratos Pydantic, seguridad sandbox, SQL y pruebas |
| 6 | [Arquitectura y Librerías](arquitectura/ARQUITECTURA_Y_LIBRERIAS.md) | `arquitectura/` | Diagramas Mermaid, stack técnico y los 5 guardrails |
| 7 | [Pipeline Técnico y de Agentes](arquitectura/PIPELINE_AGENTES.md) | `arquitectura/` | Flujo end-to-end, LangGraph, router del copiloto y memoria adaptativa |
| 8 | [Guion de Presentación (12 Slides)](guias/GUION_PRESENTACION.md) | `guias/` | 6 slides ejecutivas (Comité) + 6 slides técnicas (Arquitectura/CI) |
| 7 | [Contexto Vivo (ADRs y Handoffs)](contexto/README.md) | `contexto/` | Decisiones técnicas acumuladas, benchmarks y notas por issue |
| 8 | [Guía de Arranque Local](guias/guia_arranque_local.md) | `guias/` | Configuración y ajustes locales (RTX 4070 / 8 GB VRAM) |
| 9 | [Backlog de Issues del Equipo](planeacion/ISSUES.md) | `planeacion/` | Las 13 issues oficiales (`Jose`, `Fab`, `Diego` + equipo) con criterios de aceptación |
| 10 | [Contexto Maestro MVP](arquitectura/MVP_CONTEXT_AGENT_BANAMEX.md) y [TASKS](planeacion/TASKS.md) | `arquitectura/` · `planeacion/` | Especificación original del cubo y progreso por etapas |

---

## Estructura de `docs/`

```text
docs/
├── README.md                                  # Este índice maestro
├── arquitectura/
│   ├── ARQUITECTURA_Y_LIBRERIAS.md            # Diagramas, librerías, guardrails y sandbox
│   ├── MVP_CONTEXT_AGENT_BANAMEX.md           # Especificación maestra original del MVP
│   └── PIPELINE_AGENTES.md                    # Pipeline end-to-end, LangGraph y memoria
├── contexto/
│   └── README.md                              # Contexto vivo: ADRs, handoffs y benchmarks
├── guias/
│   ├── BUENAS_PRACTICAS.md                    # PEP 8, contratos, sandbox, SQL y testing
│   ├── COLABORACION_Y_CONTEXTO_IA.md          # Flujo Git y protocolo para humanos e IA
│   ├── CONVENCIONES.md                        # Patrones, nombrado, capas y checklist de PR
│   ├── GUION_PRESENTACION.md                  # Guion de 12 slides (6 ejecutivas + 6 técnicas)
│   ├── MANUAL_USUARIO.md                      # Manual paso a paso para el analista de riesgo
│   ├── guia_arranque_local.md                 # Configuración y arranque 100% local
│   └── guia_arranque_original_ssh.md          # Referencia original del curso (2 equipos / SSH)
└── planeacion/
    ├── ISSUES.md                              # 13 issues asignadas al equipo
    └── TASKS.md                               # Checklist histórico por etapas
```
