# Security Policy

## Supported Versions

The following versions of nlp2sql are currently being supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x:                |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

1. **DO NOT** open a public GitHub issue for security vulnerabilities
2. Report it privately through [GitHub's private vulnerability reporting](https://github.com/luiscarbonel1991/nlp2sql/security/advisories/new) (Security tab > Report a vulnerability)

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution Target**: Within 30 days for critical issues

### What to Expect

- **Accepted**: We will work on a fix and coordinate disclosure with you
- **Declined**: We will explain why the report does not qualify as a security vulnerability

### Scope

Security issues relevant to this project include:

- SQL injection vulnerabilities in generated queries
- Credential exposure in logs or error messages
- Insecure handling of database connection strings
- Vulnerabilities in AI provider API key management
- Dependencies with known security issues

### Out of Scope

- Issues in third-party AI providers (OpenAI, Anthropic, Google)
- Vulnerabilities requiring physical access to the server
- Social engineering attacks

## Security Best Practices

When using nlp2sql in production:

1. **Never commit `.env` files** - Use environment variables or secret management
2. **Connect with a database user that can only read** - nlp2sql checks every query it executes and runs it in a read-only transaction, but the database's own permissions are the guarantee that holds if a check is ever bypassed. In PostgreSQL:

   ```sql
   CREATE ROLE nlp2sql_reader LOGIN PASSWORD '...';
   GRANT CONNECT ON DATABASE mydb TO nlp2sql_reader;
   GRANT USAGE ON SCHEMA public TO nlp2sql_reader;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO nlp2sql_reader;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO nlp2sql_reader;
   ALTER ROLE nlp2sql_reader SET default_transaction_read_only = on;
   ```

   Do not use a superuser: it can read server files (`pg_read_file`) and end other sessions.
3. **Enable query validation** to prevent dangerous SQL execution
4. **Review generated SQL** before executing on sensitive data
5. **Keep dependencies updated** - Run `uv sync` regularly
