#!/usr/bin/env bash
# =============================================================================
# diagnostico_entorno.sh
# Diagnóstico de solo lectura del entorno de desarrollo para el
# Laboratorio de Investigación Académica Asistido por IA.
#
# - NO instala ni modifica nada.
# - Compatible con macOS y Linux.
# - Genera un informe Markdown con fecha en docs/diagnostico/ (o en el
#   directorio actual si no existe esa ruta).
#
# Uso:  bash scripts/diagnostico_entorno.sh
# =============================================================================
set -u

FECHA="$(date +%Y-%m-%d)"
HORA="$(date +%H:%M:%S)"
if [ -d "docs/diagnostico" ]; then
  INFORME="docs/diagnostico/${FECHA}-diagnostico-local.md"
else
  INFORME="${FECHA}-diagnostico-local.md"
fi

ok="✅"
no="❌"

ver() {
  # Imprime la primera línea de la versión de un comando, o "—" si no existe.
  if command -v "$1" >/dev/null 2>&1; then
    "$@" 2>&1 | head -n 1
  else
    echo "—"
  fi
}

estado() {
  if command -v "$1" >/dev/null 2>&1; then echo "$ok"; else echo "$no"; fi
}

{
  echo "# Diagnóstico del entorno local"
  echo
  echo "**Fecha:** ${FECHA} ${HORA}"
  echo "**Máquina:** $(uname -s) $(uname -r) ($(uname -m))"
  if [ "$(uname -s)" = "Darwin" ] && command -v sw_vers >/dev/null 2>&1; then
    echo "**macOS:** $(sw_vers -productVersion)"
  fi
  echo
  echo "## Herramientas principales"
  echo
  echo "| Herramienta | Estado | Versión |"
  echo "|---|---|---|"
  echo "| Python 3 | $(estado python3) | $(ver python3 --version) |"
  echo "| pip | $(estado pip3) | $(ver pip3 --version) |"
  echo "| R | $(estado R) | $(ver R --version) |"
  echo "| Rscript | $(estado Rscript) | $(ver Rscript --version) |"
  echo "| Git | $(estado git) | $(ver git --version) |"
  echo "| Quarto | $(estado quarto) | $(ver quarto --version) |"
  echo "| pdflatex | $(estado pdflatex) | $(ver pdflatex --version) |"
  echo "| xelatex | $(estado xelatex) | $(ver xelatex --version) |"
  echo "| lualatex | $(estado lualatex) | $(ver lualatex --version) |"
  echo "| tlmgr (TeX Live) | $(estado tlmgr) | $(ver tlmgr --version) |"
  echo "| Pandoc | $(estado pandoc) | $(ver pandoc --version) |"
  echo "| Jupyter | $(estado jupyter) | $(ver jupyter --version) |"
  echo
  echo "## Configuración de Git"
  echo
  if command -v git >/dev/null 2>&1; then
    echo "- user.name: \`$(git config --get user.name || echo 'NO CONFIGURADO')\`"
    echo "- user.email: \`$(git config --get user.email || echo 'NO CONFIGURADO')\`"
  else
    echo "- Git no está instalado."
  fi
  echo
  echo "## Paquetes científicos de Python"
  echo
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PYEOF'
import importlib.util

pkgs = [
    ("numpy", "Cálculo numérico"),
    ("pandas", "Datos tabulares"),
    ("scipy", "Estadística y optimización"),
    ("statsmodels", "Modelos estadísticos"),
    ("sklearn", "Aprendizaje automático"),
    ("matplotlib", "Visualización"),
    ("seaborn", "Visualización estadística"),
    ("nltk", "Procesamiento de lenguaje natural"),
    ("nrclex", "NRC Emotion Lexicon"),
    ("jupyter", "Notebooks"),
    ("bibtexparser", "Gestión bibliográfica"),
]
print("| Paquete | Estado | Versión | Uso |")
print("|---|---|---|---|")
for name, uso in pkgs:
    if importlib.util.find_spec(name):
        try:
            mod = __import__(name)
            v = getattr(mod, "__version__", "instalado")
        except Exception:
            v = "instalado (error al importar)"
        print(f"| {name} | ✅ | {v} | {uso} |")
    else:
        print(f"| {name} | ❌ | — | {uso} |")
PYEOF
  else
    echo "Python 3 no está instalado; no se pueden comprobar paquetes."
  fi
  echo
  echo "## Paquetes de R"
  echo
  if command -v Rscript >/dev/null 2>&1; then
    Rscript --vanilla -e '
pkgs <- c("renv","tidyverse","lme4","brms","quarto","knitr","rmarkdown","syuzhet")
inst <- installed.packages()[, "Version"]
cat("| Paquete | Estado | Versión |\n|---|---|---|\n")
for (p in pkgs) {
  if (p %in% names(inst)) {
    cat(sprintf("| %s | ✅ | %s |\n", p, inst[[p]]))
  } else {
    cat(sprintf("| %s | ❌ | — |\n", p))
  }
}' 2>/dev/null || echo "No se pudieron comprobar los paquetes de R."
  else
    echo "R no está instalado; no se pueden comprobar paquetes."
  fi
  echo
  echo "---"
  echo "_Informe generado por \`scripts/diagnostico_entorno.sh\`"
  echo "(solo lectura: no instala ni modifica nada)._"
} > "$INFORME"

echo "Informe generado: $INFORME"
