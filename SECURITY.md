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
2. Email the maintainers directly at [security contact email]
3. Or use GitHub's private vulnerability reporting feature (Security tab > Report a vulnerability)

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
2. **Use read-only database credentials** when possible
3. **Enable query validation** to prevent dangerous SQL execution
4. **Review generated SQL** before executing on sensitive data
5. **Keep dependencies updated** - Run `uv sync` regularly
