import pytest

from app.parsing.noise import NoiseReason, noise_reason
from tests.parsing.fixtures import (
    COLLECT,
    DECLINED,
    FAILED,
    FUTURE,
    KYC,
    OTP,
    S1,
    S3,
    S6,
)


@pytest.mark.parametrize(
    "text,reason",
    [
        (OTP, NoiseReason.OTP),
        ("Your OTP is 4321", NoiseReason.OTP),
        (FUTURE, NoiseReason.FUTURE_DEBIT),
        (DECLINED, NoiseReason.FAILED),
        (FAILED, NoiseReason.FAILED),
        (COLLECT, NoiseReason.COLLECT_REQUEST),
        (KYC, NoiseReason.NO_AMOUNT),
        (S1, None),
        (S3, None),
        (S6, None),
    ],
)
def test_noise_reason(text, reason):
    assert noise_reason(text) == reason
