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
Update the current month's mbox file and re-index it.

This script is designed to be run periodically (e.g., hourly via cron) to keep
the mailing list archive up-to-date with the latest emails.

Usage: update-current-month [--list <list@domain>] [--data-dir <path>]
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
import structlog

from mail_mcp.config import settings
from mail_mcp.indexing import EmailIndexer
from mail_mcp.storage.elasticsearch import ElasticsearchClient

# ---- Constants ----
DEFAULT_MAILING_LIST = "dev@maven.apache.org"
BASE_URL = "https://lists.apache.org/api/mbox.lua"
USER_AGENT = "mail-mcp-updater/1.0"

logger = structlog.get_logger(__name__)


def get_current_month() -> str:
    """Get the current year-month string in yyyy-mm format."""
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}"


def download_mbox(list_addr: str, date_str: str, output_path: Path) -> bool:
    """
    Download mbox file from Apache mailing list API.

    Args:
        list_addr: Mailing list address (e.g., dev@maven.apache.org)
        date_str: Date in yyyy-mm format
        output_path: Destination file path

    Returns:
        True if download successful, False otherwise
    """
    params = {"list": list_addr, "date": date_str}
    url = f"{BASE_URL}?{urlencode(params)}"

    logger.info("downloading_mbox", list=list_addr, date=date_str, url=url)

    tmp_path = output_path.with_suffix('.mbox.tmp')

    try:
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT})

            if response.status_code >= 400:
                logger.error(
                    "download_failed",
                    url=url,
                    status_code=response.status_code
                )
                return False

            # Write to temporary file
            tmp_path.write_bytes(response.content)

            # Atomic move to final location
            tmp_path.replace(output_path)

            logger.info(
                "download_complete",
                file=str(output_path),
                size_bytes=len(response.content)
            )
            return True

    except httpx.HTTPError as e:
        tmp_path.unlink(missing_ok=True)
        logger.error("download_http_error", url=url, error=str(e))
        return False
    except IOError as e:
        tmp_path.unlink(missing_ok=True)
        logger.error("download_io_error", error=str(e))
        return False


async def index_mbox(mbox_path: Path, list_name: str) -> bool:
    """
    Index a single mbox file into Elasticsearch.

    Args:
        mbox_path: Path to the mbox file
        list_name: Name of the mailing list

    Returns:
        True if indexing successful, False otherwise
    """
    logger.info(
        "connecting_to_elasticsearch",
        url=settings.elasticsearch_url,
        index_prefix=settings.elasticsearch_index_prefix
    )

    es_client = ElasticsearchClient(url=settings.elasticsearch_url)

    try:
        await es_client.connect()
        logger.info("elasticsearch_connected")
    except Exception as e:
        logger.error("elasticsearch_connection_failed", error=str(e))
        return False

    indexer = EmailIndexer(
        es_client=es_client,
        index_prefix=settings.elasticsearch_index_prefix,
        batch_size=100
    )

    try:
        logger.info("indexing_file", file=str(mbox_path), list_name=list_name)
        stats = await indexer.index_mbox_file(
            mbox_path=mbox_path,
            list_name=list_name,
            create_index=True
        )

        logger.info(
            "indexing_complete",
            indexed=stats.get("indexed", 0),
            errors=stats.get("errors", 0)
        )

        await es_client.close()
        return stats.get("errors", 0) == 0

    except Exception as e:
        logger.error("indexing_failed", error=str(e), exc_info=True)
        await es_client.close()
        return False


async def update_current_month_async(
    list_addr: str,
    data_dir: Path,
    list_subdir: str
) -> int:
    """
    Download and index the current month's mbox file.

    Args:
        list_addr: Mailing list address
        data_dir: Base data directory
        list_subdir: Subdirectory for this list (e.g., 'dev')

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    current_month = get_current_month()
    logger.info(
        "update_starting",
        list=list_addr,
        month=current_month,
        data_dir=str(data_dir)
    )

    # Ensure data directory exists
    list_dir = data_dir / list_subdir
    list_dir.mkdir(parents=True, exist_ok=True)

    # Download mbox
    mbox_filename = f"{current_month}.mbox"
    mbox_path = list_dir / mbox_filename

    if not download_mbox(list_addr, current_month, mbox_path):
        logger.error("update_failed", reason="download_failed")
        return 1

    # Index into Elasticsearch
    if not await index_mbox(mbox_path, list_addr):
        logger.error("update_failed", reason="indexing_failed")
        return 1

    logger.info("update_complete", month=current_month, file=str(mbox_path))
    return 0


def get_list_subdir(list_addr: str) -> str:
    """
    Get subdirectory name from list address.

    Args:
        list_addr: Mailing list address (e.g., dev@maven.apache.org)

    Returns:
        Subdirectory name (e.g., 'dev')
    """
    return list_addr.split("@")[0] if "@" in list_addr else list_addr


def main() -> None:
    """Main entry point for update-current-month command."""
    parser = argparse.ArgumentParser(
        description="Update the current month's mbox file and re-index it.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--list",
        default=DEFAULT_MAILING_LIST,
        metavar="list@domain",
        help=f"Apache mailing list address (default: {DEFAULT_MAILING_LIST})"
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        metavar="PATH",
        help=f"Base data directory (default: {settings.data_path}, or MAIL_MCP_DATA_PATH)"
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else settings.data_path
    list_subdir = get_list_subdir(args.list)

    exit_code = asyncio.run(
        update_current_month_async(args.list, data_dir, list_subdir)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
