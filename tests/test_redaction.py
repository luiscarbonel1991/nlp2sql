"""Connection strings are printed with the password replaced by ***."""

import pytest

from nlp2sql.utils.redaction import mask_database_url


@pytest.mark.parametrize(
    ("url", "masked"),
    [
        ("postgresql://analyst:s3cret@db:5432/warehouse", "postgresql://analyst:***@db:5432/warehouse"),
        ("postgres://analyst:p%40ss@db/warehouse", "postgres://analyst:***@db/warehouse"),
        # Unencoded @ and : in the password: the host starts after the last @
        ("postgresql://analyst:p@ss:w@db/warehouse", "postgresql://analyst:***@db/warehouse"),
        (
            "redshift://analyst:s3cret@c.x.redshift.amazonaws.com:5439/dev",
            "redshift://analyst:***@c.x.redshift.amazonaws.com:5439/dev",
        ),
        (
            "postgresql://db/warehouse?sslmode=require&password=s3cret&x=1",
            "postgresql://db/warehouse?sslmode=require&password=***&x=1",
        ),
        ("analyst:s3cret@db/warehouse", "analyst:***@db/warehouse"),
        # Unencoded / ? and # in the password: urllib ends the host there, and showed the rest
        ("postgresql://analyst:s3/cret@db:5432/warehouse", "postgresql://analyst:***@db:5432/warehouse"),
        ("postgresql://analyst:s3?cret@db:5432/warehouse", "postgresql://analyst:***@db:5432/warehouse"),
        ("postgresql://analyst:s3#cret@db:5432/warehouse", "postgresql://analyst:***@db:5432/warehouse"),
        ("mysql://analyst:1234/s3cret@db/shop", "mysql://analyst:***@db/shop"),
        ("analyst:s3/cret@db/warehouse", "analyst:***@db/warehouse"),
        # Other parameters that hold a secret: libpq's sslpassword and PyMySQL's ssl_key_password
        ("postgresql://analyst@db/warehouse?sslpassword=s3cret", "postgresql://analyst@db/warehouse?sslpassword=***"),
        (
            "mysql://analyst:s3cret@db/shop?ssl_key=/k.pem&ssl_key_password=s3cret&charset=utf8",
            "mysql://analyst:***@db/shop?ssl_key=/k.pem&ssl_key_password=***&charset=utf8",
        ),
        ("postgresql://analyst@db/warehouse?PASSWORD=s3cret", "postgresql://analyst@db/warehouse?PASSWORD=***"),
    ],
)
def test_the_password_is_masked(url, masked):
    assert mask_database_url(url) == masked


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://analyst@db/warehouse",
        "postgresql://db/warehouse",
        "postgresql://db:5432/warehouse?sslmode=require",
        "postgresql://[::1]:5432/warehouse",
        "postgresql://db/warehouse?options=a@b",
        "sqlite:///tmp/x.db",
        "prod",
        "",
    ],
)
def test_urls_without_a_password_are_unchanged(url):
    assert mask_database_url(url) == url


def test_when_in_doubt_it_masks() -> None:
    # host:port with an @ later reads the same as user:password with a / in the password
    assert mask_database_url("postgresql://db:5432/warehouse?application_name=me@corp") == "postgresql://db:***@corp"
