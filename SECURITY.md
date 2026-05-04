# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Dominian, please report it responsibly.

**Do not** open a public GitHub issue. Instead:

1. Email the maintainers with a description of the vulnerability.
2. Include steps to reproduce, if possible.
3. We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Scope

Dominian is a local-first code intelligence tool. It:

- **Does not** make network requests during normal operation
- **Does not** transmit code or analysis results to external servers
- **Does not** require API keys or authentication for core functionality
- **Stores** all data in a local SQLite database (`.dominian/agentgraph.db`)

### In Scope

- SQL injection or database corruption vectors
- Path traversal vulnerabilities in file scanning
- Arbitrary code execution via malicious source files
- MCP server authentication/authorization issues

### Out of Scope

- Vulnerabilities in dependencies (tree-sitter, networkx, etc.) — report to upstream
- Denial of service via extremely large files — Dominian has resource limits
- Social engineering attacks

## MCP Server Security

The MCP server runs locally and communicates via stdio or SSE. When using SSE transport:

- The server binds to `0.0.0.0` by default. Restrict to `127.0.0.1` if only local access is needed: `dominian-mcp --transport sse --host 127.0.0.1`
- No authentication is built in. If you expose the server on a network, use a reverse proxy with authentication.
- The server has full read/write access to the SQLite database and can scan any directory accessible to the process user.

## Versions

Security fixes are released for the latest minor version only. Update to the latest version to receive security patches.
