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

"""Parser for mbox files containing email messages."""

import mailbox
from collections.abc import Generator
from pathlib import Path

import structlog

from mail_mcp.parsers.email_parser import EmailParser, ParsedEmail

logger = structlog.get_logger(__name__)


class MboxParser:
    """Parser for mbox format mailbox files."""

    def __init__(self):
        """Initialize mbox parser."""
        self.email_parser = EmailParser()

    def parse_file(self, mbox_path: Path) -> Generator[ParsedEmail, None, None]:
        """
        Parse an mbox file and yield parsed emails.

        Args:
            mbox_path: Path to mbox file

        Yields:
            ParsedEmail objects

        Raises:
            FileNotFoundError: If mbox file doesn't exist
            Exception: If mbox file is malformed
        """
        if not mbox_path.exists():
            raise FileNotFoundError(f"Mbox file not found: {mbox_path}")

        logger.info("parsing_mbox_file", path=str(mbox_path), size=mbox_path.stat().st_size)

        try:
            # Open mbox file
            mbox = mailbox.mbox(str(mbox_path))

            message_count = 0
            error_count = 0

            # Iterate through messages
            for key, message in mbox.items():
                try:
                    # Get the file offset for this message
                    # Note: mailbox module doesn't easily expose offsets,
                    # so we'll track the key (position) instead
                    offset = key if isinstance(key, int) else None

                    # Parse the message
                    parsed = self.email_parser.parse(
                        message,
                        mbox_file=mbox_path.name,
                        mbox_offset=offset
                    )

                    message_count += 1
                    yield parsed

                except Exception as e:
                    error_count += 1
                    logger.warning(
                        "message_parse_failed",
                        mbox_file=mbox_path.name,
                        key=key,
                        error=str(e)
                    )
                    # Continue processing other messages

            logger.info(
                "mbox_parsing_complete",
                path=str(mbox_path),
                messages=message_count,
                errors=error_count
            )

        except Exception as e:
            logger.error("mbox_parsing_failed", path=str(mbox_path), error=str(e))
            raise

    def count_messages(self, mbox_path: Path) -> int:
        """
        Count the number of messages in an mbox file.

        Args:
            mbox_path: Path to mbox file

        Returns:
            Number of messages

        Raises:
            FileNotFoundError: If mbox file doesn't exist
        """
        if not mbox_path.exists():
            raise FileNotFoundError(f"Mbox file not found: {mbox_path}")

        try:
            mbox = mailbox.mbox(str(mbox_path))
            count = len(mbox)
            logger.debug("mbox_message_count", path=str(mbox_path), count=count)
            return count
        except Exception as e:
            logger.error("mbox_count_failed", path=str(mbox_path), error=str(e))
            raise

    def get_message_ids(self, mbox_path: Path) -> list[str]:
        """
        Extract all message IDs from an mbox file.

        Useful for checking which messages are already indexed.

        Args:
            mbox_path: Path to mbox file

        Returns:
            List of message IDs

        Raises:
            FileNotFoundError: If mbox file doesn't exist
        """
        if not mbox_path.exists():
            raise FileNotFoundError(f"Mbox file not found: {mbox_path}")

        message_ids = []

        try:
            mbox = mailbox.mbox(str(mbox_path))

            for message in mbox:
                message_id = message.get("Message-ID", "").strip()
                if message_id:
                    message_ids.append(message_id)

            logger.debug(
                "extracted_message_ids",
                path=str(mbox_path),
                count=len(message_ids)
            )

            return message_ids

        except Exception as e:
            logger.error("message_id_extraction_failed", path=str(mbox_path), error=str(e))
            raise
