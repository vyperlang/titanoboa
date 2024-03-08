.PHONY: all lint build

all: lint build

lint:
	pre-commit run --all-files

build:
	pip install .

# run tests without forked tests (which require access to a node)
test:
	pytest tests/ --ignore=tests/integration/fork/ --ignore=tests/integration/network/

clean:
	@find . -name '*.pyc' -exec rm -f {} +
	@find . -name '*.pyo' -exec rm -f {} +
	@find . -name '*~' -exec rm -f {} +
	@find . -name '__pycache__' -exec rmdir {} +

# note: for pypi upload, see pypi-publish.sh
