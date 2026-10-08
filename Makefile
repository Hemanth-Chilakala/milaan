PYTHON := .venv/bin/python
ROWS ?= 1000000
DATA ?= data/$(ROWS)

.PHONY: setup data load test lint app
setup:
	$(PYTHON) -m milaan.pipeline setup
data:
	$(PYTHON) -m generator.generate --seed 42 --rows $(ROWS) --days 30 --out $(DATA)
load:
	$(PYTHON) -m milaan.pipeline load --data $(DATA)
test:
	$(PYTHON) -m pytest -m 'not db'
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
app:
	.venv/bin/streamlit run app/Home.py --server.address 0.0.0.0 --server.port 8501
