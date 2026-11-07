# Security & privacy

Gunshot listens to the keyboard system-wide, so it's held to a strict standard:

- It reacts only to *that* a key was pressed. It never records, stores or
  transmits *which* keys were pressed.
- It makes no network connections.
- Settings are stored locally only (`%APPDATA%\Gunshot` or
  `~/Library/Application Support/Gunshot`).

Official downloads come only from this repository's **Releases** page, with
SHA-256 checksums in `SHA256SUMS.txt`. Don't trust copies from anywhere else.

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Use GitHub's
private reporting instead: **Security → Report a vulnerability** on this
repository. You'll get a reply as soon as possible.
