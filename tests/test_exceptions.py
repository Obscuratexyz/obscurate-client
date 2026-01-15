"""Tests for exception classes."""

import pytest

from obscurate_client.exceptions import (
    ObscurateError,
    WalletLockedError,
    InsufficientBalanceError,
    NoteExhaustedError,
    InsufficientAnonymityError,
    ProofGenerationError,
    SidecarUnavailableError,
    PaymentGatewayError,
    ChallengeExpiredError,
    ConfigurationError,
    DryRunError,
    SpendingLimitError,
)


class TestObscurateError:
    """Tests for base ObscurateError."""

    def test_basic_creation(self):
        """Test basic error creation."""
        error = ObscurateError("Test message")

        assert str(error) == "Test message"
        assert error.message == "Test message"
        assert error.details == {}

    def test_with_details(self):
        """Test error with details."""
        error = ObscurateError("Test message", {"key": "value"})

        assert error.details == {"key": "value"}

    def test_repr(self):
        """Test error repr."""
        error = ObscurateError("Test", {"foo": "bar"})

        assert "ObscurateError" in repr(error)
        assert "Test" in repr(error)


class TestWalletErrors:
    """Tests for wallet-related errors."""

    def test_wallet_locked_default(self):
        """Test WalletLockedError default message."""
        error = WalletLockedError()

        assert "locked" in error.message.lower()

    def test_insufficient_balance(self):
        """Test InsufficientBalanceError."""
        error = InsufficientBalanceError(required=10.0, available=5.0)

        assert error.required == 10.0
        assert error.available == 5.0
        assert "10.00" in error.message
        assert "5.00" in error.message

    def test_note_exhausted(self):
        """Test NoteExhaustedError."""
        error = NoteExhaustedError()

        assert "exhausted" in error.message.lower()


class TestPrivacyErrors:
    """Tests for privacy-related errors."""

    def test_insufficient_anonymity(self):
        """Test InsufficientAnonymityError."""
        error = InsufficientAnonymityError(
            message="Anonymity compromised",
            anonymity_set_size=5,
            min_required=10,
        )

        assert error.anonymity_set_size == 5
        assert error.min_required == 10
        assert error.details["anonymity_set_size"] == 5

    def test_proof_generation(self):
        """Test ProofGenerationError."""
        error = ProofGenerationError(phase="witness")

        assert error.phase == "witness"
        assert error.details["phase"] == "witness"


class TestNetworkErrors:
    """Tests for network-related errors."""

    def test_sidecar_unavailable(self):
        """Test SidecarUnavailableError."""
        error = SidecarUnavailableError("http://localhost:3000")

        assert error.url == "http://localhost:3000"
        assert "localhost:3000" in error.message

    def test_payment_gateway(self):
        """Test PaymentGatewayError."""
        error = PaymentGatewayError(
            code="INVALID_PROOF",
            message="Proof verification failed",
        )

        assert error.code == "INVALID_PROOF"
        assert error.details["gateway_code"] == "INVALID_PROOF"

    def test_challenge_expired(self):
        """Test ChallengeExpiredError."""
        error = ChallengeExpiredError(
            resource="https://api.example.com",
            expired_at=1000000000,
        )

        assert error.resource == "https://api.example.com"
        assert error.expired_at == 1000000000


class TestConfigurationErrors:
    """Tests for configuration errors."""

    def test_configuration_error(self):
        """Test ConfigurationError."""
        error = ConfigurationError(
            message="Missing required config",
            config_key="SIDECAR_URL",
        )

        assert error.config_key == "SIDECAR_URL"

    def test_dry_run_error(self):
        """Test DryRunError."""
        error = DryRunError(
            amount=5.0,
            resource="https://api.example.com/premium",
        )

        assert error.amount == 5.0
        assert error.resource == "https://api.example.com/premium"
        assert "DRY RUN" in error.message

    def test_spending_limit(self):
        """Test SpendingLimitError."""
        error = SpendingLimitError(
            requested=100.0,
            limit=50.0,
            period="hourly",
        )

        assert error.requested == 100.0
        assert error.limit == 50.0
        assert error.period == "hourly"
        assert "100.00" in error.message
        assert "50.00" in error.message
        assert "hourly" in error.message
