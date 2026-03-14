# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public issue**
2. Email: **qulisun@gmail.com**
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

You will receive a response within 48 hours. We will work with you to understand and address the issue before any public disclosure.

## Security Measures

Fry TFTP Server includes several built-in security features:

- **Path traversal protection** — all paths canonicalized and validated
- **Symlink policy** — configurable, disabled by default
- **IP-based ACL** — whitelist/blacklist with CIDR support
- **Per-IP rate limiting** — configurable requests per window
- **Per-IP session limits** — prevent resource exhaustion
- **Input validation** — packet parsing never panics on arbitrary input (fuzz-tested)
- **No shell execution** — filenames are never passed to shell commands
