# Overview

Titanoboa (also called `boa`) is a [Vyper](https://vyper.readthedocs.io/) interpreter designed to provide a modern, advanced and integrated development experience with:

- [pretty tracebacks](api/common_classes/call_trace.md)
- [forking](api/testing.md#fork)
- [debugging features](tutorials/debug.md)
- [opcode patching](api/pyevm/patch_opcode.md)
- [pytest integration](tutorials/pytest.md#titanoboa-plugin)
- [jupyter integration](api/env/browser_env.md)
- [iPython integration](guides/scripting/ipython_vyper_cells.md)
- [native Python import syntax](guides/scripting/native_import_syntax.md)
- [legacy Vyper support](api/vvm_deployer/overview.md)
- *and more ...*

`titanoboa` is not just a framework, but a library that can be used in any Python environment.
It is designed to be used in [jupyter notebooks](guides/scripting/ipython_vyper_cells.md), [Python scripts](guides/scripting/native_import_syntax.md), or [tests](tutorials/pytest.md) (any Python testing framework is compatible) to provide a seamless experience and as little context-switching overhead as possible between Python and Vyper.
