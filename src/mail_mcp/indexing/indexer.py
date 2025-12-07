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

"""Email indexing pipeline for bulk processing mbox files."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import structlog

from mail_mcp.parsers.email_parser import EmailParser, ParsedEmail
from mail_mcp.parsers.mbox_parser import MboxParser
from mail_mcp.storage.elasticsearch import ElasticsearchClient
from mail_mcp.storage.schema import get_index_name

logger = structlog.get_logger(__name__)


class EmailIndexer:
    """Pipeline for indexing email archives into Elasticsearch."""

    def __init__(
        self,
        es_client: ElasticsearchClient,
        index_prefix: str = "maven",
        batch_size: int = 100
    ):
        """
        Initialize email indexer.

        Args:
            es_client: Elasticsearch client
            index_prefix: Prefix for index names
            batch_size: Number of documents to batch for bulk indexing
        """
        self.es_client = es_client
        self.index_prefix = index_prefix
        self.batch_size = batch_size
        self.mbox_parser = MboxParser()
        self.email_parser = EmailParser()

    def _parsed_email_to_doc(self, email: ParsedEmail, list_name: str | None = None) -> dict:
        """
        Convert ParsedEmail to Elasticsearch document.

        Args:
            email: Parsed email object
            list_name: Mailing list name (if not in email)

        Returns:
            Document dictionary ready for indexing
        """
        # Use list_address from email or fallback to provided list_name
        final_list_address = email.list_address or list_name

        # Extract list name part (e.g., "dev" from "dev@maven.apache.org")
        list_name_part = None
        if final_list_address:
            list_name_part = final_list_address.split("@")[0]

        doc = {
            # Message identification
            "message_id": email.message_id,
            "in_reply_to": email.in_reply_to,
            "references": email.references,

            # Sender information
            "from_address": email.from_address,
            "from_name": email.from_name,

            # Recipients
            "to": email.to,
            "cc": email.cc,

            # Subject and body
            "subject": email.subject,
            "body_full": email.body_full,
            "body_effective": email.body_effective,

            # Temporal information
            "date": email.date.isoformat() if email.date else None,
            "indexed_at": datetime.now(UTC).isoformat(),

            # List information
            "list_address": final_list_address,
            "list_name": list_name_part,

            # Metadata extraction results
            "jira_references": email.jira_references,
            "github_pr_references": email.github_pr_references,
            "github_commit_references": email.github_commit_references,
            "version_numbers": email.version_numbers,
            "decision_keywords": email.decision_keywords,
            "has_vote": email.has_vote,
            "vote_value": email.vote_value,

            # Content analysis
            "quote_percentage": email.quote_percentage,
            "is_mostly_quoted": email.is_mostly_quoted,
            "has_attachment": email.has_attachment,

            # Source information
            "mbox_file": email.mbox_file,
            "mbox_offset": email.mbox_offset,
        }

        return doc

    async def process_mbox_file(
        self,
        mbox_path: Path,
        list_name: str | None = None
    ) -> AsyncIterator[ParsedEmail]:
        """
        Process an mbox file and yield parsed emails.

        Args:
            mbox_path: Path to mbox file
            list_name: Mailing list name (optional, for list_address fallback)

        Yields:
            Parsed email objects
        """
        logger.info("processing_mbox_file", path=str(mbox_path))

        email_count = 0
        error_count = 0

        for parsed in self.mbox_parser.parse_file(mbox_path):
            try:
                email_count += 1
                yield parsed

            except Exception as e:
                error_count += 1
                logger.error(
                    "email_yield_failed",
                    mbox_file=str(mbox_path),
                    error=str(e),
                    exc_info=True
                )

        logger.info(
            "mbox_processing_complete",
            path=str(mbox_path),
            email_count=email_count,
            error_count=error_count
        )

    async def index_mbox_file(
        self,
        mbox_path: Path,
        list_name: str,
        create_index: bool = True
    ) -> dict:
        """
        Index an mbox file into Elasticsearch.

        Args:
            mbox_path: Path to mbox file
            list_name: Mailing list name (e.g., "dev@maven.apache.org")
            create_index: Whether to create index if it doesn't exist

        Returns:
            Statistics dictionary with counts and errors
        """
        index_name = get_index_name(self.index_prefix, list_name)

        logger.info(
            "indexing_mbox_file",
            mbox_path=str(mbox_path),
            list_name=list_name,
            index_name=index_name
        )

        # Create index if requested
        if create_index:
            await self.es_client.create_index(list_name)

        # Statistics
        stats = {
            "indexed": 0,
            "errors": 0,
            "skipped": 0,
            "mbox_file": str(mbox_path),
            "index_name": index_name
        }

        # Batch for bulk indexing
        batch = []

        async for parsed_email in self.process_mbox_file(mbox_path, list_name):
            # Convert to document
            doc = self._parsed_email_to_doc(parsed_email, list_name)

            # Add to batch
            batch.append({
                "_id": parsed_email.message_id,
                "_source": doc
            })

            # Index batch when full
            if len(batch) >= self.batch_size:
                try:
                    # Pass list_name, not index_name - es_client will compute index name
                    success, errors = await self.es_client.bulk_index(list_name, batch)
                    stats["indexed"] += success
                    stats["errors"] += len(errors) if errors else 0
                    logger.info(
                        "batch_indexed",
                        batch_size=len(batch),
                        indexed=success,
                        errors=len(errors) if errors else 0
                    )
                except Exception as e:
                    logger.error("batch_index_failed", error=str(e), exc_info=True)
                    stats["errors"] += len(batch)

                batch = []

        # Index remaining documents
        if batch:
            try:
                # Pass list_name, not index_name - es_client will compute index name
                success, errors = await self.es_client.bulk_index(list_name, batch)
                stats["indexed"] += success
                stats["errors"] += len(errors) if errors else 0
                logger.info(
                    "final_batch_indexed",
                    batch_size=len(batch),
                    indexed=success,
                    errors=len(errors) if errors else 0
                )
            except Exception as e:
                logger.error("final_batch_index_failed", error=str(e), exc_info=True)
                stats["errors"] += len(batch)

        logger.info(
            "indexing_complete",
            **stats
        )

        return stats

    async def index_directory(
        self,
        directory: Path,
        list_name: str,
        pattern: str = "*.mbox",
        create_index: bool = True
    ) -> dict:
        """
        Index all mbox files in a directory.

        Args:
            directory: Directory containing mbox files
            list_name: Mailing list name
            pattern: Glob pattern for mbox files (default: "*.mbox")
            create_index: Whether to create index if it doesn't exist

        Returns:
            Combined statistics for all files
        """
        logger.info(
            "indexing_directory",
            directory=str(directory),
            pattern=pattern,
            list_name=list_name
        )

        # Find all mbox files
        mbox_files = sorted(directory.glob(pattern))

        if not mbox_files:
            logger.warning("no_mbox_files_found", directory=str(directory), pattern=pattern)
            return {"files": 0, "indexed": 0, "errors": 0}

        # Combined statistics
        total_stats = {
            "files": len(mbox_files),
            "indexed": 0,
            "errors": 0,
            "skipped": 0,
            "file_results": []
        }

        # Process each file
        for mbox_path in mbox_files:
            try:
                file_stats = await self.index_mbox_file(
                    mbox_path,
                    list_name,
                    create_index=create_index and (mbox_path == mbox_files[0])
                )
                total_stats["indexed"] += file_stats["indexed"]
                total_stats["errors"] += file_stats["errors"]
                total_stats["skipped"] += file_stats["skipped"]
                total_stats["file_results"].append(file_stats)

            except Exception as e:
                logger.error(
                    "file_indexing_failed",
                    mbox_path=str(mbox_path),
                    error=str(e),
                    exc_info=True
                )
                total_stats["errors"] += 1

        logger.info(
            "directory_indexing_complete",
            files=total_stats["files"],
            indexed=total_stats["indexed"],
            errors=total_stats["errors"]
        )

        return total_stats
