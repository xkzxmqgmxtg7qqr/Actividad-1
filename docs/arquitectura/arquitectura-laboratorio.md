# Arquitectura modular del Laboratorio de Investigación Académica Asistido por IA

**Versión:** 0.1 (propuesta inicial, pendiente de aprobación)
**Fecha:** 2026-10-12

---

## 1. Principios rectores

Toda decisión de diseño se subordina a cuatro principios:

1. **Reproducibilidad científica.** Cualquier resultado debe poder regenerarse
   desde los datos crudos con un único comando. Esto exige: entornos fijados
   por ficheros de bloqueo (`requirements.txt`/`uv.lock` en Python,
   `renv.lock` en R), semillas aleatorias explícitas, datos crudos inmutables
   y documentos ejecutables (Quarto) en lugar de informes escritos a mano.
2. **Validación estadística.** Ningún análisis se da por bueno sin comprobar
   sus supuestos (normalidad, homocedasticidad, independencia…), reportar
   tamaños de efecto e intervalos de confianza además de p-valores, y
   someterse a pruebas automatizadas (tests unitarios de las funciones de
   análisis y tests de regresión sobre resultados conocidos).
3. **Protección de datos.** Los datos sensibles nunca entran en el control de
   versiones: se separan datos de código, se versionan solo metadatos y
   derivados anonimizados, y se documenta el linaje de cada transformación.
4. **Supervisión humana.** Los agentes de IA proponen; el investigador
   dispone. Cada salida de un agente queda marcada como *borrador no
   validado* hasta que una persona la revisa y firma. El sistema registra
   quién validó qué y cuándo.

## 2. Visión por capas

```
┌─────────────────────────────────────────────────────────────┐
│  CAPA 5 · PUBLICACIÓN      Quarto + LaTeX → PDF/HTML/DOCX   │
├─────────────────────────────────────────────────────────────┤
│  CAPA 4 · AGENTES          estadístico · cualitativo ·      │
│  (asistencia IA)           simulación · bibliográfico ·     │
│                            redactor · revisor               │
├─────────────────────────────────────────────────────────────┤
│  CAPA 3 · ANÁLISIS         src/python (pandas, statsmodels, │
│                            sklearn, NRCLex) · src/r (tidy-  │
│                            verse, lme4, syuzhet)            │
├─────────────────────────────────────────────────────────────┤
│  CAPA 2 · DATOS            data/raw (inmutable) → data/     │
│                            processed · metadatos y linaje   │
├─────────────────────────────────────────────────────────────┤
│  CAPA 1 · INFRAESTRUCTURA  Git · entornos bloqueados (venv/ │
│                            renv) · orquestación (Makefile)  │
└─────────────────────────────────────────────────────────────┘
```

Cada capa solo depende de las inferiores. Los agentes (capa 4) nunca acceden a
los datos crudos directamente: invocan las funciones validadas de la capa 3,
lo que garantiza que todo cálculo pase por código testeado y trazable.

## 3. Estructura de directorios propuesta

```
laboratorio/
├── README.md
├── Makefile                  # Orquestación: make datos, make analisis, make informe
├── environment/
│   ├── requirements.txt      # Python fijado por versión
│   ├── renv.lock             # R fijado por versión
│   └── versions.md           # Versiones de Quarto, LaTeX, SO
├── data/
│   ├── raw/                  # Datos crudos: INMUTABLES, fuera de Git (.gitignore)
│   ├── processed/            # Derivados regenerables; fuera de Git
│   └── metadata/             # Diccionarios de datos, linaje, checksums (SÍ en Git)
├── src/
│   ├── python/
│   │   ├── estadistica/      # Pruebas, modelos, tamaños de efecto
│   │   ├── cualitativo/      # NRC Emotion Lexicon (NRCLex), minería de texto
│   │   ├── simulacion/       # Monte Carlo, modelos matemáticos
│   │   └── bibliografia/     # Búsqueda y cribado automatizado de literatura
│   └── r/
│       ├── estadistica/      # tidyverse, lme4/brms, análisis inferencial
│       └── cualitativo/      # syuzhet (incluye léxico NRC en R)
├── agents/
│   ├── README.md             # Protocolo de supervisión humana
│   ├── estadistico/          # Prompts, herramientas y límites de cada agente
│   ├── cualitativo/
│   ├── simulador/
│   ├── bibliografico/
│   └── redactor/
├── analysis/                 # Documentos Quarto ejecutables (.qmd) por estudio
│   └── plantillas/
├── reports/                  # Salidas renderizadas (PDF/HTML); regenerables
├── bibliography/
│   ├── referencias.bib
│   └── estilos/              # CSL (APA 7, etc.)
├── tests/
│   ├── python/               # pytest
│   └── r/                    # testthat
└── docs/
    ├── diagnostico/          # Informes de estado del entorno
    ├── arquitectura/         # Este documento y decisiones (ADR)
    └── validaciones/         # Registro de revisiones humanas firmadas
```

