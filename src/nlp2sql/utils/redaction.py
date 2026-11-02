"""Hide credentials before a connection string is printed or logged."""

import re
from urllib.parse import urlsplit

MASK = "***"

# The PostgreSQL repository also reads a password from the query string (?password=...)
_QUERY_PASSWORD = re.compile(r"(?i)((?:^|&)password=)[^&]*")


def mask_database_url(url: str) -> str:
    """Return ``url`` with its password replaced by ``***``; everything else is kept as typed.

    Handles the password in the user info (``user:secret@host``), including passwords
    that contain ``@`` or ``:``, and in a ``password`` query parameter. A URL without a
    scheme (``user:secret@host/db``) is masked too, since that is a common typo.
    """
    has_scheme = "://" in url
    parts = urlsplit(url if has_scheme else f"//{url}")

    netloc = parts.netloc
    userinfo, at, host = netloc.rpartition("@")
    if at and ":" in userinfo:
        netloc = f"{userinfo.partition(':')[0]}:{MASK}@{host}"
    query = _QUERY_PASSWORD.sub(rf"\g<1>{MASK}", parts.query)

    if (netloc, query) == (parts.netloc, parts.query):
        return url
    masked = parts._replace(netloc=netloc, query=query).geturl()
    return masked if has_scheme else masked[2:]
