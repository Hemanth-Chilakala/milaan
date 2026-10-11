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
deck_stage="$(mktemp -d /tmp/milaan-deck.XXXXXX)"
trap 'rm -rf "$deck_stage"' EXIT
npx --yes @marp-team/marp-cli@4.5.1 docs/deck/milaan_deck.md --theme-set docs/deck/theme.css --html --allow-local-files --pdf -o "$deck_stage/milaan_deck.pdf"
npx --yes @marp-team/marp-cli@4.5.1 docs/deck/milaan_deck.md --theme-set docs/deck/theme.css --html --allow-local-files --pptx -o "$deck_stage/milaan_deck.pptx"
mkdir -p "$deck_stage/cards"
npx --yes @marp-team/marp-cli@4.5.1 docs/deck/milaan_deck.md --theme-set docs/deck/theme.css --html --allow-local-files --images png --image-scale 3 -o "$deck_stage/cards/slide.png"
.venv/bin/python - "$deck_stage" <<'PY'
from pathlib import Path
import shutil, sys
stage=Path(sys.argv[1]); target=Path('docs/deck')
files=[(stage/'milaan_deck.pdf',target/'milaan_deck.pdf'),(stage/'milaan_deck.pptx',target/'milaan_deck.pptx')]
for path in (stage/'cards').glob('slide.*.png'):
    files.append((path,target/'cards'/f'{int(path.stem.split(".")[-1])}.png'))
required=sum(max(0,source.stat().st_size-(destination.stat().st_size if destination.exists() else 0)) for source,destination in files)
if shutil.disk_usage(target).free-required-max(source.stat().st_size for source,_ in files)<6_000_000_000:
    raise RuntimeError('Deck exports would breach the 6 GB workspace reserve')
for source,destination in files:
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,destination)
PY
