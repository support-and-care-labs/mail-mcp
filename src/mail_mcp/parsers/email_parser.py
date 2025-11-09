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

"""Email message parser for extracting structured data from email messages."""

import email
import email.utils
from dataclasses import dataclass
from datetime import datetime
from email.message import Message

import structlog

from mail_mcp.extractors import MetadataExtractor, QuoteDetector

logger = structlog.get_logger(__name__)


@dataclass
class ParsedEmail:
    """Structured representation of a parsed email message."""

    # Message identification
    message_id: str
    in_reply_to: str | None
    references: list[str]

    # Sender/recipient information
    from_address: str
    from_name: str | None
    to: list[str]
    cc: list[str]

    # Subject and content
    subject: str
    body_full: str
    body_effective: str  # Body with quotes/signatures removed

    # Temporal information
    date: datetime | None

    # List information
    list_address: str | None

    # Source information
    mbox_file: str | None = None
    mbox_offset: int | None = None

    # Content flags
    has_attachment: bool = False

    # Quote analysis
    quote_percentage: float = 0.0
    is_mostly_quoted: bool = False

    # Extracted metadata
    jira_references: list[str] = None  # type: ignore
    github_pr_references: list[str] = None  # type: ignore
    github_commit_references: list[str] = None  # type: ignore
    version_numbers: list[str] = None  # type: ignore
    decision_keywords: list[str] = None  # type: ignore
    has_vote: bool = False
    vote_value: str | None = None

    def __post_init__(self):
        """Initialize mutable default values."""
        if self.jira_references is None:
            self.jira_references = []
        if self.github_pr_references is None:
            self.github_pr_references = []
        if self.github_commit_references is None:
            self.github_commit_references = []
        if self.version_numbers is None:
            self.version_numbers = []
        if self.decision_keywords is None:
            self.decision_keywords = []


