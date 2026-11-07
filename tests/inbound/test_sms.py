import pytest

from app.inbound.sms import is_trusted_sms_sender


@pytest.mark.parametrize(
    "sender,ok",
    [
        ("VM-HDFCBK", True),
        ("AD-HDFCBK-S", True),
        ("JD-HDFCBK-T", True),
        ("HDFCBK", True),
        ("vm-hdfcbk", True),
        ("VM-HDFCBK-P", False),
        ("+919876543210", False),
        ("VM-HDFCBX", False),
        ("", False),
    ],
)
def test_is_trusted_sms_sender(sender, ok):
    assert is_trusted_sms_sender(sender, ["HDFCBK"]) is ok
