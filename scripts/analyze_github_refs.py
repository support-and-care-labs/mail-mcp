#!/usr/bin/env python3
#
# Copyright 2025 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Analyze GitHub references in Maven mailing list emails.

This script queries Elasticsearch directly to extract and categorize
GitHub repository and PR/issue references from email archives.

Usage:
    poetry run python scripts/analyze_github_refs.py [--days N] [--es-url URL]

Prerequisites:
    - Elasticsearch must be running with indexed email data
    - Run: docker compose up -d elasticsearch

Examples:
    # Analyze last 90 days (default)
    poetry run python scripts/analyze_github_refs.py

    # Analyze last 30 days
    poetry run python scripts/analyze_github_refs.py --days 30

    # Use custom Elasticsearch URL
    poetry run python scripts/analyze_github_refs.py --es-url http://localhost:59200
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.request import Request, urlopen


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze GitHub references in Maven mailing list archives"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days to analyze (default: 90)",
    )
    parser.add_argument(
        "--es-url",
        default="http://localhost:59200",
        help="Elasticsearch URL (default: http://localhost:59200)",
    )
    parser.add_argument(
        "--index",
        default="maven-dev",
        help="Elasticsearch index name (default: maven-dev)",
    )
    return parser.parse_args()


def fetch_all_emails(es_url: str, index: str, since_date: str) -> list:
    """
    Fetch all emails with GitHub references from Elasticsearch.

    Args:
        es_url: Elasticsearch URL
        index: Index name
        since_date: ISO date string for filtering

    Returns:
        List of email documents
    """
    url = f"{es_url}/{index}/_search?scroll=2m"

    query = {
        "size": 1000,
        "query": {
            "bool": {
                "must": [
                    {"range": {"date": {"gte": since_date}}},
                    {"exists": {"field": "github_pr_references"}},
                ]
            }
        },
        "_source": ["body_full", "github_pr_references", "subject", "date"],
        "sort": [{"date": {"order": "desc"}}],
    }

    req = Request(
        url, data=json.dumps(query).encode("utf-8"), headers={"Content-Type": "application/json"}
    )

    try:
        with urlopen(req) as response:
            data = json.load(response)
    except Exception as e:
        print(f"Error connecting to Elasticsearch: {e}", file=sys.stderr)
        print(f"Make sure Elasticsearch is running at {es_url}", file=sys.stderr)
        sys.exit(1)

    return data["hits"]["hits"]


def extract_github_refs(emails: list) -> tuple[dict, dict]:
    """
    Extract GitHub repository and issue/PR references.

    Args:
        emails: List of email documents from Elasticsearch

    Returns:
        Tuple of (repo_prs dict, unmatched_prs dict)
    """
    repo_prs = defaultdict(set)
    unmatched_prs = defaultdict(int)

    # Patterns to match GitHub URLs
    patterns = [
        # https://github.com/apache/maven/issues/123
        re.compile(r"github\.com/apache/(maven[^/\s\)]*)/(?:issues|pull)/(\d+)", re.IGNORECASE),
        # [maven-compiler-plugin#123]
        re.compile(r"\[(maven[^]#]+)#(\d+)\]", re.IGNORECASE),
    ]

    for email in emails:
        body = email["_source"].get("body_full", "")
        subject = email["_source"].get("subject", "")
        text = body + " " + subject
        prs = email["_source"].get("github_pr_references", [])

        matched_prs = set()

        # Try all patterns
        for pattern in patterns:
            for match in pattern.finditer(text):
                repo = match.group(1)
                pr_num = match.group(2)
                repo_prs[repo].add(pr_num)
                matched_prs.add(pr_num)

        # Count unmatched PRs (those that didn't have explicit repo in text)
        for pr in prs:
            if pr not in matched_prs:
                unmatched_prs[pr] += 1

    return repo_prs, unmatched_prs


def main():
    """Main entry point."""
    args = parse_args()

    # Calculate date range
    since_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Fetching emails from Elasticsearch ({args.es_url})...")
    print(f"Analyzing emails from the last {args.days} days (since {since_date})")
    print()

    emails = fetch_all_emails(args.es_url, args.index, since_date)
    print(f"Found {len(emails)} emails with GitHub PR references\n")

    if not emails:
        print("No emails found. Make sure:")
        print("  1. Elasticsearch is running: docker compose up -d elasticsearch")
        print("  2. Data is indexed: poetry run index-mbox data/dev/*.mbox")
        return

    print("Extracting GitHub references...")
    repo_prs, unmatched = extract_github_refs(emails)

    print("\n" + "=" * 80)
    print(f"GITHUB REPOSITORIES REFERENCED (Last {args.days} days)")
    print("=" * 80 + "\n")

    total_matched = 0
    for repo in sorted(repo_prs.keys()):
        count = len(repo_prs[repo])
        total_matched += count
        print(f"apache/{repo:40s} {count:4d} issues/PRs")

        # Show first few PR numbers as examples
        sample_prs = sorted([int(pr) for pr in list(repo_prs[repo])[:10]])
        print(f"  Examples: {', '.join(f'#{pr}' for pr in sample_prs[:8])}")
        if len(repo_prs[repo]) > 8:
            print(f"  ... and {len(repo_prs[repo]) - 8} more")
        print()

    print(f"Total matched: {total_matched} PR/issue references to specific repositories")
    print(f"Total unmatched: {len(unmatched)} PR/issue numbers (no explicit repo in text)")

    if unmatched:
        print("\nMost frequently mentioned unmatched PR numbers:")
        for pr, count in sorted(unmatched.items(), key=lambda x: -x[1])[:20]:
            print(f"  #{pr:6s} mentioned {count} times")


if __name__ == "__main__":
    main()