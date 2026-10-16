# Changelog

All notable changes to ivanlabs-site-baseline are documented here. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-16

### Security

- `live`, `redirects` and `links --check-external` now fetch only absolute
  `http(s)` URLs and follow redirects only to `http(s)` URLs. Previously a
  sitemap index could list a `file://` "sitemap", which was opened and its
  contents used, and `ftp://` targets were followed.
- `live` only fetches URLs on the sitemap's own host, as the sitemaps.org
  protocol requires; other hosts are reported as `SKIPPED (different host)`.
  Use `--allow-cross-host` to check them anyway.
- Sitemap downloads are capped at 50 MiB, the protocol's own limit, instead of
  being read into memory without a bound.
- Everything printed that came from a page, sitemap or server has its control
  characters and bidi overrides escaped, so hostile content can no longer
  inject terminal escape sequences or hide lines in CI logs.
- `links`: `..` — including percent-encoded `%2e%2e` — stops at the site root,
  so a link can no longer make the audit test for files outside the build.

### Fixed

- `links` resolves relative links from the page's own folder instead of the
  site root (`post.html` linked from `blog/index.html` was reported broken),
  treats protocol-relative `//host/...` links as URLs, matches `mailto:` and
  friends case-insensitively, and reports links with an unknown scheme.
- `schema` reports deeply nested JSON-LD as a parse error instead of crashing,
  and now also finds entity artifacts inside arrays such as `sameAs`.
- `live` decodes `&amp;` in sitemap URLs and no longer crashes when a `<loc>`
  is not an http(s) URL.
- `redirects` rejects a `--base` that is not an http(s) URL.

### Added

- `live --allow-cross-host`.
- Unit tests (standard library only) and a CI workflow; security policy.

## [0.1.0] - 2026-09-09

### Added

- `links`, `schema`, `redirects` and `live` commands.

[Unreleased]: https://github.com/IvanLabs-com/ivanlabs-site-baseline/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/IvanLabs-com/ivanlabs-site-baseline/releases/tag/v0.2.0
[0.1.0]: https://github.com/IvanLabs-com/ivanlabs-site-baseline/commit/c3c9d12
