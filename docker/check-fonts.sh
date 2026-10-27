#!/bin/bash
# ============================================================
# Font coverage gate for the OverBranch TeX base image.
# ============================================================
# Runs at build time. Fails the build if any REQUIRED family is missing (a
# renamed/dropped Debian package, or a broken TeX Live font tree). MS core
# fonts and exotic scripts are reported but not fatal: the compiler's font
# preflight substitutes a metric-compatible family for a missing MS font, so
# their absence (e.g. a SourceForge outage during the build) is survivable.
set -u

families() { fc-list : family | tr ',' '\n' | sed 's/^ *//; s/ *$//' | sort -u; }
ALL="$(families)"
have() { printf '%s\n' "$ALL" | grep -qiF "$1"; }

# Required: always available from Debian + TeX Live, metric-compatible with the
# fonts real Overleaf/Prism documents select, plus the TeX defaults.
REQUIRED=(
  "Carlito" "Caladea" "Arimo" "Tinos" "Cousine"
  "Liberation Serif" "Liberation Sans" "Liberation Mono"
  "DejaVu Serif" "DejaVu Sans" "DejaVu Sans Mono"
  "TeX Gyre Termes" "TeX Gyre Heros" "TeX Gyre Pagella" "TeX Gyre Bonum"
  "TeX Gyre Schola" "TeX Gyre Cursor"
  "Latin Modern Roman" "Latin Modern Sans" "Latin Modern Mono"
  "Noto Serif" "Noto Sans" "Noto Sans Mono" "Noto Sans CJK" "Noto Serif CJK"
  "EB Garamond" "Fira Sans" "Fira Math" "Source Serif 4" "Source Sans 3"
  "Roboto" "Lato" "Inconsolata"
  "IBM Plex Serif" "IBM Plex Sans" "IBM Plex Mono"
  "STIX Two Text" "STIX Two Math"
  "Rachana" "Meera" "Amiri"
)

# Nice to have: reported only. MS originals are covered by substitution.
OPTIONAL=(
  "Times New Roman" "Arial" "Courier New" "Georgia" "Verdana"
  "Trebuchet MS" "Comic Sans MS" "Impact"
  "Hack" "Fira Code" "JetBrains Mono" "Cantarell" "Symbola"
  "IPAGothic" "IPAMincho" "NanumGothic" "WenQuanYi Micro Hei"
  "AR PL UMing CN" "Scheherazade" "Charis SIL" "Gentium" "Padauk"
  "Lohit Malayalam" "FreeSerif" "FreeSans" "Linux Libertine O"
)

miss=0
echo "============================================================"
echo "Required font coverage"
echo "============================================================"
for f in "${REQUIRED[@]}"; do
  if have "$f"; then echo "  ok   $f"; else echo "  MISS $f"; miss=$((miss+1)); fi
done

echo ""
echo "============================================================"
echo "Optional font coverage (reported only)"
echo "============================================================"
for f in "${OPTIONAL[@]}"; do
  if have "$f"; then echo "  ok   $f"; else echo "  --   $f (absent; substitution applies)"; fi
done

echo ""
echo "Total families installed: $(printf '%s\n' "$ALL" | grep -c .)"
if [ "$miss" -gt 0 ]; then
  echo "FONT GATE FAILED: $miss required families missing." >&2
  exit 1
fi
echo "FONT GATE PASSED."
