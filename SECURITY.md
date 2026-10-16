# Security Policy

## Supported versions

Security fixes are made on the default branch and included in the next tagged release. The latest
release is the supported version.

## Reporting a vulnerability

Please do not disclose a suspected vulnerability in a public issue.

Use GitHub's
[private vulnerability reporting form](https://github.com/amirimi/contribution-compass/security/advisories/new)
to send a confidential report. Include:

- the affected version or commit;
- reproduction steps or a minimal proof of concept;
- the security impact;
- any known mitigations; and
- whether the issue has been disclosed elsewhere.

The project aims to acknowledge a report within seven days. This is a volunteer-maintained project,
so that target is not a service-level guarantee. The maintainer will coordinate validation,
remediation, credit, and disclosure with the reporter.

## Relevant security boundaries

Reports are especially useful when they concern:

- leakage or misuse of `GITHUB_TOKEN` or other credentials;
- unsafe handling of untrusted GitHub, registry, manifest, or profile content;
- script injection in generated static pages;
- path traversal or unsafe file persistence;
- evidence or recommendation provenance bypasses; or
- unintended data exposure through CLI or MCP responses.

Upstream GitHub, package-registry, dependency, or browser vulnerabilities should be reported to
their respective maintainers unless Contribution Compass introduces the vulnerable behavior.
