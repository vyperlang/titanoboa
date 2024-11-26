## ipython Vyper Cells

Titanoboa supports iPython Vyper "magic" cells with the `%%vyper` magic command.
To enable the cell magic, add a `%load_ext boa.ipython` cell after installing boa.

This means that you can write Vyper code in an iPython/Jupyter Notebook environment and execute it as if it was a Python cell (the contract will be compiled instead, and a `ContractFactory` will be returned).

You can use Jupyter to execute Titanoboa code in network mode from your browser using any wallet - using your wallet to sign transactions and call the RPC.
To set up the environment, simply run [`boa.set_browser_env`](../../api/env/singleton.md#set_browser_env).
For a full example, please see [this example Jupyter notebook](https://colab.research.google.com/drive/1d79XDUBXNhxNX67KSlNnWADyB0_ef7tN).

!!!python "iPython"
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

### JupyterLab
The Vyper team provides the website [try.vyperlang.org](https://try.vyperlang.org) where you can try Vyper code directly in your browser.
To run your own instance of JupyterLab, please check the [try.vyperlang.org repository](https://github.com/vyperlang/try.vyperlang.org/blob/93751db5b/README.md#running-locally).

### Google Colab
Another convenient way to run Vyper code in the browser is by using [Google Colab](https://colab.research.google.com/).
This is a free service that allows you to run notebooks in the cloud without any setup.
