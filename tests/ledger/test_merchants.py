import pytest

from app.ledger.merchants import merchant_key


@pytest.mark.parametrize(
    "raw,key",
    [
        ("swiggy@icici", "SWIGGY"),
        ("SWIGGY*BLR", "SWIGGY"),
        ("BESCOM", "BESCOM"),
        ("AMAZON PAY INDIA", "AMAZON PAY"),
        ("ACME CORP PVT LTD", "ACME"),
        ("The Bangalore Electricity Supply", "BANGALORE ELECTRICITY"),
        ("9876543210@ybl", "9876543210"),
        ("ZOMATO 12345678", "ZOMATO"),
        (None, None),
        ("  ", None),
    ],
)
def test_merchant_key(raw, key):
    assert merchant_key(raw) == key
