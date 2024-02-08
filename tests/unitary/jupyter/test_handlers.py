from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def server_app_mock():
    server_app_mock = MagicMock()
    server_app_mock.web_app.settings = {"base_url": "/base_url"}
    return server_app_mock


@pytest.fixture()
def handlers(jupyter_module_mock, nest_asyncio_mock):
    from boa.integrations.jupyter import handlers

    return handlers


@pytest.fixture()
def callback_handler(handlers):
    handler = handlers.CallbackHandler()
    handler.request = MagicMock()
    handler.current_user = MagicMock()
    handler.set_status = MagicMock()
    handler.finish = MagicMock()
    return handler


def test_setup_handlers(handlers, server_app_mock, nest_asyncio_mock):
    handlers.setup_handlers(server_app_mock)
    server_app_mock.web_app.add_handlers.assert_called_once()
    _, kwargs = server_app_mock.web_app.add_handlers.call_args
    assert kwargs == {
        "host_pattern": ".*$",
        "host_handlers": [
            (
                "/base_url/titanoboa_jupyterlab/callback/(titanoboa_jupyterlab_[0-9a-fA-F]{64})$",
                handlers.CallbackHandler,
            )
        ],
    }
    nest_asyncio_mock.apply.assert_not_called()


def test_no_body(callback_handler, token):
    callback_handler.request.body = None
    callback_handler.post(token)
    callback_handler.set_status.assert_called_once_with(400)
    callback_handler.finish.assert_called_once_with(
        {"error": "Request body is required"}
    )


def test_invalid_token(callback_handler, token):
    callback_handler.post(token)
    callback_handler.set_status.assert_called_once_with(404)
    callback_handler.finish.assert_called_once_with(
        {"error": "Invalid token: " + token}
    )


def test_value_error(callback_handler, token, shared_memory, shared_memory_length):
    callback_handler.request.body = b"0" * shared_memory_length  # no space for the \0
    callback_handler.post(token)
    callback_handler.set_status.assert_called_once_with(413)
    callback_handler.finish.assert_called_once_with(
        {"error": "Request body has 51201 bytes, but only 51200 are allowed"}
    )


def test_success(callback_handler, token, shared_memory):
    callback_handler.request.body = b"body"
    callback_handler.post(token)
    callback_handler.set_status.assert_called_once_with(204)
    callback_handler.finish.assert_called_once_with()
