# Security Policy

## Supported versions

This project is pre-1.0; only the latest release / `main` receives fixes.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Preferred: use GitHub's private vulnerability reporting —
**Security → Report a vulnerability** on the repository.

Alternatively, email **strebkov.vladislav@gmail.com** with:

- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- any suggested fix.

You'll get an acknowledgement as soon as possible. Please allow time for a fix
before any public disclosure.

## Scope notes

- The server reads API keys (OpenAI/Groq/Gemini) from a local `.env`; it never
  logs or transmits them except to the corresponding provider.
- The `url` input downloads remote content; private/loopback addresses are
  blocked to mitigate SSRF. Report any bypass.
