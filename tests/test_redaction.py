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
    ],
)
def test_the_password_is_masked(url, masked):
    assert mask_database_url(url) == masked


@pytest.mark.parametrize(
    "url", ["postgresql://analyst@db/warehouse", "postgresql://db/warehouse", "sqlite:///tmp/x.db"]
)
def test_urls_without_a_password_are_unchanged(url):
    assert mask_database_url(url) == url
