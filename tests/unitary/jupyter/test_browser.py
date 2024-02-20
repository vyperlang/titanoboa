import json
import re
from asyncio import get_event_loop
from multiprocessing.shared_memory import SharedMemory
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

import boa


@pytest.fixture()
def mocked_token(token):
    with mock.patch(
        "boa.integrations.jupyter.browser._generate_token"
    ) as generate_token:
        generate_token.return_value = token
        yield token


@pytest.fixture()
def env(browser, account, mock_fork, mock_callback):
    mock_callback("eth_requestAccounts", [account.address])
    boa.set_browser_env(account)
    return boa.env


@pytest.fixture(autouse=True)
def reset_env():  # Do not pollute other tests
    yield
    boa.reset_env()


def find_response(mock_calls, func_to_body_dict):
    """
    Find the response in the mock calls to the display function.
    :param mock_calls: The calls to the display function.
    :param func_to_body_dict: A dictionary that maps function names to their responses.
        The keys represent either an RPC function or a JS function.
    :return: The response to the last call to the display function.
    """
    assert mock_calls
    (javascript,) = [call for call in mock_calls if call.args][-1].args
    js_func, js_args = re.match(
        r"window._titanoboa.([a-zA-Z0-9_]+)\(([^)]*)\)", javascript.data
    ).groups()
    if js_func not in ("rpc", "multiRpc"):
        # JS function
        return func_to_body_dict[js_func]

    first_arg = json.loads(f"[{js_args}]")[1]  # ignore the token
    if js_func == "rpc":
        # Single RPC call
        return func_to_body_dict[first_arg]

    # Multi RPC call, gather all the responses or error if any of them is an error
    responses = [func_to_body_dict[name] for name, _ in first_arg]
    error = next((r["error"] for r in responses if r.get("error")), None)
    if error:
        return {"error": error}
    return {"data": [r["data"] for r in responses]}


@pytest.fixture()
def mock_callback(mocked_token, browser, display_mock):
    """Returns a function that allows mocking the result of the frontend callback."""

    with mock.patch("boa.integrations.jupyter.browser.get_event_loop") as mock_get_loop:
        io_loop = mock_get_loop.return_value
        io_loop.time.return_value = 0
        func_to_body_dict = {}

        def fixture(fn_name, data=None, error=None):
            """
            Mock the asyncio.create_task function to run the future immediately.
            :param fn_name: The name of the function to mock.
                Either a JS function or an RPC function name.
            :param data: The response to return.
            :param error: The error to return.
            """
            func_to_body_dict[fn_name] = {"error": error} if error else {"data": data}

            def create_task(future):
                """Set the memory buffer and run the async task that checks it"""
                response = find_response(display_mock.mock_calls, func_to_body_dict)
                body = json.dumps(response).encode() + b"\0"

                memory = SharedMemory(name=mocked_token)
                memory.buf[0 : len(body)] = body
                task = MagicMock()
                loop = get_event_loop()
                task.result.return_value = loop.run_until_complete(future)
                return task

            io_loop.create_task = create_task

        yield fixture


@pytest.fixture()
def mock_fork(mock_callback):
    mock_callback("evm_snapshot", "0x123456")
    mock_callback("evm_revert", "0x12345678")
    data = {"number": "0x123", "timestamp": "0x65bbb460"}
    mock_callback("eth_getBlockByNumber", data)
    yield
    boa.reset_env()


@pytest.fixture()
def browser():
    # Import the browser module after the mocks have been set up
    from boa.integrations.jupyter import browser

    return browser


@pytest.fixture()
def display_mock(browser):
    yield browser.display
    browser.display.reset_mock()


@pytest.fixture()
def account():
    return Account.create()


@pytest.fixture()
def colab_eval_mock(browser):
    colab_eval_mock = MagicMock()
    with patch.object(browser, "colab_eval_js", colab_eval_mock):
        yield colab_eval_mock


def test_nest_applied(browser):
    browser.nest_asyncio.apply.assert_called()


def test_browser_sign_typed_data(browser, display_mock, mock_callback, env):
    signature = env.generate_address()
    mock_callback("eth_signTypedData_v4", signature)
    data = env.signer.sign_typed_data(
        {"name": "My App"}, {"types": []}, {"data": "0x1234"}
    )
    assert data == signature


def test_browser_rpc_inject_js(mocked_token, display_mock, browser, mock_callback):
    browser.BrowserRPC()
    (((js1,), _),) = display_mock.call_args_list
    assert "window._titanoboa = " in js1.data


def test_browser_signer_colab(colab_eval_mock, mocked_token, browser, display_mock):
    address = boa.env.generate_address()
    colab_eval_mock.return_value = json.dumps({"data": [address]})
    signer = browser.BrowserSigner()
    assert signer.address == address
    colab_eval_mock.assert_called_once()
    (js,), _ = colab_eval_mock.call_args
    assert f'rpc("{mocked_token}", "eth_requestAccounts", [])' in js
    display_mock.assert_called_once()


def test_browser_loads_signer(
    token, browser, display_mock, mock_callback, account, mock_fork
):
    mock_callback("eth_requestAccounts", [account.address])
    boa.set_browser_env()
    assert boa.env.eoa == account.address
    assert (
        type(boa.env._accounts[boa.env.eoa]).__name__ == browser.BrowserSigner.__name__
    )


def test_browser_chain_id(token, env, display_mock, mock_callback):
    display_mock.reset_mock()
    mock_callback("eth_chainId", "0x1234")
    assert env.get_chain_id() == 4660
    mock_callback("wallet_switchEthereumChain")
    env.set_chain_id(1)
    assert display_mock.call_count == 3
    (js,), _ = display_mock.call_args_list[-2]
    assert (
        f'rpc("{token}", "wallet_switchEthereumChain", [{{"chainId": "0x1"}}])'
        in js.data
    )


def test_browser_rpc(
    token, browser, display_mock, mock_callback, account, mock_fork, env
):
    mock_callback("eth_gasPrice", "0x123")
    assert env.get_gas_price() == 291

    assert display_mock.call_count == 6
    (js,), _ = display_mock.call_args
    assert f'rpc("{token}", "eth_gasPrice", [])' in js.data


def test_browser_rpc_error(
    token, browser, display_mock, mock_callback, account, mock_fork, env
):
    rpc_error = {"code": -32000, "message": "Reverted"}
    mock_callback(
        "eth_gasPrice", error={"message": "error", "info": {"error": rpc_error}}
    )
    with pytest.raises(browser.RPCError) as exc_info:
        env.get_gas_price()
    assert str(exc_info.value) == "-32000: Reverted"


def test_browser_rpc_server_error(
    token, browser, display_mock, mock_callback, account, mock_fork, env
):
    error = {
        "code": "UNKNOWN_ERROR",
        "error": {"code": -32603, "message": "server error"},
    }
    mock_callback("eth_gasPrice", error=error)
    with pytest.raises(browser.RPCError) as exc_info:
        env.get_gas_price()
    assert str(exc_info.value) == "-32603: server error"


def test_browser_js_error(
    token, browser, display_mock, mock_callback, account, mock_fork
):
    mock_callback(
        "eth_requestAccounts", error={"message": "custom message", "stack": ""}
    )
    with pytest.raises(browser.RPCError) as exc_info:
        browser.BrowserSigner()
    assert str(exc_info.value) == "CALLBACK_ERROR: custom message"
