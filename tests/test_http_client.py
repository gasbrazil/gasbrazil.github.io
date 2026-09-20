"""Tests for unified HTTP pipeline client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import http_client
import pytest
import requests


def test_make_session_has_custom_user_agent_and_retries():
    session = http_client.make_session(user_agent="TestAgent/1.0")
    assert "TestAgent/1.0" in session.headers["User-Agent"]
    # Verify adapter mounts
    assert "https://" in session.adapters
    assert "http://" in session.adapters


def test_fetch_url_successful(monkeypatch):
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True}

    mock_session = MagicMock(spec=requests.Session)
    mock_session.request.return_value = mock_resp

    res = http_client.fetch_url("https://example.com/api", session=mock_session)
    assert res.json() == {"ok": True}
    mock_session.request.assert_called_once_with(
        method="GET",
        url="https://example.com/api",
        params=None,
        data=None,
        json=None,
        headers=None,
        timeout=http_client.DEFAULT_TIMEOUT,
    )


def test_fetch_url_raises_for_status():
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

    mock_session = MagicMock(spec=requests.Session)
    mock_session.request.return_value = mock_resp

    with pytest.raises(requests.HTTPError, match="404 Not Found"):
        http_client.fetch_url("https://example.com/missing", session=mock_session)


def test_download_file_atomic(tmp_path):
    dest = tmp_path / "output.csv"
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.raw = MagicMock()

    with patch("http_client.make_session") as mock_make:
        mock_sess = MagicMock()
        mock_sess.get.return_value.__enter__.return_value = mock_resp
        mock_make.return_value = mock_sess

        with patch("shutil.copyfileobj") as mock_copy:
            out = http_client.download_file("https://example.com/file.csv", dest, session=mock_sess)
            assert out == dest
            assert mock_copy.called
