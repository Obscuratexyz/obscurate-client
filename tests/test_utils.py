"""Tests for utility functions and data models."""

import base64
import json
import pytest

from obscurate_client.utils import (
    X402Challenge,
    PaymentResult,
    WalletBalance,
    extract_challenge_from_response,
    build_payment_header,
    validate_usdc_amount,
    validate_sidecar_url,
)


# =============================================================================
# X402Challenge Tests
# =============================================================================


class TestX402Challenge:
    """Tests for X402Challenge parsing."""

    def test_from_header_base64(self):
        """Test parsing base64-encoded header."""
        challenge_data = {
            "version": "1",
            "scheme": "exact",
            "network": "base",
            "maxAmountRequired": "5.0",
            "resource": "https://api.example.com/data",
            "nonce": "abc123",
            "expiry": 1999999999,
        }
        encoded = base64.b64encode(json.dumps(challenge_data).encode()).decode()

        challenge = X402Challenge.from_header(f"x402 {encoded}")

        assert challenge.scheme == "exact"
        assert challenge.amount_float == 5.0
        assert challenge.resource == "https://api.example.com/data"

    def test_from_header_json(self):
        """Test parsing direct JSON header."""
        challenge_data = {
            "version": "1",
            "scheme": "upto",
            "network": "polygon",
            "maxAmountRequired": "10.0",
            "resource": "https://api.example.com/premium",
            "nonce": "xyz789",
            "expiry": 1999999999,
        }

        challenge = X402Challenge.from_header(json.dumps(challenge_data))

        assert challenge.scheme == "upto"
        assert challenge.network == "polygon"
        assert challenge.amount_float == 10.0

    def test_from_response_body_dict(self):
        """Test parsing from response body dict."""
        body = {
            "version": "1",
            "scheme": "exact",
            "network": "base",
            "maxAmountRequired": "1.0",
            "resource": "https://api.example.com/data",
            "nonce": "abc",
            "expiry": 1999999999,
        }

        challenge = X402Challenge.from_response_body(body)

        assert challenge.scheme == "exact"
        assert challenge.amount_float == 1.0

    def test_from_response_body_array(self):
        """Test parsing from array-wrapped body."""
        body = [
            {
                "version": "1",
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "2.0",
                "resource": "https://api.example.com/data",
                "nonce": "abc",
                "expiry": 1999999999,
            }
        ]

        challenge = X402Challenge.from_response_body(body)

        assert challenge.amount_float == 2.0

    def test_is_expired(self):
        """Test expiry checking."""
        # Expired challenge
        expired = X402Challenge(
            version="1",
            scheme="exact",
            network="base",
            maxAmountRequired="1.0",
            resource="https://api.example.com",
            nonce="abc",
            expiry=0,  # Epoch - definitely expired
        )
        assert expired.is_expired() is True

        # Future challenge
        future = X402Challenge(
            version="1",
            scheme="exact",
            network="base",
            maxAmountRequired="1.0",
            resource="https://api.example.com",
            nonce="abc",
            expiry=9999999999,
        )
        assert future.is_expired() is False


# =============================================================================
# PaymentResult Tests
# =============================================================================


class TestPaymentResult:
    """Tests for PaymentResult model."""

    def test_from_sidecar_response(self):
        """Test parsing sidecar payment response."""
        response = {
            "authHeader": "x402 abc123...",
            "amountPaid": 1.5,
            "remainingBalance": 98.5,
            "nullifierHash": "0x1234...",
            "proofId": "proof_abc",
        }

        result = PaymentResult.model_validate(response)

        assert result.auth_header == "x402 abc123..."
        assert result.amount_paid == 1.5
        assert result.remaining_balance == 98.5


# =============================================================================
# WalletBalance Tests
# =============================================================================


class TestWalletBalance:
    """Tests for WalletBalance model."""

    def test_from_sidecar_response(self):
        """Test parsing sidecar balance response."""
        response = {
            "totalUsdc": 100.0,
            "noteCount": 5,
            "largestNote": 50.0,
            "smallestNote": 5.0,
            "chain": "base",
        }

        balance = WalletBalance.model_validate(response)

        assert balance.total_usdc == 100.0
        assert balance.note_count == 5
        assert balance.largest_note == 50.0
        assert balance.chain == "base"


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestExtractChallenge:
    """Tests for extract_challenge_from_response."""

    def test_extract_from_www_authenticate(self):
        """Test extraction from WWW-Authenticate header."""
        challenge_data = {
            "version": "1",
            "scheme": "exact",
            "network": "base",
            "maxAmountRequired": "1.0",
            "resource": "https://api.example.com",
            "nonce": "abc",
            "expiry": 9999999999,
        }
        encoded = base64.b64encode(json.dumps(challenge_data).encode()).decode()

        result = extract_challenge_from_response(
            status_code=402,
            headers={"WWW-Authenticate": f"x402 {encoded}"},
        )

        assert result is not None
        assert result.scheme == "exact"

    def test_extract_from_body(self):
        """Test extraction from response body."""
        challenge_data = {
            "version": "1",
            "scheme": "exact",
            "network": "base",
            "maxAmountRequired": "1.0",
            "resource": "https://api.example.com",
            "nonce": "abc",
            "expiry": 9999999999,
        }

        result = extract_challenge_from_response(
            status_code=402,
            headers={},
            body=json.dumps(challenge_data).encode(),
        )

        assert result is not None
        assert result.scheme == "exact"

    def test_returns_none_for_non_402(self):
        """Test that non-402 responses return None."""
        result = extract_challenge_from_response(
            status_code=200,
            headers={},
        )

        assert result is None


class TestBuildPaymentHeader:
    """Tests for build_payment_header."""

    def test_builds_header(self):
        """Test header building."""
        headers = build_payment_header("x402 abc123...")

        assert headers == {"X-PAYMENT": "x402 abc123..."}


class TestValidateUsdcAmount:
    """Tests for validate_usdc_amount."""

    def test_valid_amount(self):
        """Test valid amounts pass."""
        validate_usdc_amount(1.0)
        validate_usdc_amount(0.000001)
        validate_usdc_amount(1000000.0)

    def test_negative_raises(self):
        """Test negative amounts raise."""
        with pytest.raises(ValueError, match="negative"):
            validate_usdc_amount(-1.0)

    def test_zero_raises(self):
        """Test zero raises."""
        with pytest.raises(ValueError, match="zero"):
            validate_usdc_amount(0)

    def test_exceeds_max_raises(self):
        """Test exceeding max raises."""
        with pytest.raises(ValueError, match="exceeds"):
            validate_usdc_amount(100.0, max_amount=50.0)


class TestValidateSidecarUrl:
    """Tests for validate_sidecar_url."""

    def test_valid_http(self):
        """Test valid HTTP URL."""
        url = validate_sidecar_url("http://localhost:3000")
        assert url == "http://localhost:3000"

    def test_valid_https(self):
        """Test valid HTTPS URL."""
        url = validate_sidecar_url("https://sidecar.example.com")
        assert url == "https://sidecar.example.com"

    def test_strips_trailing_slash(self):
        """Test trailing slash removal."""
        url = validate_sidecar_url("http://localhost:3000/")
        assert url == "http://localhost:3000"

    def test_empty_raises(self):
        """Test empty URL raises."""
        with pytest.raises(ValueError, match="empty"):
            validate_sidecar_url("")

    def test_invalid_scheme_raises(self):
        """Test invalid scheme raises."""
        with pytest.raises(ValueError, match="scheme"):
            validate_sidecar_url("ftp://localhost:3000")