class EmailParser:
    """Parser for individual email messages."""

    def __init__(self):
        """Initialize email parser with extractors."""
        self.metadata_extractor = MetadataExtractor()
        self.quote_detector = QuoteDetector()

    @staticmethod
    def parse_address(address_string: str | None) -> tuple[str | None, str]:
        """
        Parse an email address string into name and address.

        Args:
            address_string: Email address string (e.g., "John Doe <john@example.com>")

        Returns:
            Tuple of (name, address)
        """
        if not address_string:
            return None, ""

        parsed = email.utils.parseaddr(address_string)
        name = parsed[0] if parsed[0] else None
        address = parsed[1] if parsed[1] else ""

        return name, address

    @staticmethod
    def parse_address_list(address_string: str | None) -> list[str]:
        """
        Parse a comma-separated list of email addresses.

        Args:
            address_string: Comma-separated email addresses

        Returns:
            List of email addresses (just the address part, not names)
        """
        if not address_string:
            return []

        addresses = email.utils.getaddresses([address_string])
        return [addr for name, addr in addresses if addr]

    @staticmethod
    def parse_date(date_string: str | None) -> datetime | None:
        """
        Parse an email date string into a datetime object.

        Args:
            date_string: Email date string (RFC 2822 format)

        Returns:
            Datetime object or None if parsing fails
        """
        if not date_string:
            return None

        try:
            # parsedate_to_datetime handles RFC 2822 format
            return email.utils.parsedate_to_datetime(date_string)
        except (TypeError, ValueError) as e:
            logger.warning("date_parse_failed", date_string=date_string, error=str(e))
            return None

    @staticmethod
    def parse_references(references_string: str | None) -> list[str]:
        """
        Parse References header into list of message IDs.

        Args:
            references_string: References header value

        Returns:
            List of message IDs
        """
        if not references_string:
            return []

        # References are space or newline separated message IDs in angle brackets
        # Remove angle brackets and split
        refs = references_string.replace("\n", " ").replace("\r", " ")
        message_ids = []

        for ref in refs.split():
            ref = ref.strip()
            if ref.startswith("<") and ref.endswith(">"):
                message_ids.append(ref)

        return message_ids

    @staticmethod
    def extract_body(message: Message) -> str:
        """
        Extract text body from email message.

        Handles multipart messages and extracts plain text content.

        Args:
            message: Email message object

        Returns:
            Email body text
        """
        body_parts = []

        if message.is_multipart():
            # Walk through message parts
            for part in message.walk():
                content_type = part.get_content_type()

                # Look for text/plain parts
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            # Decode bytes to string
                            charset = part.get_content_charset() or "utf-8"
                            text = payload.decode(charset, errors="replace")
                            body_parts.append(text)
                    except Exception as e:
                        logger.warning("body_extraction_failed", error=str(e))
        else:
            # Simple non-multipart message
            try:
                payload = message.get_payload(decode=True)
                if payload:
                    charset = message.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")
                    body_parts.append(text)
            except Exception as e:
                logger.warning("body_extraction_failed", error=str(e))

        return "\n\n".join(body_parts)

    @staticmethod
    def has_attachments(message: Message) -> bool:
        """
        Check if message has attachments.

        Args:
            message: Email message object

        Returns:
            True if message has attachments
        """
        if not message.is_multipart():
            return False

        for part in message.walk():
            # Check for attachment disposition or non-text content
            if part.get_content_disposition() == "attachment":
                return True
            content_type = part.get_content_type()
            if content_type not in ("text/plain", "text/html", "multipart/alternative", "multipart/mixed"):
                return True

        return False

    def parse(
        self,
        message: Message,
        mbox_file: str | None = None,
        mbox_offset: int | None = None
    ) -> ParsedEmail:
        """
        Parse an email message into structured data.

        Args:
            message: Email message object
            mbox_file: Source mbox filename (optional)
            mbox_offset: Byte offset in mbox file (optional)

        Returns:
            ParsedEmail object with extracted data
        """
        # Extract message ID
        message_id = message.get("Message-ID", "").strip()
        if not message_id:
            # Generate a placeholder ID if missing
            message_id = f"<no-message-id-{hash(message.as_string())}>"
            logger.warning("missing_message_id", generated_id=message_id)

        # Extract In-Reply-To
        in_reply_to = message.get("In-Reply-To", "").strip() or None

        # Extract References
        references = self.parse_references(message.get("References"))

        # Extract sender information
        from_name, from_address = self.parse_address(message.get("From"))

        # Extract recipients
        to = self.parse_address_list(message.get("To"))
        cc = self.parse_address_list(message.get("Cc"))

        # Extract subject
        subject = message.get("Subject", "(No subject)")

        # Extract body
        body_full = self.extract_body(message)

        # Extract date
        date = self.parse_date(message.get("Date"))

        # Extract list information (List-Id or List-Post headers)
        list_id = message.get("List-Id", "").strip()
        list_post = message.get("List-Post", "").strip()

        # Try to extract list address from List-Post or List-Id
        list_address = None
        if list_post and "<mailto:" in list_post:
            # Extract from List-Post: <mailto:dev@maven.apache.org>
            start = list_post.find("<mailto:") + 8
            end = list_post.find(">", start)
            if end > start:
                list_address = list_post[start:end]
        elif list_id:
            # Extract from List-Id: <dev.maven.apache.org>
            if "<" in list_id and ">" in list_id:
                start = list_id.find("<") + 1
                end = list_id.find(">", start)
                if end > start:
                    list_domain = list_id[start:end]
                    # Convert dev.maven.apache.org to dev@maven.apache.org
                    if "." in list_domain:
                        parts = list_domain.split(".", 1)
                        list_address = f"{parts[0]}@{parts[1]}"

        # Check for attachments
        has_attachment = self.has_attachments(message)

        # Analyze quotes and extract effective content
        quote_analysis = self.quote_detector.analyze(body_full)

        # Extract metadata from subject and body
        # Combine subject and body for better metadata extraction
        combined_text = f"{subject}\n\n{body_full}"
        metadata = self.metadata_extractor.extract(combined_text)

        return ParsedEmail(
            message_id=message_id,
            in_reply_to=in_reply_to,
            references=references,
            from_address=from_address,
            from_name=from_name,
            to=to,
            cc=cc,
            subject=subject,
            body_full=body_full,
            body_effective=quote_analysis.body_effective,
            date=date,
            list_address=list_address,
            mbox_file=mbox_file,
            mbox_offset=mbox_offset,
            has_attachment=has_attachment,
            quote_percentage=quote_analysis.quote_percentage,
            is_mostly_quoted=quote_analysis.quote_percentage > self.quote_detector.quote_threshold,
            jira_references=metadata.jira_references,
            github_pr_references=metadata.github_pr_references,
            github_commit_references=metadata.github_commit_references,
            version_numbers=metadata.version_numbers,
            decision_keywords=metadata.decision_keywords,
            has_vote=metadata.has_vote,
            vote_value=metadata.vote_value
        )
