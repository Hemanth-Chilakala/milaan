PYTHON := .venv/bin/python
ROWS ?= 1000000
DATA ?= data/$(ROWS)
BENCH_ARGS ?=

.PHONY: setup data load recon explain score bench demo test lint app
setup:
	$(PYTHON) -m milaan.pipeline setup
data:
	$(PYTHON) -m scripts.ensure_data --rows $(ROWS) --out $(DATA)
load:
	$(PYTHON) -m milaan.pipeline load --data $(DATA)
recon:
	$(PYTHON) -m milaan.pipeline recon
explain:
	$(PYTHON) -m milaan.explain
score:
	$(PYTHON) -m milaan.pipeline score
bench:
	$(PYTHON) -m scripts.benchmark $(BENCH_ARGS)
demo: setup data load recon explain app
test:
	$(PYTHON) -m pytest -m 'not db'
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
app:
	.venv/bin/streamlit run app/Home.py --server.address 0.0.0.0 --server.port 8501
