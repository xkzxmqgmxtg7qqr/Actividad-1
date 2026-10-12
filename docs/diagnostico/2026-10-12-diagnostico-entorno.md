# Informe de diagnóstico técnico del entorno de desarrollo

**Proyecto:** Laboratorio de Investigación Académica Asistido por IA
**Fecha:** 2026-10-12
**Fase:** Diagnóstico inicial (sin instalaciones ni modificaciones)

---

## 1. Alcance y limitaciones

Este diagnóstico se ejecutó en el **entorno de trabajo del agente en la nube**
(máquina virtual Linux), no directamente en el Mac del investigador. Por tanto:

- Los resultados de la sección 2 describen el entorno de nube donde se
  desarrollará y validará el laboratorio.
- Para diagnosticar el Mac local, ejecutar el script reproducible
  [`scripts/diagnostico_entorno.sh`](../../scripts/diagnostico_entorno.sh),
  que realiza exactamente las mismas comprobaciones sin instalar ni modificar
  nada, y genera un informe en Markdown.

## 2. Resultados del diagnóstico (entorno de nube)

### 2.1 Sistema operativo

| Componente | Valor |
|---|---|
| SO | Ubuntu 24.04.5 LTS (kernel 6.12.94+, x86_64) |

### 2.2 Herramientas principales

| Herramienta | Estado | Versión detectada | Observaciones |
|---|---|---|---|
| **Python** | ✅ Instalado | 3.12.3 (`/usr/bin/python3`) | pip 24.0 disponible |
| **R** | ❌ No instalado | — | Ni `R` ni `Rscript` en el PATH |
| **Git** | ✅ Instalado y configurado | 2.43.0 | `user.name` y `user.email` configurados; repositorio operativo |
| **Quarto** | ❌ No instalado | — | Necesario para informes reproducibles |
| **LaTeX** | ❌ No instalado | — | Sin `pdflatex`, `xelatex`, `lualatex` ni `tectonic` |
| **Pandoc** | ❌ No instalado | — | Dependencia de Quarto para conversión de documentos |

### 2.3 Ecosistema científico de Python

| Paquete | Estado | Versión | Uso previsto en el laboratorio |
|---|---|---|---|
| numpy | ✅ | 1.26.4 | Cálculo numérico |
| pandas | ❌ | — | Manipulación de datos tabulares |
| scipy | ❌ | — | Estadística y optimización |
| statsmodels | ❌ | — | Modelos estadísticos inferenciales |
| scikit-learn | ❌ | — | Aprendizaje automático y validación cruzada |
| matplotlib / seaborn / plotly | ❌ | — | Visualización |
| nltk | ❌ | — | Procesamiento de lenguaje natural |
| NRCLex | ❌ | — | Análisis de emociones (NRC Emotion Lexicon) |
| jupyter | ❌ | — | Exploración interactiva |
| bibtexparser | ❌ | — | Automatización bibliográfica |

## 3. Conclusiones del diagnóstico

1. **Base funcional mínima:** el entorno dispone de Python 3.12 y Git
   correctamente configurados, suficientes para control de versiones y
   scripting, pero no para el flujo científico completo.
2. **Carencias críticas para la reproducibilidad:** sin R, Quarto, LaTeX y
   Pandoc no es posible generar informes científicos reproducibles ni
   ejecutar los análisis estadísticos en R previstos.
3. **Carencias del stack analítico de Python:** faltan los paquetes
   fundamentales de análisis de datos, estadística, PLN (incluido NRCLex para
   el NRC Emotion Lexicon) y visualización.
4. **Riesgo de deriva de entornos:** al trabajar entre un Mac local y un
   entorno de nube, la paridad de versiones debe garantizarse mediante
   ficheros de bloqueo (`requirements.txt`/`uv.lock` para Python y `renv.lock`
   para R) desde el primer momento.

## 4. Recomendaciones (pendientes de aprobación — no ejecutadas)

En cumplimiento del principio de **supervisión humana**, no se ha instalado ni
modificado nada. Cuando se apruebe la fase de aprovisionamiento, el orden
sugerido es:

1. **R** (≥ 4.4) con `renv` para gestión reproducible de paquetes.
2. **Quarto** (≥ 1.5), que integra Python, R y LaTeX en un único flujo de
   publicación.
3. **LaTeX**: en el Mac, la distribución ligera **TinyTeX** (instalable vía
   `quarto install tinytex`) suele ser preferible a MacTeX completo; en la
   nube, `texlive` o TinyTeX según el peso aceptable de la imagen.
4. **Entorno virtual de Python** (`venv` o `uv`) con los paquetes de la
   sección 2.3 fijados por versión.
5. Verificación final: render de un documento Quarto de prueba a PDF (valida
   simultáneamente Quarto, Pandoc, LaTeX y los motores de Python y R).

## 5. Trazabilidad

- Comprobaciones realizadas mediante comandos de solo lectura (`--version`,
  `command -v`, `importlib.util.find_spec`); sin escrituras fuera del
  repositorio.
- Script de diagnóstico reproducible: `scripts/diagnostico_entorno.sh`.
- Este informe queda versionado en Git como evidencia del estado inicial del
  entorno.
