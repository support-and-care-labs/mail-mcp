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
Retrieve an mbox file from Apache mailing list server by month.

Usage: retrieve-mbox --date <yyyy-mm> [--list <list@domain>] [--output-dir <path>]
Stores the file as <yyyy-mm>.mbox in the specified directory (default: current).
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx

# ---- Constants ----
DEFAULT_MAILING_LIST = "dev@maven.apache.org"
BASE_URL = "https://lists.apache.org/api/mbox.lua"
USER_AGENT = "retrieve-mbox.py"


def validate_date(date_str: str) -> tuple[int, int]:
    """
    Validate date string format and return year and month.

    Args:
        date_str: Date string in yyyy-mm format

    Returns:
        Tuple of (year, month)

    Raises:
        ValueError: If date format is invalid
    """
    if not re.match(r'^\d{4}-\d{2}$', date_str):
        raise ValueError("Date must be in the form yyyy-mm, e.g., 2024-10")

    try:
        year = int(date_str[:4])
        month = int(date_str[5:7])
    except (ValueError, IndexError) as e:
        raise ValueError(f"Unable to parse date: {date_str}") from e

    if not (1 <= month <= 12):
        raise ValueError("Month must be between 01 and 12")

    # Validate date by constructing datetime
    try:
        datetime(year, month, 1)
    except ValueError as e:
        raise ValueError(f"Invalid date: {e}") from e

    return year, month


def validate_list(list_addr: str) -> None:
    """
    Validate mailing list address format.

    Args:
        list_addr: Mailing list address

    Raises:
        ValueError: If list address is invalid
    """
    if not list_addr or not list_addr.strip():
        raise ValueError("List address must be non-empty")

    if ' ' in list_addr:
        raise ValueError("List address must not contain spaces")

    if '@' not in list_addr:
        print(
            f"Warning: List value '{list_addr}' does not contain '@'. Proceeding anyway.",
            file=sys.stderr
        )


def download_mbox(list_addr: str, date_str: str, output_path: Path) -> None:
    """
    Download mbox file from Apache mailing list API.

    Args:
        list_addr: Mailing list address (e.g., dev@maven.apache.org)
        date_str: Date in yyyy-mm format
        output_path: Destination file path

    Raises:
        httpx.HTTPError: If download fails
        IOError: If file operations fail
    """
    params = {"list": list_addr, "date": date_str}
    url = f"{BASE_URL}?{urlencode(params)}"

    print(f"Retrieving mbox for {list_addr} {date_str}", file=sys.stderr)
    print(f"GET {url}", file=sys.stderr)

    tmp_path = output_path.with_suffix('.mbox.tmp')

    try:
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT})

            if response.status_code >= 400:
                print(
                    f"Download failed from {url} (HTTP {response.status_code})",
                    file=sys.stderr
                )
                sys.exit(4)

            # Write to temporary file
            tmp_path.write_bytes(response.content)

            # Atomic move to final location
            tmp_path.replace(output_path)

    except httpx.HTTPError as e:
        # Clean up temporary file on error
        tmp_path.unlink(missing_ok=True)
        print(f"Download failed from {url}: {e}", file=sys.stderr)
        sys.exit(4)
    except OSError as e:
        # Clean up temporary file on error
        tmp_path.unlink(missing_ok=True)
        print(f"File operation failed: {e}", file=sys.stderr)
        sys.exit(4)


def main() -> None:
    """Main entry point for retrieve-mbox command."""
    parser = argparse.ArgumentParser(
        description="Retrieve an mbox file from Apache mailing list server by month.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--date",
        required=True,
        metavar="yyyy-mm",
        help="Year and month in the form yyyy-mm (e.g., 2024-10)"
    )
    parser.add_argument(
        "--list",
        default=DEFAULT_MAILING_LIST,
        metavar="list@domain",
        help=f"Apache mailing list address (default: {DEFAULT_MAILING_LIST})"
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        metavar="PATH",
        help="Output directory for mbox file (default: current directory)"
    )

    args = parser.parse_args()

    # Validate inputs
    try:
        validate_date(args.date)
        validate_list(args.list)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        parser.print_help(sys.stderr)
        sys.exit(2)

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download mbox file
    output_filename = f"{args.date}.mbox"
    output_path = output_dir / output_filename

    download_mbox(args.list, args.date, output_path)

    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
