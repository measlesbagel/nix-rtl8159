"""Open an issue when Realtek publishes an r8152 Linux driver newer than the newest v* tag.

Reads Realtek's download listing only; the tarball sits behind a CAPTCHA and is
never fetched. Prints what it would do unless --apply is given.
"""

import argparse
import json
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass

# The listing page's own scripts called this JSON endpoint until 2026.
LISTING_URL = "https://www.realtek.com/Download/ListAllDownloadItem?cate_id=585"
DOWNLOAD_PAGE = "https://www.realtek.com/Download/List?cate_id=585"
USER_AGENT = "nix-rtl8159-release-watch (+https://github.com/measlesbagel/nix-rtl8159)"
MARKER = "<!-- realtek-watch -->"

VERSION = re.compile(r"\d+(?:\.\d+)+")
TARBALL = re.compile(r"r8152-v(\d+(?:\.\d+)+)\.tar\.\w+")
TAG = re.compile(r"v(\d+(?:\.\d+)+)-(\d+)")
DATE = re.compile(r"\d{4}/\d{2}/\d{2}")


def key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


@dataclass(frozen=True)
class Release:
    version: str
    filename: str
    published: str | None


@dataclass(frozen=True)
class Known:
    version: str
    label: str


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str


@dataclass(frozen=True)
class Nothing:
    reason: str


@dataclass(frozen=True)
class Create:
    title: str
    body: str


@dataclass(frozen=True)
class Update:
    number: int
    title: str
    body: str


Action = Nothing | Create | Update


def fetch_listing() -> dict:
    request = urllib.request.Request(LISTING_URL, headers={"User-Agent": USER_AGENT})
    error: Exception | None = None
    for attempt in range(3):
        if attempt:
            time.sleep(5 * attempt)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (OSError, ValueError) as err:
            error = err
    raise SystemExit(f"error: Realtek listing unreachable or not JSON: {error!r}")


def latest_release(listing: dict) -> Release:
    if listing.get("Pass") is not True:
        raise SystemExit(f"error: Realtek listing reports Pass={listing.get('Pass')!r}")
    found = []
    try:
        for group in listing["Data"]["DownloadItems"].values():
            for item in group:
                match = TARBALL.fullmatch(item["Name"])
                if not match:
                    continue
                if item["Version"] != match[1]:
                    raise SystemExit(
                        f"error: {item['Name']} is listed as Version {item['Version']!r}"
                    )
                published = item.get("UpdateTime")
                found.append(
                    Release(
                        match[1],
                        item["Name"],
                        published if DATE.fullmatch(str(published)) else None,
                    )
                )
    except (KeyError, TypeError, AttributeError) as err:
        raise SystemExit(f"error: Realtek listing changed shape: {err!r}") from err
    if not found:
        raise SystemExit("error: no r8152-v<version>.tar.* in Realtek's listing")
    return max(found, key=lambda release: key(release.version))


def newest_tag() -> Known:
    listed = subprocess.run(
        ["git", "tag", "--list", "v*"], check=True, capture_output=True, text=True
    ).stdout.split()
    tags = [
        (key(match[1]), int(match[2]), tag)
        for tag in listed
        if (match := TAG.fullmatch(tag))
    ]
    if not tags:
        raise SystemExit("error: no v<version>-<n> tag found; were tags fetched?")
    _, _, tag = max(tags)
    return Known(TAG.fullmatch(tag)[1], tag)


def gh(*args: str, stdin: str | None = None) -> str:
    done = subprocess.run(
        ["gh", *args], check=False, input=stdin, capture_output=True, text=True
    )
    if done.returncode:
        raise SystemExit(
            f"error: gh {' '.join(args[:2])} failed: {done.stderr.strip()}"
        )
    return done.stdout


def open_issues() -> list[Issue]:
    fields = "number,title,body"
    rows = json.loads(
        gh("issue", "list", "--state", "open", "--limit", "100", "--json", fields)
    )
    return [Issue(row["number"], row["title"], row["body"] or "") for row in rows]


def write_issue(command: list[str], title: str, body: str) -> str:
    return gh("issue", *command, "--title", title, "--body-file", "-", stdin=body)


def render(latest: Release, known: Known) -> tuple[str, str]:
    published = f", published {latest.published}" if latest.published else ""
    title = f"Realtek r8152 {latest.version} is out"
    body = (
        f"{MARKER}\n"
        f"Realtek lists r8152 **{latest.version}** (`{latest.filename}`{published}). "
        f"The newest release here is `{known.label}`.\n\n"
        f"Its tarball is behind a CAPTCHA, so the update is manual: download it from "
        f"{DOWNLOAD_PAGE} and follow Updating in the README.\n\n"
        "Filed by the `realtek-watch` workflow.\n"
    )
    return title, body


def plan(latest: Release, known: Known, issues: list[Issue]) -> Action:
    title, body = render(latest, known)
    existing = next((issue for issue in issues if MARKER in issue.body), None)
    if existing is None:
        return Create(title, body)
    if (existing.title, existing.body) == (title, body):
        return Nothing(f"issue #{existing.number} already says this")
    return Update(existing.number, title, body)


def apply(action: Action, dry_run: bool) -> None:
    would = "would " if dry_run else ""
    match action:
        case Nothing(reason):
            print(reason)
        case Create(title, body):
            print(f"{would}create an issue:")
            print_issue(title, body)
            if not dry_run:
                print(write_issue(["create"], title, body).strip())
        case Update(number, title, body):
            print(f"{would}update issue #{number}:")
            print_issue(title, body)
            if not dry_run:
                write_issue(["edit", str(number)], title, body)
                print(f"updated #{number}")


def print_issue(title: str, body: str) -> None:
    print(f"  title: {title}")
    print("  body:")
    for line in body.splitlines():
        print(f"    | {line}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create or edit the issue instead of printing it",
    )
    parser.add_argument(
        "--known-version",
        metavar="X.Y.Z",
        help="compare against this instead of the newest v* tag, to exercise the issue path",
    )
    args = parser.parse_args()

    latest = latest_release(fetch_listing())
    print(
        f"realtek: {latest.version} ({latest.filename}, published {latest.published or 'unknown'})"
    )

    if args.known_version:
        if not VERSION.fullmatch(args.known_version):
            raise SystemExit(
                f"error: --known-version {args.known_version!r} is not X.Y.Z"
            )
        known = Known(args.known_version, f"{args.known_version} (--known-version)")
    else:
        known = newest_tag()
    print(f"known:   {known.label}")

    if key(latest.version) <= key(known.version):
        print("up to date")
        return
    print(f"newer:   {latest.version} > {known.version}")
    apply(plan(latest, known, open_issues()), dry_run=not args.apply)


if __name__ == "__main__":
    main()
