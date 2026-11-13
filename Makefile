.PHONY: install test scenarios evaluate learning trace all

install:
	python -m pip install -r requirements.txt

test:
	python -m pytest -q

scenarios:
	python scripts/run_scenarios.py

evaluate:
	python scripts/evaluate.py

learning:
	python scripts/learning_experiment.py

trace:
	python scripts/trace_demo.py

all: test scenarios evaluate learning trace
