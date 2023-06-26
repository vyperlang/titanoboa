#!/usr/bin/env bash

rm -r titanoboa.egg-info/ dist/

# requires: `pip install build`
python -m build

# requires: `pip install twine`
# requires twine being configured, e.g. with a ~/.pypirc file
twine upload dist/*
