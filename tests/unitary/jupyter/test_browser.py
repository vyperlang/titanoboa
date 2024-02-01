import json
import re
from asyncio import get_event_loop
from multiprocessing.shared_memory import SharedMemory
from unittest import mock
from unittest.mock import MagicMock

import pytest
from eth_account import Account


@pytest.fixture()
def display_mock(replace_modules):
    with mock.patch("boa.integrations.jupyter.browser.display") as display_mock:
        yield display_mock


@pytest.fixture()
def mocked_token(token):
    with mock.patch(
        "boa.integrations.jupyter.browser._generate_token"
    ) as generate_token:
        generate_token.return_value = token
        yield token


@pytest.fixture()
def mock_inject_javascript():
    with mock.patch(
        "boa.integrations.jupyter.browser.install_jupyter_javascript_triggers"
    ) as inject_mock:
        yield inject_mock


def find_response(mock_calls, func_to_body_dict):
    (javascript,) = [call for call in mock_calls if call.args][-1].args
    js_func, js_args = re.match(
        r"window._titanoboa.([a-zA-Z0-9_]+)\(([^)]*)\)", javascript.data
    ).groups()
    if js_func not in ("rpc", "multiRpc"):
        return func_to_body_dict[js_func]

    first_arg = json.loads(f"[{js_args}]")[1]  # ignore the token
    if js_func == "rpc":
        return func_to_body_dict[first_arg]

    responses = [func_to_body_dict[name] for name, _ in first_arg]
    error = next((r["error"] for r in responses if r.get("error")), None)
    if error:
        return error
    return {"data": [r["data"] for r in responses]}


@pytest.fixture()
def mock_callback(mocked_token, browser):
    """Returns a function that allows mocking the result of the frontend callback."""

    with mock.patch(
        "boa.integrations.jupyter.browser.get_running_loop"
    ) as mock_get_loop:
        io_loop = mock_get_loop.return_value
        io_loop.time.return_value = 0
        func_to_body_dict = {}

        def fixture(fn_name, data=None, error=None):
            """
            Mock the asyncio.create_task function to run the future immediately.
            :param fn_name: The name of the function to mock.
            :param data: The response to return.
            :param error: The error to return.
            """
            func_to_body_dict[fn_name] = {"data": data, "error": error}

            def create_task(future):
                """Set the memory buffer and run the async task that checks it"""
                response = find_response(browser.display.mock_calls, func_to_body_dict)
                body = json.dumps(response).encode() + b"\0"

                memory = SharedMemory(name=mocked_token)
                memory.buf[0 : len(body)] = body
                task = MagicMock()
                task.result.return_value = get_event_loop().run_until_complete(future)
                return task

            io_loop.create_task = create_task

        yield fixture


@pytest.fixture()
def mock_get_block_by_number(mock_callback):
    mock_callback(
        "eth_getBlockByNumber", {"number": "0x123", "timestamp": "0x65bbb460"}
    )


@pytest.fixture()
def browser(nest_asyncio_mock, jupyter_module_mock):
    from boa.integrations.jupyter import browser

    return browser


@pytest.fixture()
def account():
    return Account.create()


@pytest.fixture()
def colab_eval_mock(replace_modules):
    colab_output_mock = MagicMock()
    replace_modules({"google.colab.output": colab_output_mock})
    return colab_output_mock.eval_js


def test_nest_applied(nest_asyncio_mock, browser):
    nest_asyncio_mock.apply.assert_called_once()


def test_browser_signer_given_address(browser, display_mock, mock_inject_javascript):
    signer = browser.BrowserSigner("0x1234")
    assert signer.address == "0x1234"
    display_mock.assert_not_called()
    mock_inject_javascript.assert_not_called()


def test_browser_signer_no_address(
    mocked_token, browser, display_mock, mock_callback, mock_inject_javascript
):
    mock_callback({"data": "0x123"})
    signer = browser.BrowserSigner()
    assert signer.address == "0x123"
    display_mock.assert_called_once()
    (js,), _ = display_mock.call_args
    assert f'loadSigner("{mocked_token}")' in js.data
    mock_inject_javascript.assert_called()


def test_browser_signer_colab(
    mocked_token, browser, colab_eval_mock, mock_inject_javascript, display_mock
):
    colab_eval_mock.return_value = json.dumps({"data": "0x123"})
    signer = browser.BrowserSigner()
    assert signer.address == "0x123"
    colab_eval_mock.assert_called_once()
    (js,), _ = colab_eval_mock.call_args
    assert f'loadSigner("{mocked_token}")' in js
    mock_inject_javascript.assert_called()
    display_mock.assert_not_called()


def test_browser_env(
    browser,
    display_mock,
    mock_inject_javascript,
    account,
    mock_callback,
    mock_get_block_by_number,
):
    env = browser.NetworkEnv.browser(account)
    assert env.eoa == account
    display_mock.assert_called_once()
    mock_inject_javascript.assert_called_once()


def test_browser_env_loads_signer(
    token,
    browser,
    display_mock,
    mock_callback,
    mock_inject_javascript,
    account,
    mock_get_block_by_number,
):
    mock_callback("loadSigner", account.address)
    env = browser.NetworkEnv.browser()
    assert env.eoa == account.address
    assert type(env._accounts[env.eoa]).__name__ == browser.BrowserSigner.__name__
    mock_inject_javascript.assert_called()


def test_browser_env_rpc(
    token,
    browser,
    display_mock,
    mock_callback,
    mock_inject_javascript,
    account,
    mock_get_block_by_number,
):
    env = browser.NetworkEnv.browser(account)

    mock_callback({"data": "0x123"})
    assert env.get_gas_price() == 291

    display_mock.assert_called_once()
    (js,), _ = display_mock.call_args
    assert f'rpc("{token}", "eth_gasPrice", [])' in js.data
    mock_inject_javascript.assert_called()


def test_browser_rpc_error(
    token, browser, display_mock, mock_callback, mock_inject_javascript, account
):
    env = browser.NetworkEnv.browser(account)

    rpc_error = {"code": -32000, "message": "Reverted"}
    mock_callback({"error": {"message": "error", "info": {"error": rpc_error}}})
    with pytest.raises(browser.RPCError) as exc_info:
        env.get_gas_price()
    assert str(exc_info.value) == "-32000: Reverted"


def test_browser_rpc_server_error(
    token, browser, display_mock, mock_callback, mock_inject_javascript, account
):
    env = browser.NetworkEnv.browser(account)

    original_error = {
        "message": "server error",
        "code": -41002,
        "data": "net/http: timeout awaiting response headers",
    }
    error = {
        "code": -32603,
        "data": {"originalError": original_error},
        "message": "server error",
    }
    outer_error = {
        "code": "UNKNOWN_ERROR",
        "error": error,
        "payload": {},
        "shortMessage": "could not coalesce error",
    }
    rpc_message = {"error": outer_error}
    mock_callback(rpc_message)
    with pytest.raises(browser.RPCError) as exc_info:
        env.get_gas_price()
    assert str(exc_info.value) == "-32603: server error"


def test_browser_js_error(
    token, browser, display_mock, mock_callback, mock_inject_javascript, account
):
    mock_callback({"error": {"message": "custom message", "stack": ""}})
    with pytest.raises(browser.RPCError) as exc_info:
        browser.BrowserSigner()
    assert str(exc_info.value) == "CALLBACK_ERROR: custom message"


def test_browser_env_no_fork(browser, account):
    with pytest.raises(NotImplementedError):
        browser.NetworkEnv.browser(account).fork("")
