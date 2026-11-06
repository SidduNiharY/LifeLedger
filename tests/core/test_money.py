from decimal import Decimal

import pytest

from app.core.money import format_inr, parse_inr_amount


@pytest.mark.parametrize(
    "text,expected",
    [
        ("450", "450.00"),
        ("1,250.50", "1250.50"),
        ("1,02,345.67", "102345.67"),
        ("Rs.2,999", "2999.00"),
        ("INR 50,000.00", "50000.00"),
        ("₹ 75.5", "75.50"),
        ("Rs 1250.505", "1250.51"),
        ("  rs. 10  ", "10.00"),
        ("inr100", "100.00"),
        ("0", "0.00"),
        ("123456789012.345", "123456789012.35"),
    ],
)
def test_parse_inr_amount(text, expected):
    assert str(parse_inr_amount(text)) == expected


@pytest.mark.parametrize(
    "text", ["", "abc", "1.2.3", "-5", "   ", "Rs.", "₹", "1e5", "Rs -5", "NaN", "5 0"]
)
def test_parse_inr_amount_rejects(text):
    with pytest.raises(ValueError):
        parse_inr_amount(text)


@pytest.mark.parametrize(
    "amount,expected",
    [
        ("450", "₹450.00"),
        ("1250.5", "₹1,250.50"),
        ("102345.67", "₹1,02,345.67"),
        ("12345678.9", "₹1,23,45,678.90"),
        ("0.5", "₹0.50"),
        ("999", "₹999.00"),
        ("1000", "₹1,000.00"),
        ("100000", "₹1,00,000.00"),
        ("1250.505", "₹1,250.51"),
        ("0", "₹0.00"),
        ("999999.999", "₹10,00,000.00"),
        ("1234567890123", "₹12,34,56,78,90,123.00"),
    ],
)
def test_format_inr(amount, expected):
    assert format_inr(Decimal(amount)) == expected


def test_format_inr_rejects_negative():
    with pytest.raises(ValueError):
        format_inr(Decimal("-1"))
