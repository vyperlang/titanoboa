
lint:
	black -C -t py310 boa/ tests/
	isort boa/ tests/
	flake8 boa/ tests/
	mypy --install-types --non-interactive --follow-imports=silent --ignore-missing-imports --implicit-optional -p boa

# note: for pypi upload,
# rm -r titanoboa.egg-info/ dist/
# python -m build
# twine upload dist/*
