import re
from collections.abc import Sequence
from dataclasses import dataclass
from email.utils import parseaddr


@dataclass(frozen=True)
class SenderCheck:
    trusted: bool
    reason: str


def verify_sender(
    from_header: str,
    auth_results: list[str],
    allowed_domains: Sequence[str],
) -> SenderCheck:
    # Rule 1: From address comes from email.utils.parseaddr, and its domain must
    # equal or be a subdomain of an allowed domain (else "domain_not_allowed").
    _, addr = parseaddr(from_header)
    if not addr or "@" not in addr:
        return SenderCheck(trusted=False, reason="domain_not_allowed")

    from_domain = addr.rpartition("@")[2].lower().strip()
    if not from_domain:
        return SenderCheck(trusted=False, reason="domain_not_allowed")

    domain_allowed = any(
        from_domain == allowed.lower().strip()
        or from_domain.endswith("." + allowed.lower().strip())
        for allowed in allowed_domains
        if allowed.strip()
    )
    if not domain_allowed:
        return SenderCheck(trusted=False, reason="domain_not_allowed")

    # Rule 2: Only auth_results[0] is used, and its authserv-id must be mx.google.com
    # (else "no_gmail_auth_results").
    if not auth_results:
        return SenderCheck(trusted=False, reason="no_gmail_auth_results")

    first_auth = auth_results[0].strip()
    authserv_part = first_auth.split(";", 1)[0].strip()
    authserv_id = authserv_part.split()[0] if authserv_part else ""
    if authserv_id != "mx.google.com":
        return SenderCheck(trusted=False, reason="no_gmail_auth_results")

    # Rule 3: Trusted if it has dmarc=pass, or dkim=pass with header.i=@<d>/header.d=<d>
    # where <d> equals or is a parent of the From domain. Otherwise "auth_failed".
    # Trusted -> reason "ok".
    if re.search(r"(?:^|[\s;])dmarc\s*=\s*pass\b", first_auth, re.IGNORECASE):
        return SenderCheck(trusted=True, reason="ok")

    clauses = first_auth.split(";")[1:]
    for clause in clauses:
        if re.search(r"(?:^|\s)dkim\s*=\s*pass\b", clause, re.IGNORECASE):
            for match in re.finditer(r"header\.[id]\s*=\s*([^\s;]+)", clause, re.IGNORECASE):
                val = match.group(1).strip("\"'")
                if val.startswith("@"):
                    d = val[1:].lower()
                elif "@" in val:
                    d = val.split("@")[-1].lower()
                else:
                    d = val.lower()

                if d and (from_domain == d or from_domain.endswith("." + d)):
                    return SenderCheck(trusted=True, reason="ok")

    return SenderCheck(trusted=False, reason="auth_failed")
