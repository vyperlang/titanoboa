# Titanoboa

An experimental [Vyper](https://github.com/vyperlang/vyper) interpreter

## Installation
```
pip install git+https://github.com/vyperlang/titanoboa
```

If you are installing titanoboa alongside brownie, you must manually install titanoboa *after* installing brownie

```
pip install brownie
pip install git+https://github.com/vyperlang/titanoboa
```

## Background

Titanoboa (/tiˌtɑːnoʊˈboʊə/) is an extinct genus of very large snakes that lived in what is now La Guajira in northeastern Colombia. They could grow up to 12.8 m (42 ft), perhaps even 14.3 m (47 ft) long and reach a weight of 1,135 kg (2,500 lb). This snake lived during the Middle to Late Paleocene epoch, around 60 to 58 million years ago following the extinction of the dinosaurs. Although originally thought to be an apex predator, the discovery of skull bones revealed that it was more than likely specialized in preying on fish. The only known species is Titanoboa cerrejonensis, the largest snake ever discovered,[1] which supplanted the previous record holder, Gigantophis garstini.[2]

## Usage

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

### As a factory

```python
>>> import boa

>>> factory = boa.load("examples/ERC20.vy", as_factory=True)
>>> deployer = boa.load("examples/deployer.vy", factory.address)
```

### From within IPython

```python
In [1]: %load_ext boa.ipython

In [2]: %%vyper
   ...:
   ...: @external
   ...: def foo() -> uint256:
   ...:     return 1
   ...:
Out[2]: <boa.contract.VyperContract at 0x7fb254392cb0>

In [3]: _.foo()
Out[3]: 1
```


basic tests:
```bash
$ python -m tests.sim_veYFI
```
