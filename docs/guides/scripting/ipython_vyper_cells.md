# IPython and Vyper cells

Load Titanoboa's IPython extension after installing the package:

```python
%load_ext boa.ipython
import boa
```

The extension registers four magics:

- `%vyper <expression>` evaluates one Vyper expression through `boa.eval`.
- `%eval <expression>` is an alias for `%vyper`.
- `%%vyper [Name]` compiles the cell and returns a deployer. When `Name` is supplied, the deployer is also bound in the notebook namespace.
- `%%contract [Name]` compiles and deploys the cell. When `Name` is supplied, the contract is bound in the notebook namespace.

```python
In [1]: import boa; boa.fork("<rpc server address>")

In [2]: %load_ext boa.ipython

In [3]: %%vyper Test
   ...: interface HasName:
   ...:     def name() -> String[32]: view
   ...:
   ...: @external
   ...: def get_name_of(addr: HasName) -> String[32]:
   ...:     return staticcall addr.name()

In [4]: c = Test.deploy()

In [5]: c.get_name_of("0xD533a949740bb3306d119CC777fa900bA034cd52")
Out[5]: 'Curve DAO Token'
```

`boa.fork()` creates a local py-evm fork. For wallet-backed network transactions in JupyterLab or Google Colab, use [`boa.set_browser_env()`](../../api/env/singleton.md#set_browser_env) instead. It relies on the Titanoboa Jupyter server extension and browser-side JavaScript, so it is not a generic terminal-IPython wallet workflow. It changes the singleton environment; use it in a `with` block if the previous environment must be restored.

### JupyterLab
The Vyper team provides the website [try.vyperlang.org](https://try.vyperlang.org) where you can try Vyper code directly in your browser.
Titanoboa exposes its callback handler as a Python Jupyter server extension, so no separate JupyterLab frontend-extension enable command is required. Install `titanoboa`, start JupyterLab, and load `boa.ipython` in the notebook.

### Google Colab
Another convenient way to run Vyper code in the browser is by using [Google Colab](https://colab.research.google.com/).
Install the Colab extra, then load the extension:

```python
!pip install "titanoboa[colab]"
%load_ext boa.ipython
```
