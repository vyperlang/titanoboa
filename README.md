# Titanoboa

A [Vyper](https://github.com/vyperlang/vyper) interpreter with pretty tracebacks, forking, debugging features and more! Titanoboa's goal is to provide a modern, advanced and integrated development experience for vyper users.

## Architecture

Titanoboa achieves feature parity with the vyper compiler while providing an interpreted experience. How does it do this? Internally, titanoboa uses vyper as a library to compile source code to bytecode, and then runs the bytecode using [py-evm](https://github.com/ethereum/py-evm), adding instrumenting hooks to provide introspection. The use of `py-evm` means that the entire experience is highly configurable, down to the ability to patch opcodes and precompiles at the EVM level.

## Documentation

Usage and quickstart are [below](#usage-quick-start). For more detailed documentation, please see the [documentation](https://titanoboa.readthedocs.io/en/latest/index.html).

## Installation
```
pip install titanoboa
```

For latest dev version:
```
pip install git+https://github.com/vyperlang/titanoboa
```


If you are installing titanoboa from git alongside brownie, you may have to manually install titanoboa *after* installing brownie

```
pip install brownie
pip install git+https://github.com/vyperlang/titanoboa
```

Sometimes, using [pypy](https://www.pypy.org/download.html) can result in a substantial performance improvement for computation heavy contracts. `Pypy` can usually be used as a drop-in replacement for `CPython`.

To get a performance boost for mainnet forking, install with the `forking-recommended` extra (`pip install "git+https://github.com/vyperlang/titanoboa#egg=titanoboa[forking-recommended]"`, or `pip install titanoboa[forking-recommended]`). This installs `plyvel` to cache RPC results between sessions, and `ujson` which improves json performance.

If you are running titanoboa on a local [Vyper](https://github.com/vyperlang/vyper) project folder, you might need to run `python setup.py install` on your [Vyper](https://github.com/vyperlang/vyper) project if you encounter errors such as `ModuleNotFoundError: No module named 'vyper.version'`

## Background

Titanoboa (/ˌtaɪtənəˈboʊə/;[1] lit. 'titanic boa') is an extinct genus of very large snakes that lived in what is now La Guajira in northeastern Colombia. They could grow up to 12.8 m (42 ft), perhaps even 14.3 m (47 ft) long and reach a body mass of 730–1,135 kg (1,610–2,500 lb). This snake lived during the Middle to Late Paleocene epoch, around 60 to 58 million years ago, following the extinction of all non-avian dinosaurs. Although originally thought to be an apex predator, the discovery of skull bones revealed that it was more than likely specialized in preying on fish. The only known species is Titanoboa cerrejonensis, the largest snake ever discovered,[2] which supplanted the previous record holder, Gigantophis garstini.[3]

## Usage / Quick Start

### Hello, world

```python
import boa
boa.eval("empty(uint256)")
```

### Basic
```vyper
# simple.vy
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
```

```python
>>> import boa

>>> simple = boa.load("examples/simple.vy")
>>> simple.foo()
    8
>>> simple.foo()._vyper_type
    uint256
```


### Passing `__init__`

```python
>>> import boa

>>> erc20 = boa.load("examples/ERC20.vy", 'titanoboa', 'boa', 18, 1)
>>> erc20.name()
    titanoboa
>>> erc20.symbol()
    boa
>>> erc20.balanceOf(erc20.address)
    0
>>> erc20.totalSupply()
    1000000000000000000
```

### As a blueprint

```python
>>> import boa
>>> s = boa.load_partial("examples/ERC20.vy")
>>> blueprint = s.deploy_as_blueprint()
>>> deployer = boa.load("examples/deployer.vy", blueprint)
>>> token = s.at(deployer.create_new_erc20("token", "TKN", 18, 10**18))
>>> token.totalSupply()
>>> 1000000000000000000000000000000000000
```

### Expecting BoaErrors / handling reverts
```python
>>> import boa
>>> erc20 = boa.load("examples/ERC20.vy", "titanoboa", "boa", 18, 0)
>>> with boa.env.prank(boa.env.generate_address()):
...     with boa.reverts():
...         erc20.mint(boa.env.eoa, 100)  # non-minter cannot mint
...
>>> with boa.env.prank(boa.env.generate_address()):
...     # you can be more specific about the failure reason
...     with boa.reverts(rekt="non-minter tried to mint"):
...         erc20.mint(boa.env.eoa, 100)
```

### From within IPython

```python
In [1]: %load_ext boa.ipython
        import boa
        boa.interpret.set_cache_dir()  # cache source compilations across sessions

In [2]: %vyper msg.sender  # evaluate a vyper expression directly
Out[2]: '0x0000000000000000000000000000000000000065'

In [3]: %%vyper
   ...:
   ...: MY_IMMUTABLE: immutable(uint256)
   ...:
   ...: @external
   ...: def __init__(some_number: uint256):
   ...:     MY_IMMUTABLE = some_number * 2
   ...:
   ...: @external
   ...: def foo() -> uint256:
   ...:     return MY_IMMUTABLE
   ...:
Out[3]: <boa.vyper.contract.VyperDeployer at 0x7f3496187190>

In [4]: d = _

In [4]: c = d.deploy(5)

In [5]: c.foo()
Out[5]: 10
```

### Evaluating arbitrary code

```python
>>> erc20 = boa.load("examples/ERC20.vy", 'titanoboa', 'boa', 18, 1)
>>> erc20.balanceOf(erc20.address)
    0
>>> erc20.totalSupply()
    1000000000000000000
>>> erc20.eval("self.totalSupply += 10")  # manually mess with total supply
>>> erc20.totalSupply()
1000000000000000010
>>> erc20.eval("self.totalSupply")  # same result when eval'ed
1000000000000000010
>>> erc20.eval("self.balanceOf[msg.sender] += 101")  # manually mess with balance
>>> erc20.balanceOf(boa.env.eoa)
1000000000000000101
>>> erc20.eval("self.balanceOf[msg.sender]")  # same result when eval'ed
1000000000000000101
```

Note that in `eval()` mode, titanoboa uses slightly different optimization settings, so gas usage may not be the same as using the external interface.

### Forking
Create a fork of mainnet given rpc.
```python
In [1]: import boa; boa.env.fork(url="<rpc server address>")

In [2]: %load_ext boa.ipython

In [3]: %%vyper Test
   ...: interface HasName:
   ...:     def name() -> String[32]: view
   ...:
   ...: @external
   ...: def get_name_of(addr: HasName) -> String[32]:
   ...:     return addr.name()
Out[3]: <boa.vyper.contract.VyperDeployer at 0x7f3496187190>

In [4]: c = Test.deploy()

In [5]: c.get_name_of("0xD533a949740bb3306d119CC777fa900bA034cd52")
Out[5]: 'Curve DAO Token'
```

Cast current deployed addresses to vyper contract
```python
>>> import boa; boa.env.fork(url="<rpc server address>")
>>> c = boa.load_partial("examples/ERC20.vy").at("0xD533a949740bb3306d119CC777fa900bA034cd52")
>>> c.name()
    'Curve DAO Token'
```

### Network Mode
```python
>>> import boa; from boa.network import NetworkEnv
>>> from eth_account import Account
>>> boa.env.set_env(NetworkEnv("<rpc server address>"))
>>> # in a real codebase, always load private keys safely from an encrypted store!
>>> boa.env.add_account(Account(<a private key>))
>>> c = boa.load("examples/ERC20.vy", "My Token", "TKN", 10**18, 10)
>>> c.name()
    'My Token'
```

### Jupyter Integration

You can use Jupyter to execute titanoboa code in network mode from your browser using any wallet, using `boa.integrations.jupyter.BrowserSigner` as a drop-in replacement for `eth_account.Account`. For a full example, please see [this example Jupyter notebook](examples/jupyter_browser_signer.ipynb)


### Basic tests

```bash
$ python -m tests.integration.sim_veYFI
```
