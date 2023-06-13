.PHONY: all lint build

all: lint build

lint:
	black -C -t py310 boa/ tests/
	isort boa/ tests/
	flake8 boa/ tests/
	mypy --install-types --non-interactive --follow-imports=silent --ignore-missing-imports --implicit-optional -p boa

build:
	pip install .

test:
	pytest -n0 tests/ --ignore=tests/unitary/fork/ --ignore=tests/unitary/network/

# note: for pypi upload,
# rm -r titanoboa.egg-info/ dist/
# python -m build
# twine upload dist/*