## 4. Módulos funcionales

### M1 — Análisis estadístico (Python + R)
- Python: `pandas`, `scipy`, `statsmodels`, `scikit-learn`.
- R: `tidyverse`, `lme4`/`brms` para modelos mixtos y bayesianos.
- Contrato del módulo: cada función de análisis devuelve, junto al resultado,
  un objeto de *diagnóstico* (supuestos comprobados, tamaño de efecto, IC) que
  los informes Quarto muestran obligatoriamente.

### M2 — Análisis cualitativo y NRC Emotion Lexicon
- Vía Python: `NRCLex` + `nltk` (tokenización, lematización).
- Vía R: `syuzhet::get_nrc_sentiment()` como validación cruzada independiente.
- Salidas: matrices documento × emoción (8 emociones + 2 polaridades de NRC),
  con visualizaciones y exportación trazable a `data/processed/`.
- Nota metodológica: el léxico NRC fue construido para inglés; para corpus en
  español se usará su traducción oficial documentando la versión exacta.

### M3 — Simulación matemática y modelos estadísticos
- Monte Carlo, remuestreo (bootstrap), análisis de potencia, modelos
  dinámicos. Semilla aleatoria obligatoria y registrada en cada ejecución.

### M4 — Revisión bibliográfica automatizada
- Búsqueda vía APIs abiertas (Crossref, OpenAlex, Semantic Scholar),
  deduplicación, cribado asistido por IA con decisión final humana
  (flujo PRISMA), y exportación a `bibliography/referencias.bib`.

### M5 — Ecosistema de agentes (construcción progresiva)
Orden de incorporación propuesto, de menor a mayor riesgo:
1. **Agente bibliográfico** (bajo riesgo: sus errores se detectan leyendo).
2. **Agente redactor** (redacta secciones a partir de resultados ya validados).
3. **Agente estadístico** (propone y ejecuta análisis usando solo la capa 3).
4. **Agente cualitativo** (codificación y emociones, con doble codificación
   humana en una muestra para medir concordancia, p. ej. kappa de Cohen).
5. **Agente simulador** y **agente revisor** (crítica metodológica interna).

Reglas comunes: cada agente tiene herramientas delimitadas, no puede escribir
en `data/raw/`, y toda salida entra en `docs/validaciones/` como pendiente
hasta su aprobación humana.

### M6 — Publicación reproducible (Quarto + LaTeX)
- Un `.qmd` por estudio que entrelaza texto, código Python/R y resultados.
- Plantillas LaTeX para formato de revista/tesis; bibliografía desde
  `referencias.bib` con estilo CSL (APA 7 por defecto).
- `make informe` regenera el PDF completo desde los datos crudos.

## 5. Trazabilidad de datos, procedimientos y resultados

| Elemento | Mecanismo |
|---|---|
| Datos crudos | Checksums SHA-256 registrados en `data/metadata/`; directorio inmutable |
| Transformaciones | Solo mediante scripts versionados; linaje documentado (origen → script → derivado) |
| Entornos | Ficheros de bloqueo versionados; versiones de herramientas en `environment/versions.md` |
| Análisis | Documentos Quarto ejecutables: el informe ES el procedimiento |
| Aleatoriedad | Semillas explícitas registradas en cada salida |
| Decisiones | Registros de decisión de arquitectura (ADR) en `docs/arquitectura/` |
| Validación humana | Registro firmado en `docs/validaciones/` por cada resultado aprobado |

## 6. Hoja de ruta de implantación

| Fase | Contenido | Criterio de salida |
|---|---|---|
| 0. Diagnóstico | Estado del entorno (este informe) | ✅ Completada |
| 1. Aprovisionamiento | Instalar R, Quarto, TinyTeX, paquetes Python/R bloqueados | `quarto render` de un documento de prueba con chunks Python y R genera PDF |
| 2. Esqueleto | Estructura de directorios, Makefile, tests mínimos, .gitignore de datos | `make informe` funciona de extremo a extremo con datos de ejemplo |
| 3. Módulos M1–M3 | Estadística, cualitativo (NRC), simulación | Tests pasan; análisis de ejemplo validado por humano |
| 4. Módulo M4 | Pipeline bibliográfico | Revisión piloto PRISMA completada |
| 5. Módulo M5 | Agentes, incorporados uno a uno | Protocolo de supervisión en uso real |

Cada fase requiere aprobación explícita del investigador antes de ejecutarse
(principio de supervisión humana): ninguna instalación de la fase 1 se ha
realizado todavía.
