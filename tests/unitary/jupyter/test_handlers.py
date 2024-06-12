from unittest.mock import MagicMock

import pytest

from boa.integrations.jupyter.constants import SHARED_MEMORY_LENGTH, TOKEN_REGEX
from boa.integrations.jupyter.handlers import CallbackHandler, setup_handlers


@pytest.fixture()
def server_app_mock():
    server_app_mock = MagicMock()
    server_app_mock.web_app.settings = {"base_url": "/base_url"}
    return server_app_mock


@pytest.fixture()
def callback_handler(server_app_mock):
    request_mock = MagicMock()
    handler = CallbackHandler(server_app_mock.web_app, request_mock)
    handler.current_user = MagicMock()
    handler.finish = MagicMock()
    return handler


def test_setup_handlers(server_app_mock):
    setup_handlers(server_app_mock)
    server_app_mock.web_app.add_handlers.assert_called_once()
    _, kwargs = server_app_mock.web_app.add_handlers.call_args
    assert kwargs == {
        "host_pattern": ".*$",
        "host_handlers": [
            (
                f"/base_url/titanoboa_jupyterlab/callback/({TOKEN_REGEX})$",
                CallbackHandler,
            )
        ],
    }


def test_no_body(callback_handler, token):
    callback_handler.request.body = None
    callback_handler.post(token)
    assert callback_handler.get_status() == 400
    callback_handler.finish.assert_called_once_with(
        {"error": "Request body is required"}
    )


def test_invalid_token(callback_handler, token):
    callback_handler.post(token)
    assert callback_handler.get_status() == 404
    callback_handler.finish.assert_called_once_with(
        {"error": "Invalid token: " + token}
    )


def test_value_error(callback_handler, token, shared_memory):
    callback_handler.request.body = b"0" * SHARED_MEMORY_LENGTH  # no space for the \0
    callback_handler.post(token)
    assert callback_handler.get_status() == 413
    callback_handler.finish.assert_called_once_with(
        {"error": "Request body has 102401 bytes, but only 102400 are allowed"}
    )


def test_success(callback_handler, token, shared_memory):
    callback_handler.request.body = b"body"
    callback_handler.post(token)
    assert callback_handler.get_status() == 204
    callback_handler.finish.assert_called_once_with()
