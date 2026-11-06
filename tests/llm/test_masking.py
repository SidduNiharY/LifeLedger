import pytest

from app.llm.masking import mask_for_cloud


@pytest.mark.parametrize(
    ("text", "owners", "expected"),
    [
        ("to 9876543210@ybl", [], "to [PHONE]@ybl"),
        ("call +91 98765 43210", [], "call [PHONE]"),
        ("Acct 123456781234 debited", [], "Acct XX1234 debited"),
        ("UPI Ref 432112345678", [], "UPI Ref XX5678"),
        ("A/c XX1234", [], "A/c XX1234"),
        ("Rs.1,02,345.67 on 05-11-2026", [], "Rs.1,02,345.67 on 05-11-2026"),
        ("to swiggy@icici", [], "to swiggy@icici"),
        ("PAN ABCDE1234F mail me@example.com", [], "PAN [PAN] mail [EMAIL]"),
        ("from SIDDU NIHAR via IMPS", ["Siddu Nihar"], "from [NAME] via IMPS"),
    ],
)
def test_mask_for_cloud(text: str, owners: list[str], expected: str):
    assert mask_for_cloud(text, owners) == expected
