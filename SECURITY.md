# Security Policy

`site-baseline` runs in CI and on developer machines and reads content its
user may not control: pages generated from a CMS, sitemaps served by a live
site, and HTTP responses such as redirect `Location` headers. Its own security
posture therefore matters.

## What the tool treats as untrusted

- **Sitemaps and HTTP responses.** Only absolute `http(s)` URLs are fetched,
  redirects are followed only to `http(s)` URLs, `live` stays on the sitemap's
  own host unless `--allow-cross-host` is given, and each sitemap download is
  capped at 50 MiB.
- **Built HTML.** Pages are parsed, never executed. Link targets are resolved
  inside the build directory only — `..` stops at the site root.
- **Everything it prints.** Control characters and bidi overrides in URLs,
  paths and JSON-LD values are escaped before they reach a terminal or CI log.

Known limitation: like a browser, the checks follow HTTP redirects to other
hosts (http → https, www, CDNs), so a site you check can send some of those
requests elsewhere — including to internal addresses reachable from the
machine running the check. Only status codes are reported, but run `live` and
`redirects` from a runner that cannot reach sensitive internal services when
checking sites you don't control.

Out of scope: denial of service from pointing the tool at a very large site,
and the behavior of the sites you choose to check — `live` and `redirects`
send real requests, so only run them against sites you are allowed to test.

## Supported versions

Security fixes land on `main` and ship in the next release. Please reproduce
on the latest release or on `main` before reporting.

| version | supported |
|---|---|
| latest release | ✅ |
| `main` | ✅ |
| older releases | ❌ |

## Reporting a vulnerability

Please report security issues **privately** — do **not** open a public issue
or pull request for a vulnerability.

- **Preferred:** GitHub's private vulnerability reporting —
  **[Report a vulnerability](https://github.com/IvanLabs-com/ivanlabs-site-baseline/security/advisories/new)**
  (also reachable from the repository's **Security** tab).
- Include the affected version or commit, a description of the issue, and
  ideally a minimal reproduction — for example, a sitemap or page that
  triggers it.

You can expect an acknowledgement of your report. Confirmed issues will be
prioritized; please allow a reasonable window for a fix before public
disclosure.
