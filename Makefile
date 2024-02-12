.PHONY: all lint build

all: lint build

lint:
	pre-commit run --all-files
	mypy --install-types --non-interactive --follow-imports=silent --ignore-missing-imports --implicit-optional -p boa

build:
	pip install .

# run tests without forked tests (which require access to a node)
test:
	pytest tests/ --ignore=tests/integration/fork/ --ignore=tests/integration/network/

# note: for pypi upload,
# rm -r titanoboa.egg-info/ dist/
# python -m build
# twine upload dist/*
