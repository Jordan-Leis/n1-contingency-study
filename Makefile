# `make reproduce` rebuilds every result, figure and report from a clean clone.
PY = PYTHONPATH=src uv run --frozen python

.PHONY: reproduce study report test check quick clean

reproduce: study report test check
	@echo "reproduce: OK"

study:
	uv sync --frozen
	$(PY) -m n1study.run

# Everything except the hosting sweep (about a minute); reuses the committed sweep results.
quick:
	uv sync --frozen
	$(PY) -m n1study.run --skip-hosting
	$(MAKE) report test check

report:
	$(PY) -m n1study.report

test:
	uv run --frozen pytest -q

check:
	$(PY) -m n1study.check_numbers

clean:
	rm -rf results/* figures/* memo/*
