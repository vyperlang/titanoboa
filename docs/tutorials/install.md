<h1><strong>Installing Titanoboa</strong></h1>

Titanoboa requires Python 3.9 or later to function properly.

## Install Using Moccasin

!!!moccasin
    [Moccasin](https://github.com/cyfrin/moccasin) is a CLI tool that wraps Boa, providing a smoother and more feature-rich development experience. If you are accustomed to frameworks like Foundry, you’ll likely want to install Moccasin. Refer to the [Moccasin documentation](https://cyfrin.github.io/moccasin/) for more details.

If you have installed Moccasin and used `mox init` to set up your project, Titanoboa is already included as a dependency.

---

## Install Using pip, poetry, or uv

Titanoboa is available on PyPI, so you can install it using pip, poetry, or uv. The latest release can be installed with:

=== "pip"

    ```console
    pip install titanoboa
    ```

=== "poetry"

    ```console
    poetry add titanoboa
    ```

=== "uv"

    ```console
    uv add titanoboa
    ```

---

## Install Latest Development Version

To install the latest development version, use:

=== "pip"

    ```console
    pip install git+https://github.com/vyperlang/titanoboa.git@<commit-hash>
    ```

=== "poetry"

    ```console
    poetry add git+https://github.com/vyperlang/titanoboa.git@<commit-hash>
    ```

=== "uv"

    ```console
    uv add https://github.com/vyperlang/titanoboa.git --rev <commit-hash>
    ```