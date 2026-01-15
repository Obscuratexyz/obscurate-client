"""Tests for the DarkPoolClient core functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from obscurate_client import (
    DarkPoolClient,
    DarkPoolConfig,
    WalletLockedError,
    InsufficientBalanceError,
    SpendingLimitError,
    DryRunError,
    SidecarUnavailableError,
)
from obscurate_client.utils import X402Challenge


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_sidecar_response():
    """Create a mock sidecar response."""
    return {
        "totalUsdc": 100.0,
        "noteCount": 3,
        "largestNote": 50.0,
        "smallestNote": 10.0,
        "chain": "base",
    }


@pytest.fixture
def mock_health_response():
    """Create a mock health response."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "uptime": 3600,
        "mode": "mock",
        "chains": [
            {"chain": "base", "status": "connected", "blockNumber": 12345678},
        ],
    }


@pytest.fixture
def mock_payment_response():
    """Create a mock payment response."""
    return {
        "authHeader": "x402 abc123...",
        "amountPaid": 1.0,
        "remainingBalance": 99.0,
        "nullifierHash": "0x1234...",
        "proofId": "proof_123",
    }


@pytest.fixture
def mock_challenge():
    """Create a mock x402 challenge."""
    return X402Challenge(
        version="1",
        scheme="exact",
        network="base",
        maxAmountRequired="1.0",
        resource="https://api.example.com/data",
        nonce="abc123",
        expiry=9999999999,  # Far future
    )


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================


class TestDarkPoolConfig:
    """Tests for DarkPoolConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DarkPoolConfig()

        assert config.sidecar_url == "http://localhost:3000"
        assert config.dry_run is False
        assert config.max_spend_per_tx == 0
        assert config.max_spend_hourly == 0
        assert config.max_retries == 3
        assert config.timeout == 30.0

    def test_config_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("OBSCURATE_SIDECAR_URL", "http://sidecar:4000")
        monkeypatch.setenv("OBSCURATE_DRY_RUN", "true")
        monkeypatch.setenv("OBSCURATE_MAX_SPEND_TX", "50.0")
        monkeypatch.setenv("OBSCURATE_MAX_SPEND_HOURLY", "500.0")

        config = DarkPoolConfig()

        assert config.sidecar_url == "http://sidecar:4000"
        assert config.dry_run is True
        assert config.max_spend_per_tx == 50.0
        assert config.max_spend_hourly == 500.0


# =============================================================================
# CLIENT TESTS
# =============================================================================


class TestDarkPoolClient:
    """Tests for DarkPoolClient."""

    def test_client_initialization(self):
        """Test client initialization."""
        client = DarkPoolClient(
            sidecar_url="http://localhost:3000",
            dry_run=True,
            max_spend_per_tx=10.0,
        )

        assert client._config.sidecar_url == "http://localhost:3000"
        assert client._config.dry_run is True
        assert client._config.max_spend_per_tx == 10.0

    def test_is_unlocked(self):
        """Test wallet lock status."""
        client = DarkPoolClient()

        assert client.is_unlocked() is False

        client.load_credentials("encrypted_note", "password")
        assert client.is_unlocked() is True

    def test_ensure_unlocked_raises(self):
        """Test that operations fail when wallet is locked."""
        client = DarkPoolClient()

        with pytest.raises(WalletLockedError):
            client._ensure_unlocked()

    @pytest.mark.asyncio
    async def test_connect_and_close(self, mock_health_response):
        """Test client connect and close lifecycle."""
        client = DarkPoolClient()

        with patch.object(client, "_sidecar_request", new_callable=AsyncMock) as mock:
            mock.return_value = mock_health_response

            await client.connect()

            assert client._http_client is not None
            assert client._sidecar_client is not None

            await client.close()

            assert client._http_client is None
            assert client._sidecar_client is None

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_health_response):
        """Test async context manager."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_health_response

            async with DarkPoolClient() as client:
                assert client._http_client is not None

            assert client._http_client is None


# =============================================================================
# WALLET TESTS
# =============================================================================


