# Titanoboa

An experimental [Vyper](https://github.com/vyperlang/vyper) interpreter

## Installation
```
pip install git+https://github.com/vyperlang/titanoboa
```

If you are installing titanoboa from git alongside brownie, you may have to manually install titanoboa *after* installing brownie

```
pip install brownie
pip install git+https://github.com/vyperlang/titanoboa
```

## Background

Titanoboa (/tiˌtɑːnoʊˈboʊə/) is an extinct genus of very large snakes that lived in what is now La Guajira in northeastern Colombia. They could grow up to 12.8 m (42 ft), perhaps even 14.3 m (47 ft) long and reach a weight of 1,135 kg (2,500 lb). This snake lived during the Middle to Late Paleocene epoch, around 60 to 58 million years ago following the extinction of the dinosaurs. Although originally thought to be an apex predator, the discovery of skull bones revealed that it was more than likely specialized in preying on fish. The only known species is Titanoboa cerrejonensis, the largest snake ever discovered,[1] which supplanted the previous record holder, Gigantophis garstini.[2]

## Usage

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

### Expecting BoaErrors
```python
>>> import boa
>>> erc20 = boa.load("examples/ERC20.vy", "titanoboa", "boa", 18, 0)
>>> with boa.env.prank(boa.env.generate_address()):
...     with boa.reverts():
...         erc20.mint(boa.env.eoa, 100)  # non-minter cannot mint
...
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
Out[3]: <boa.contract.VyperDeployer at 0x7f3496187190>

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

basic tests:
```bash
$ python -m tests.sim_veYFI
```
