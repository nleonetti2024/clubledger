.PHONY: install init demo run test lint eval clean

install:
	pip install -r requirements-dev.txt

init:
	flask --app clubledger init-db

demo: init
	flask --app clubledger seed-demo

run:
	flask --app clubledger run

test:
	pytest

lint:
	ruff check .

eval:
	python scripts/evaluate.py --markdown docs/evaluation-results.md

clean:
	rm -rf instance .pytest_cache .ruff_cache .coverage htmlcov
