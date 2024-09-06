# Contributing

Thank you for wanting to contribute! This project reviews PRs that have an associated issue with
them. If you have not make an issue for your PR, please make one first.

Issues, feedback, and sharing that you're using Titanoboa and Vyper on social media is always welcome!

# Table of Contents

- [Contributing](#contributing)
- [Table of Contents](#table-of-contents)
- [Setup](#setup)
  - [Requirements](#requirements)
  - [Installing for local development](#installing-for-local-development)
  - [Running Tests](#running-tests)
    - [Unit tests](#unit-tests)
    - [Integration tests](#integration-tests)
- [Thank you!](#thank-you)

# Setup

## Requirements

You must have the following installed to proceed with contributing to this project.

- [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
  - You'll know you did it right if you can run `git --version` and you see a response like `git version x.x.x`
- [python](https://www.python.org/downloads/)
  - You'll know you did it right if you can run `python --version` and you see a response like `Python x.x.x`
- [pip](https://pip.pypa.io/en/stable/installation/)
  - You'll know you did it right if you can run `pip --version` and you see a response like `pip x.x.x`
- Linux and/or MacOS
  - This project is not tested on Windows, so it is recommended to use a Linux or MacOS machine, or use a tool like [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) for windows users.

## Installing for local development

Follow the steps to clone the repo for you to make changes to this project.

1. Clone the repo

```bash
git clone https://github.com/vyperlang/titanoboa
cd titanoboa
```

2. Setup virtual environment and install dependencies

*You can learn more about [activating and deactivating virtual environments here.](https://docs.python.org/3/library/venv.html)*

```bash
python -m venv venv
source venv/bin/activate
# Install dev requirements
pip install -r dev-requirements.txt
# Install prod requirements (in the pyproject.tom)
pip install . 
```

*Note: When you delete your terminal/shell, you will need to reactivate this virtual environment again each time. To exit this python virtual environment, type `deactivate`*

3. Create a new branch

```bash
git checkout -b <branch_name>
```

And start making your changes! Once you're done, you can commit your changes and push them to your forked repo.

```bash
git add .
git commit -m 'your commit message'
git push <your_forked_github>
```

## Running Tests

Once you have your environment setup, you can run the tests to make sure everything is working as expected. You'll need to have your virtual environment activated to run the tests.

### Unit tests

Run the following:

```bash
pytest tests/unitary -x
```

This will skip the integration tests, which need extra "stuff".

### Integration tests

Once you have setup your virtual environment, to run integration tests, you'll need to add environment variables.

You can see the `.env.unsafe.example` for environment variables you'll want to use.

```bash
MAINNET_ENDPOINT=<eth_mainnet_rpc_url>
SEPOLIA_ENDPOINT=<sepolia_rpc_url>
SEPOLIA_PKEY=<sepolia_private_key> # DO NOT USE A KEY ASSSOCIATED WITH REAL FUNDS
```

You can optionally copy `.env.unsafe.example` and create a new file called `.env.unsafe` file and run the following command to load the environment variables.

```bash
source .env.unsafe
```

Then, you can just run:

```bash
pytest tests/integration/ -x
```


# Thank you!

Thank you for wanting to participate in titanoboa!
