#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export CHROME_PATH
CHROME_PATH="$(.venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
PY
)"
npx --yes @marp-team/marp-cli@4.5.1 docs/deck/milaan_deck.md --theme-set docs/deck/theme.css --html --allow-local-files --pdf -o docs/deck/milaan_deck.pdf
npx --yes @marp-team/marp-cli@4.5.1 docs/deck/milaan_deck.md --theme-set docs/deck/theme.css --html --allow-local-files --pptx -o docs/deck/milaan_deck.pptx
mkdir -p docs/deck/cards
npx --yes @marp-team/marp-cli@4.5.1 docs/deck/milaan_deck.md --theme-set docs/deck/theme.css --html --allow-local-files --images png --image-scale 3 -o docs/deck/cards/slide.png
.venv/bin/python - <<'PY'
from pathlib import Path
folder=Path('docs/deck/cards')
for path in folder.glob('slide.*.png'):
    path.rename(folder/f'{int(path.stem.split(".")[-1])}.png')
PY
