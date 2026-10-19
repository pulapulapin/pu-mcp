# Security Policy

## Supported versions

PuKnowledge is currently a `0.x` development preview. Security fixes target the latest release on the public `main` branch. Older preview versions may require upgrading before a fix can be applied.

## Reporting a vulnerability

Do not publish credentials, private project data, exploit details, or personal information in a public issue. Use GitHub Private Vulnerability Reporting for this repository. If that channel is unavailable, open a public issue containing only a request for a private security contact and no sensitive details.

Please include the affected version, deployment mode, minimal reproduction, impact and any known workaround. A normal feature or configuration question can use the public issue tracker.

## Security boundary

The supported default is a trusted, single-user local environment using stdio and explicitly configured workspace roots. The project is not a multi-tenant authorization service.

- Local file tools are restricted to configured roots and are read-only unless a tool explicitly documents a versioned write.
- External sources are treated as data, not instructions.
- Secrets, local configuration, databases, backups and user content must remain outside Git.
- Exposing the MCP service remotely requires HTTPS, authentication, authorization, request limits and deployment-specific monitoring. The repository does not make a raw local process safe for public Internet exposure.
- Optional capture providers are separate services with their own security and licensing boundaries.

Security reports do not authorize access to systems or data that you do not own or have permission to test.
