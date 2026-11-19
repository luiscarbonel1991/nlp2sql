"""Hide credentials before a connection string is printed, logged or returned."""

import re

MASK = "***"

# For a URL that urllib cannot split. It names no value: the bad port can be a piece of the password
UNREADABLE_URL = (
    "The {database} URL cannot be read: check the host and the port. Special characters in the "
    "password must be URL-encoded (/ as %2F, ? as %3F, # as %23, @ as %40)"
)

# Query parameters that hold a secret: password (PostgreSQL), sslpassword (libpq) and
# ssl_key_password (PyMySQL)
_QUERY_SECRET = re.compile(r"(?i)((?:^|&)[^=&]*password=)[^&]*")
_AUTHORITY_END = re.compile(r"[/?#]")


def _split_user_info(body: str) -> tuple[str, str]:
    """Split what follows ``scheme://`` into the user info and the rest, which starts at ``@``.

    The user info ends at the last ``@`` of the authority, so a password can hold ``@``
    and ``:``. A password with a ``/``, ``?`` or ``#`` that was not URL-encoded ends the
    authority early: ``user:pa/ss@host/db`` reads as host ``user`` and port ``pa``. So when
    the authority has a ``:`` and no ``@``, and an ``@`` comes later, the user info runs to
    the last ``@`` of the whole string. A URL without credentials that has an ``@`` in its
    path or query is masked by mistake; that is better than showing a password.
    """
    end = _AUTHORITY_END.search(body)
    authority = body[: end.start()] if end else body

    user_info, at, _ = authority.rpartition("@")
    if not at and ":" in authority and "@" in body:
        user_info, at, _ = body.rpartition("@")
    return (user_info, body[len(user_info) :]) if at else ("", body)


def mask_database_url(url: str) -> str:
    """Return ``url`` with its password replaced by ``***``; everything else is kept as typed.

    Handles the password in the user info (``user:secret@host``), including passwords
    that contain ``@``, ``:``, ``/``, ``?`` or ``#``, and in a query parameter whose name
    ends in ``password``. A URL without a scheme (``user:secret@host/db``) is masked too,
    since that is a common typo.
    """
    scheme, separator, body = url.partition("://")
    if not separator:
        scheme, body = "", url

    user_info, rest = _split_user_info(body)
    user, colon, _ = user_info.partition(":")
    if colon:
        user_info = f"{user}:{MASK}"

    location, question, query = rest.partition("?")
    query = _QUERY_SECRET.sub(rf"\g<1>{MASK}", query)

    return f"{scheme}{separator}{user_info}{location}{question}{query}"
