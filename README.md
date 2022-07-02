# Titanoboa

An experimental [Vyper](https://github.com/vyperlang/vyper) interpreter

## Background

Titanoboa (/tiˌtɑːnoʊˈboʊə/) is an extinct genus of very large snakes that lived in what is now La Guajira in northeastern Colombia. They could grow up to 12.8 m (42 ft), perhaps even 14.3 m (47 ft) long and reach a weight of 1,135 kg (2,500 lb). This snake lived during the Middle to Late Paleocene epoch, around 60 to 58 million years ago following the extinction of the dinosaurs. Although originally thought to be an apex predator, the discovery of skull bones revealed that it was more than likely specialized in preying on fish. The only known species is Titanoboa cerrejonensis, the largest snake ever discovered,[1] which supplanted the previous record holder, Gigantophis garstini.[2]

## Installation
```
pip install git+https://github.com/vyperlang/titanoboa
```

## Usage

```vyper
# simple.vy
@external
def foo() -> uint256:
    x: uint256 = 1
    return x + 7
```

```python
>>> import boa

>>> simple = boa.load("simple.vy")
>>> simple.foo()
    8
>>> simple.foo()._vyper_type
    uint256
```

basic tests:
```bash
$ python -m tests.sim_veYFI
```
