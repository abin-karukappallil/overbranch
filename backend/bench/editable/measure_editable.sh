#!/bin/bash
# Baseline: source vs editable-output page counts (deterministic CLI, no LLM)
S=$1; shift
cd /home/abin/overbranch/backend
for pdf in "$@"; do
  name=$(basename "$pdf" .pdf | tr ' ' '_' | cut -c1-40)
  out=$S/editable_baseline/$name
  mkdir -p "$out"
  timeout 900 .venv/bin/python -m pdf2latex.editable "$pdf" --out "$out" --gates --max-pages 120 > "$out/gates.txt" 2>"$out/err.txt"
  src=$(.venv/bin/python -c "import fitz,sys;print(fitz.open(sys.argv[1]).page_count)" "$pdf")
  dst=$(.venv/bin/python -c "import fitz,sys;print(fitz.open(sys.argv[1]).page_count)" "$out/main.pdf" 2>/dev/null)
  echo "$name src=$src out=$dst failed=$(grep -o '"failed": \[[^]]*\]' $out/gates.txt | tr -d '\n')"
done
