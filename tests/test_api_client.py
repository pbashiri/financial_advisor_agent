"""Tests for API client (with mocked httpx)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from financial_advisor.api_client import ApiClient


@pytest.fixture
def api_client():
    """ApiClient pointing to a fake base URL (we mock all requests)."""
    return ApiClient(base_url="http://testserver")


@pytest.mark.asyncio
async def test_health_returns_true_when_200(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        m_get.return_value = mock_client

        result = await api_client.health()
        assert result is True


@pytest.mark.asyncio
async def test_health_returns_false_on_connection_error(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        import httpx

        m_get.side_effect = httpx.ConnectError("Connection refused")
        result = await api_client.health()
        assert result is False


@pytest.mark.asyncio
async def test_health_returns_false_when_not_200(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        m_get.return_value = mock_client

        result = await api_client.health()
        assert result is False


@pytest.mark.asyncio
async def test_get_portfolio_summary_text_returns_text(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"text": "*Portfolio Summary*\n\nTotal: $1,500"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        m_get.return_value = mock_client

        result = await api_client.get_portfolio_summary_text()
        assert result == "*Portfolio Summary*\n\nTotal: $1,500"


@pytest.mark.asyncio
async def test_get_portfolio_summary_text_returns_none_on_connect_error(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        import httpx

        m_get.side_effect = httpx.ConnectError("refused")
        result = await api_client.get_portfolio_summary_text()
        assert result is None


@pytest.mark.asyncio
async def test_import_csv_text_returns_result(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"imported": 2, "skipped": 0, "errors": []}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        m_get.return_value = mock_client

        result = await api_client.import_csv_text("symbol,shares,cost_basis\nAAPL,10,150\n")
        assert result is not None
        assert result["imported"] == 2


@pytest.mark.asyncio
async def test_import_csv_text_returns_none_on_timeout(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        import httpx

        m_get.side_effect = httpx.TimeoutException("timeout")
        result = await api_client.import_csv_text("symbol,shares,cost_basis\nAAPL,10,150\n")
        assert result is None


@pytest.mark.asyncio
async def test_get_quote_returns_dict_when_200(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"symbol": "AAPL", "price": 185.0}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        m_get.return_value = mock_client

        result = await api_client.get_quote("AAPL")
        assert result == {"symbol": "AAPL", "price": 185.0}


@pytest.mark.asyncio
async def test_get_portfolio_summary_returns_dict(api_client):
    """get_portfolio_summary returns raw summary dict when 200."""
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "total_value": 5000.0,
            "total_cost": 4000.0,
            "total_gain": 1000.0,
            "gain_pct": 25.0,
            "holdings": [],
            "allocation": [],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        m_get.return_value = mock_client

        result = await api_client.get_portfolio_summary()
        assert result is not None
        assert result["total_value"] == 5000.0
        assert result["gain_pct"] == 25.0


@pytest.mark.asyncio
async def test_get_quote_returns_none_on_404(api_client):
    with patch.object(api_client, "_get_client", new_callable=AsyncMock) as m_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        m_get.return_value = mock_client

        result = await api_client.get_quote("INVALID")
        assert result is None


@pytest.mark.asyncio
async def test_close_closes_client(api_client):
    mock_client = AsyncMock()
    mock_client.is_closed = False
    with patch.object(api_client, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        await api_client._get_client()
        api_client._client = mock_client
    await api_client.close()
    mock_client.aclose.assert_called_once()
