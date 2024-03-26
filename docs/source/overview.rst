Overview
========

Titanoboa (also called ``boa``) is a `Vyper <https://vyper.readthedocs.io/>`_ interpreter designed to provide a modern, advanced and integrated development experience with:

* pretty tracebacks
* forking
* debugging features
* opcode patching
* *and more ...*

``titanoboa`` is not just a framework, but a library that can be used in any Python environment. It is designed to be used in jupyter notebooks, Python scripts, or tests (any Python testing framework is compatible) to provide a seamless experience and as little context-switching overhead as possible between Python and Vyper.

Installation
------------

``titanoboa`` is available to install from `PyPI <https://pypi.org/project/titanoboa/>`_.

.. code-block:: bash

   pip install titanoboa

Alternatively, the latest in-development version of ``titanoboa`` can be installed from `GitHub <https://github.com/vyperlang/titanoboa>`_.

.. code-block:: bash

   pip install git+https://github.com/vyperlang/titanoboa#egg=titanoboa

If you are using `Poetry <https://python-poetry.org/>`_ as a dependency manager:

.. code-block:: bash

   poetry add titanoboa

If you want to use a specific version you can customize the dependency in your `pyproject.toml` file like this:

.. code-block:: toml

   [tool.poetry.dependencies]
   titanoboa = { git = "https://github.com/vyperlang/titanoboa.git", rev = <commit hash> }
