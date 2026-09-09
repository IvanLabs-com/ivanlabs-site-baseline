"""Command-line interface for ivanlabs-site-baseline."""

import argparse
import sys

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="site-baseline",
        description=(
            "Validation toolkit for static sites: link integrity, JSON-LD health, "
            "redirect maps, and live sitemap checks."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_links = sub.add_parser("links", help="audit internal/external links in a built site directory")
    p_links.add_argument("root", help="path to the built site (e.g. public/)")
    p_links.add_argument("--host", action="append", required=True,
                         help="hostname treated as internal (repeatable), e.g. --host example.com")
    p_links.add_argument("--check-external", action="store_true",
                         help="also live-check every external URL over HTTP")

    p_schema = sub.add_parser("schema", help="validate JSON-LD blocks in a built site directory")
    p_schema.add_argument("root", help="path to the built site (e.g. public/)")

    p_redir = sub.add_parser("redirects", help="verify a redirect map against the live site")
    p_redir.add_argument("map", help="file of 'source target' pairs, one per line")
    p_redir.add_argument("--base", required=True, help="base URL, e.g. https://example.com")

    p_live = sub.add_parser("live", help="verify every sitemap URL returns 200")
    p_live.add_argument("sitemap", help="sitemap or sitemap-index URL")

    args = parser.parse_args(argv)

    if args.command == "links":
        from . import links
        return links.audit(args.root, [h.lower() for h in args.host], args.check_external)
    if args.command == "schema":
        from . import schema
        return schema.audit(args.root)
    if args.command == "redirects":
        from . import redirects
        return redirects.verify(args.map, args.base)
    if args.command == "live":
        from . import live
        return live.verify(args.sitemap)
    return 2


if __name__ == "__main__":
    sys.exit(main())
