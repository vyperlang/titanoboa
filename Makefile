
lint:
	black -C -t py39 boa/
	flake8 boa/
	isort boa/
	mypy boa/