class TestWalletInterface:
    """Tests for WalletInterface."""

    @pytest.mark.asyncio
    async def test_get_balance(self, mock_sidecar_response, mock_health_response):
        """Test getting wallet balance."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = [mock_health_response, mock_sidecar_response]

            async with DarkPoolClient() as client:
                client.load_credentials("note", "password")

                balance = await client.wallet.get_balance()

                assert balance.total_usdc == 100.0
                assert balance.note_count == 3

    @pytest.mark.asyncio
    async def test_get_balance_locked(self, mock_health_response):
        """Test balance check when wallet is locked."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_health_response

            async with DarkPoolClient() as client:
                with pytest.raises(WalletLockedError):
                    await client.wallet.get_balance()

    @pytest.mark.asyncio
    async def test_can_afford(self, mock_sidecar_response, mock_health_response):
        """Test affordability check."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = [mock_health_response, mock_sidecar_response]

            async with DarkPoolClient() as client:
                client.load_credentials("note", "password")

                assert await client.wallet.can_afford(50.0) is True
                
                # Reset mock for next call
                mock.side_effect = [mock_sidecar_response]
                assert await client.wallet.can_afford(200.0) is False


# =============================================================================
# HTTP INTERFACE TESTS
# =============================================================================


class TestHTTPInterface:
    """Tests for HTTPInterface."""

    @pytest.mark.asyncio
    async def test_get_success(self, mock_health_response):
        """Test successful GET request."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock_sidecar:
            mock_sidecar.return_value = mock_health_response

            async with DarkPoolClient() as client:
                # Mock the HTTP client
                mock_response = MagicMock(spec=httpx.Response)
                mock_response.status_code = 200
                mock_response.json.return_value = {"data": "test"}

                client._http_client.request = AsyncMock(return_value=mock_response)

                response = await client.http.get("https://api.example.com/data")

                assert response.status_code == 200
                assert response.json() == {"data": "test"}

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, mock_health_response, mock_challenge):
        """Test dry-run mode prevents actual payments."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock_sidecar:
            mock_sidecar.return_value = mock_health_response

            async with DarkPoolClient(dry_run=True) as client:
                client.load_credentials("note", "password")

                # Mock 402 response
                mock_response = MagicMock(spec=httpx.Response)
                mock_response.status_code = 402
                mock_response.headers = {
                    "WWW-Authenticate": f"x402 {mock_challenge.model_dump_json()}"
                }
                mock_response.content = b""

                client._http_client.request = AsyncMock(return_value=mock_response)

                with pytest.raises(DryRunError) as exc:
                    await client.http.get("https://api.example.com/paid")

                assert exc.value.amount == 1.0
                assert exc.value.resource == "https://api.example.com/paid"

    @pytest.mark.asyncio
    async def test_spending_limit_exceeded(self, mock_health_response, mock_challenge):
        """Test spending limit enforcement."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock_sidecar:
            mock_sidecar.return_value = mock_health_response

            async with DarkPoolClient(max_spend_per_tx=0.5) as client:
                client.load_credentials("note", "password")

                # Mock 402 response requiring 1.0 USDC
                mock_response = MagicMock(spec=httpx.Response)
                mock_response.status_code = 402
                mock_response.headers = {
                    "WWW-Authenticate": f"x402 {mock_challenge.model_dump_json()}"
                }
                mock_response.content = b""

                client._http_client.request = AsyncMock(return_value=mock_response)

                with pytest.raises(SpendingLimitError) as exc:
                    await client.http.get("https://api.example.com/paid")

                assert exc.value.requested == 1.0
                assert exc.value.limit == 0.5


# =============================================================================
# DECORATOR TESTS
# =============================================================================


class TestPayProtectedDecorator:
    """Tests for the @pay_protected decorator."""

    @pytest.mark.asyncio
    async def test_decorator_sets_limit(self, mock_health_response):
        """Test that decorator sets spending limit."""
        with patch.object(
            DarkPoolClient, "_sidecar_request", new_callable=AsyncMock
        ) as mock_sidecar:
            mock_sidecar.return_value = mock_health_response

            async with DarkPoolClient() as client:
                original_limit = client._config.max_spend_per_tx

                @client.pay_protected(max_spend=25.0)
                async def test_func():
                    assert client._config.max_spend_per_tx == 25.0
                    return "result"

                result = await test_func()

                assert result == "result"
                # Limit restored after function
                assert client._config.max_spend_per_tx == original_limit
