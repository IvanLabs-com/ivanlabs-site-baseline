# ivanlabs-site-baseline

[![CI](https://github.com/IvanLabs-com/ivanlabs-site-baseline/actions/workflows/ci.yml/badge.svg)](https://github.com/IvanLabs-com/ivanlabs-site-baseline/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/IvanLabs-com/ivanlabs-site-baseline?sort=semver)](https://github.com/IvanLabs-com/ivanlabs-site-baseline/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Validation toolkit for static sites: link integrity, structured-data health, redirect maps, and live sitemap checks. Pure Python, zero dependencies.**

These are the scripts [IvanLabs](https://ivanlabs.com) uses in production to validate its own platform — extracted from real use, not built as a demo. They implement the mechanical layers of the [pre-migration baseline](https://ivanlabs.com/blog/pre-migration-baseline-what-to-capture/) and the post-deploy validation described in the [platform migration checklist](https://ivanlabs.com/blog/platform-migration-checklist/): the checks that catch broken links, corrupted JSON-LD, and mis-mapped redirects *before* search engines and answer engines find them.

## Install

```bash
pip install .
# or run without installing:
python -m sitebaseline --help
```

Python ≥ 3.9, standard library only.

## Commands

### `links` — link audit of a built site

Walks every `.html` file in a build directory, resolves every internal `href`/`src` against the filesystem, and reports broken targets. Optionally live-checks every external URL.

Links resolve the way a browser resolves them: relative links from the page's own folder, root-relative links from the site root. `..` (also percent-encoded, as `%2e%2e`) stops at the site root, so a link can never point the audit at files outside the build directory. Links with an unknown URL scheme (a typo such as `htps://`) are reported as broken.

```bash
site-baseline links public/ --host example.com
site-baseline links public/ --host example.com --check-external
```

### `schema` — JSON-LD health check

Extracts every `application/ld+json` block, verifies it parses, and scans all string values for HTML-entity artifacts (`&#x2F;`, `&amp;`, …) — the classic symptom of template auto-escaping leaking into `<script>` content, where browsers do **not** entity-decode. Also flags `Person`/`Organization` nodes missing `sameAs`.

```bash
site-baseline schema public/
```

### `redirects` — redirect-map verification

Given a file of `source target` pairs, verifies each source answers with a **single-hop permanent redirect** (301/308) to exactly the mapped target, and that the target returns 200. Chains, temporary redirects, and mis-targets — the redirect failures that quietly destroy search visibility during migrations — all fail loudly.

```bash
site-baseline redirects examples/redirects.txt --base https://example.com
```

```text
# examples/redirects.txt — relative paths resolve against --base
/old-section/page/   /new-section/page/
/legacy-topic/       https://example.com/topics/new-topic/
```

### `live` — sitemap-wide 200 check

Fetches a sitemap (or sitemap index, recursively) and verifies every `<loc>` returns 200. The fastest "did the deploy break anything crawlers know about" signal.

```bash
site-baseline live https://example.com/sitemap_index.xml
site-baseline live https://example.com/sitemap.xml --allow-cross-host
```

Sitemap content is treated as untrusted input. Only `http(s)` URLs are ever fetched, and by default only URLs on the sitemap's own host — the [sitemaps.org rule](https://www.sitemaps.org/protocol.html#location) — so a compromised sitemap cannot steer a CI runner to local files or internal services. URLs on other hosts are reported as `SKIPPED (different host)` and count as findings; `--allow-cross-host` checks them anyway. Each sitemap file is capped at 50 MiB, the protocol's own limit.

## Exit codes

`0` clean · `1` findings · `2` usage/input error — so every command drops straight into CI:

```yaml
- run: site-baseline links public/ --host example.com
- run: site-baseline schema public/
```

## Security

The checks read content you may not control — pages built from a CMS, sitemaps served by a live site, redirect `Location` headers — so they treat all of it as untrusted:

- only absolute `http(s)` URLs are requested, and redirects are only followed to `http(s)` URLs;
- `live` stays on the sitemap's own host unless you pass `--allow-cross-host`;
- downloads are size-capped, and malformed or deeply nested input is reported as a finding instead of crashing the run;
- anything printed that came from a page or a server has its control characters escaped, so it cannot rewrite your terminal or hide lines in CI logs.

Please report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

## Development

```bash
python -m unittest discover -s tests -v   # standard library only; no network beyond 127.0.0.1
```

Notable changes are listed in [CHANGELOG.md](CHANGELOG.md).

## Why these checks

Migrations and redesigns rarely fail loudly. They fail as a 4% redirect-mapping error rate, a template that silently lost its structured data, an entity-escaped URL inside JSON-LD that every browser renders fine and every parser reads as garbage. Each command here exists because that failure happened somewhere real. The reasoning is documented in the [Migrations & Redesign Risk](https://ivanlabs.com/topics/migrations-redesign-risk/) field notes.

## License

MIT © [Ivan Popov](https://ivanlabs.com/about/), IvanLabs
