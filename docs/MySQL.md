# MySQL and MariaDB Support

`nlp2sql` reads and queries MySQL and MariaDB with the same DSL it uses for PostgreSQL. It is tested against MySQL 8.4 and MariaDB 11.4.

## Install

The driver, PyMySQL, is an optional dependency:

```bash
pip install 'nlp2sql[mysql]'
```

The extra also installs `cryptography`. MySQL 8 signs in with `caching_sha2_password`, which needs it when the connection has no TLS.

## Connect

```python
import nlp2sql
from nlp2sql import ProviderConfig

nlp = await nlp2sql.connect(
    "mysql://reader:password@localhost:3306/shop",
    provider=ProviderConfig(provider="openai", api_key="sk-..."),
)

result = await nlp.ask("How many orders did each store receive last month?", validate=True)
```

These URL schemes are the same adapter:

```bash
mysql://user:password@host:3306/database
mariadb://user:password@host:3306/database
mysql+pymysql://user:password@host:3306/database
```

The server kind is detected on connect, not from the scheme.

From the CLI:

```bash
nlp2sql inspect --database-url mysql://reader:password@localhost:3306/shop
nlp2sql query --database-url mysql://reader:password@localhost:3306/shop --question "How many users are there?"
```

## A schema is a database

MySQL has no schemas inside a database. `nlp2sql` reads the database named in the URL, so the URL must name one. Leave `schema` at its default. A `schema` other than the default names another database of the same server:

```python
nlp = await nlp2sql.connect("mysql://reader:password@localhost:3306/shop", provider=..., schema="analytics")
```

Views are not listed, as with PostgreSQL. The row count of a table is the storage engine's estimate (`information_schema.TABLES.TABLE_ROWS`).

## URL parameters

Only these query parameters are accepted. They are passed to PyMySQL by the same names:

| Parameter | Meaning |
|---|---|
| `charset` | Connection character set. Default `utf8mb4` |
| `connect_timeout`, `read_timeout`, `write_timeout` | Seconds |
| `unix_socket` | Path of a local socket to use instead of the host |
| `ssl_ca`, `ssl_cert`, `ssl_key`, `ssl_key_password` | TLS certificate files |
| `ssl_verify_cert`, `ssl_verify_identity` | `true` or `false` |
| `ssl_disabled` | `true` turns TLS off |

```bash
mysql://reader:password@db.example.com:3306/shop?ssl_ca=/etc/ssl/certs/ca.pem&ssl_verify_identity=true
```

Any other parameter raises `ConfigurationException`. Some PyMySQL options are dangerous in a URL that a caller supplies: `local_infile` lets the server ask for files of the client machine, `init_command` runs SQL on connect, and `read_default_file` reads a local file.

## What protects the database

1. **The safety check** reads the query the way MySQL and MariaDB do. It rejects anything that is not a single `SELECT`, `WITH` or `EXPLAIN`, comments that the server runs (`/*! ... */`, `/*+ ... */`), `INTO OUTFILE`, and functions such as `load_file`, `sleep` and `benchmark`.
2. **Every connection is read-only** for its whole session (`SET SESSION TRANSACTION READ ONLY`). The server refuses a write with error 1792.
3. **One statement per query.** The driver does not ask the server for multiple statements, so a second statement after `;` is a syntax error.
4. **A statement timeout**: `max_execution_time` on MySQL, `max_statement_time` on MariaDB. MySQL's does not interrupt every statement, so the client also stops waiting 5 seconds after the limit.

The database user's own permissions are the guard that still holds if one of these is bypassed. Create a user that can only read:

```sql
CREATE USER 'nlp2sql_reader'@'%' IDENTIFIED BY '...';
GRANT SELECT ON shop.* TO 'nlp2sql_reader'@'%';
```

This user cannot write, create tables (temporary ones included), write files with `INTO OUTFILE`, or read the `mysql` system database. Do not grant `FILE`: it lets a query read and write files on the database server.

The safety check rejects a string literal that contains a backslash before a quote (`'it\'s'`), because its end depends on the server's SQL mode. Write a quote inside a string as `''`.

## SQL dialect

The prompt tells the model the rules that differ from PostgreSQL. Two PostgreSQL habits do not fail on MySQL; they return a wrong answer:

| PostgreSQL | What MySQL and MariaDB do | Write instead |
|---|---|---|
| `"order_date"` | A string literal: returns the text `order_date` | `` `order_date` `` |
| `first_name \|\| ' ' \|\| last_name` | Logical OR: returns `0` or `1` | `CONCAT(first_name, ' ', last_name)` |

The others fail with a syntax error, and `validate()` and `ask()` report them as warnings before the query runs:

| PostgreSQL | MySQL and MariaDB |
|---|---|
| `value::int` | `CAST(value AS SIGNED)` |
| `ILIKE` | `LIKE`, which ignores case with the default collations |
| `DATE_TRUNC('month', d)` | `DATE_FORMAT(d, '%Y-%m-01')`, `YEAR(d)`, `MONTH(d)` |
| `d - INTERVAL '1 month'` | `d - INTERVAL 1 MONTH` |
| `STRING_AGG(col, ', ')` | `GROUP_CONCAT(col SEPARATOR ', ')` |
| `FULL OUTER JOIN` | `LEFT JOIN ... UNION ... RIGHT JOIN` |
| `DISTINCT ON (...)` | `ROW_NUMBER() OVER (...)` in a subquery |
| `ORDER BY col NULLS LAST` | `ORDER BY col IS NULL, col` |
| `COUNT(*) FILTER (WHERE ...)` | `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` |
| `generate_series()` | Not available |

MySQL also requires every selected column that is not inside an aggregate to be in `GROUP BY` (`ONLY_FULL_GROUP_BY`, on by default). MariaDB does not by default.

With `repair=True`, a failed query is classified by the server's error number. An unknown column, an unknown table, a syntax error or a timeout goes back to the model with a hint. A refused write or a permission error does not.

## Not supported

- A server with `ANSI_QUOTES` or `NO_BACKSLASH_ESCAPES` in its SQL mode has not been tested. With `ANSI_QUOTES`, double quotes are names, not strings, and the safety check reads them as strings.
- MySQL 5.7 and MariaDB before 10.11 have not been tested.
- The pgvector example repository is PostgreSQL only.

## Local test servers

```bash
cd docker
docker compose up -d mysql mariadb
```

MySQL listens on 3306 and MariaDB on 3307, both with the e-commerce schema of the PostgreSQL test database:

```bash
mysql://testuser:testpass@127.0.0.1:3306/testdb
mariadb://testuser:testpass@127.0.0.1:3307/testdb
```
