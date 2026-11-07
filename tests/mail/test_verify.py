import pytest

from app.mail.verify import verify_sender

GOOD = (
    "mx.google.com; dkim=pass header.i=@hdfcbank.net header.s=s1; "
    "spf=pass smtp.mailfrom=hdfcbank.net; dmarc=pass (p=REJECT) header.from=hdfcbank.net"
)
DKIM_ONLY = "mx.google.com; dkim=pass header.i=@hdfcbank.net; spf=neutral"
SPF_ONLY = "mx.google.com; spf=pass smtp.mailfrom=hdfcbank.net"
EVIL_DKIM = "mx.google.com; dkim=pass header.i=@attacker.com; dmarc=fail header.from=hdfcbank.net"


@pytest.mark.parametrize(
    ("from_", "auth", "trusted", "reason"),
    [
        ("HDFC Bank <alerts@hdfcbank.net>", [GOOD], True, "ok"),
        ("alerts@mail.hdfcbank.net", [GOOD], True, "ok"),
        ("alerts@hdfcbank.net", [DKIM_ONLY], True, "ok"),
        ("alerts@hdfcbank.net", [SPF_ONLY], False, "auth_failed"),
        ("alerts@hdfcbank.net", [EVIL_DKIM], False, "auth_failed"),
        ("alerts@hdfcbank.net.evil.com", [GOOD], False, "domain_not_allowed"),
        ('"alerts@hdfcbank.net" <evil@attacker.com>', [GOOD], False, "domain_not_allowed"),
        ("alerts@hdfcbank.net", [EVIL_DKIM, GOOD], False, "auth_failed"),
        ("alerts@hdfcbank.net", ["relay.example; dmarc=pass"], False, "no_gmail_auth_results"),
        ("alerts@hdfcbank.net", [], False, "no_gmail_auth_results"),
    ],
)
def test_verify_sender(from_, auth, trusted, reason):
    check = verify_sender(from_, auth, ["hdfcbank.net"])
    assert (check.trusted, check.reason) == (trusted, reason)
