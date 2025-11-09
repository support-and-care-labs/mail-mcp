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

"""CLI tool for indexing mbox files into Elasticsearch."""

import argparse
import asyncio
import sys
from pathlib import Path

import structlog

from mail_mcp.config import settings
from mail_mcp.indexing import EmailIndexer
from mail_mcp.storage.elasticsearch import ElasticsearchClient

logger = structlog.get_logger(__name__)


async def index_mbox_async(args: argparse.Namespace) -> int:
    """
    Async implementation of mbox indexing.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Resolve paths
    mbox_path = Path(args.mbox).resolve()

    # Validate path exists
    if args.directory:
        if not mbox_path.is_dir():
            logger.error("directory_not_found", path=str(mbox_path))
            print(f"Error: Directory not found: {mbox_path}", file=sys.stderr)
            return 1
    else:
        if not mbox_path.is_file():
            logger.error("file_not_found", path=str(mbox_path))
            print(f"Error: File not found: {mbox_path}", file=sys.stderr)
            return 1

    # Create Elasticsearch client
    logger.info(
        "connecting_to_elasticsearch",
        url=settings.elasticsearch_url,
        index_prefix=settings.elasticsearch_index_prefix
    )

    es_client = ElasticsearchClient(
        url=settings.elasticsearch_url
    )

    # Connect
    try:
        await es_client.connect()
        logger.info("elasticsearch_connected")
    except Exception as e:
        logger.error("elasticsearch_connection_failed", error=str(e))
        print(f"Error: Failed to connect to Elasticsearch: {e}", file=sys.stderr)
        return 1

    # Create indexer
    indexer = EmailIndexer(
        es_client=es_client,
        index_prefix=settings.elasticsearch_index_prefix,
        batch_size=args.batch_size
    )

    # Index files
    try:
        if args.directory:
            logger.info(
                "indexing_directory",
                directory=str(mbox_path),
                list_name=args.list,
                pattern=args.pattern
            )
            stats = await indexer.index_directory(
                directory=mbox_path,
                list_name=args.list,
                pattern=args.pattern,
                create_index=not args.no_create_index
            )

            print(f"Directory indexing complete:")
            print(f"  Files processed: {stats['files']}")
            print(f"  Documents indexed: {stats['indexed']}")
            print(f"  Errors: {stats['errors']}")

        else:
            logger.info(
                "indexing_file",
                file=str(mbox_path),
                list_name=args.list
            )
            stats = await indexer.index_mbox_file(
                mbox_path=mbox_path,
                list_name=args.list,
                create_index=not args.no_create_index
            )

            print(f"File indexing complete:")
            print(f"  Documents indexed: {stats['indexed']}")
            print(f"  Errors: {stats['errors']}")

        # Close connection
        await es_client.close()

        # Return error code if there were errors
        return 1 if stats.get("errors", 0) > 0 else 0

    except Exception as e:
        logger.error("indexing_failed", error=str(e), exc_info=True)
        print(f"Error: Indexing failed: {e}", file=sys.stderr)
        await es_client.close()
        return 1


def main():
    """Main entry point for index-mbox CLI tool."""
    parser = argparse.ArgumentParser(
        description="Index mbox files into Elasticsearch for Maven mailing list analysis"
    )

    parser.add_argument(
        "mbox",
        help="Path to mbox file or directory containing mbox files"
    )

    parser.add_argument(
        "--list",
        default="dev@maven.apache.org",
        help="Mailing list address (default: dev@maven.apache.org)"
    )

    parser.add_argument(
        "--directory", "-d",
        action="store_true",
        help="Index all mbox files in directory"
    )

    parser.add_argument(
        "--pattern",
        default="*.mbox",
        help="File pattern for directory mode (default: *.mbox)"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for bulk indexing (default: 100)"
    )

    parser.add_argument(
        "--no-create-index",
        action="store_true",
        help="Don't create index if it doesn't exist"
    )

    args = parser.parse_args()

    # Run async function
    exit_code = asyncio.run(index_mbox_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
