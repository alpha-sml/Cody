setup:
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt

run:
	PYTHONPATH=. ./venv/bin/python -m src.harness.main $(ARGS)

test:
	PYTHONPATH=. ./venv/bin/pytest tests/

clean:
	rm -rf venv/
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type d -name .pytest_cache -exec rm -r {} +
