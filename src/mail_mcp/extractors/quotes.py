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

"""Quote detection and filtering for email content."""

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


# Quote line patterns
QUOTE_PREFIX_PATTERN = re.compile(r'^[\s]*[>|]+[\s]*', re.MULTILINE)
ATTRIBUTION_PATTERN = re.compile(
    r'^(?:On\s+.+?\s+wrote:|.+?\s+wrote:|From:.+?$|Sent:.+?$)',
    re.IGNORECASE | re.MULTILINE
)

# Signature patterns
SIGNATURE_MARKER_PATTERN = re.compile(
    r'^--\s*$|^___+\s*$|^Best regards|^Regards|^Cheers|^Thanks',
    re.MULTILINE | re.IGNORECASE
)


@dataclass
class QuoteAnalysis:
    """Results from quote detection analysis."""

    total_lines: int
    quoted_lines: int
    effective_lines: int
    quote_percentage: float
    body_effective: str  # Body with quotes removed


class QuoteDetector:
    """Detector for quoted content in email bodies."""

    def __init__(self, quote_threshold: float = 0.8):
        """
        Initialize quote detector.

        Args:
            quote_threshold: Percentage threshold (0.0-1.0) above which
                           an email is considered mostly quoted
        """
        self.quote_threshold = quote_threshold

    def is_quote_line(self, line: str) -> bool:
        """
        Check if a line is quoted content.

        Args:
            line: Single line of text

        Returns:
            True if line appears to be quoted
        """
        # Empty lines are not quotes
        if not line.strip():
            return False

        # Check for quote prefix (>, |, etc.)
        if QUOTE_PREFIX_PATTERN.match(line):
            return True

        # Check for attribution lines
        if ATTRIBUTION_PATTERN.match(line):
            return True

        return False

    def remove_signature(self, text: str) -> str:
        """
        Remove email signature from text.

        Args:
            text: Email body text

        Returns:
            Text with signature removed
        """
        # Find signature marker
        match = SIGNATURE_MARKER_PATTERN.search(text)
        if match:
            # Return text up to signature
            return text[:match.start()].rstrip()

        return text

    def extract_effective_content(self, text: str) -> str:
        """
        Extract effective (non-quoted) content from email body.

        Args:
            text: Email body text

        Returns:
            Body with quotes and signatures removed
        """
        # First remove signature
        text = self.remove_signature(text)

        # Split into lines
        lines = text.split('\n')

        # Filter out quoted lines
        effective_lines = []
        for line in lines:
            if not self.is_quote_line(line):
                effective_lines.append(line)

        # Rejoin and clean up
        result = '\n'.join(effective_lines)

        # Remove excessive blank lines (more than 2 consecutive)
        result = re.sub(r'\n{3,}', '\n\n', result)

        return result.strip()

    def analyze(self, text: str) -> QuoteAnalysis:
        """
        Analyze email body for quoted content.

        Args:
            text: Email body text

        Returns:
            QuoteAnalysis with statistics and effective content
        """
        logger.debug("analyzing_quotes", text_length=len(text))

        # Split into lines
        lines = text.split('\n')
        total_lines = len(lines)

        # Count quoted lines
        quoted_lines = sum(1 for line in lines if self.is_quote_line(line))

        # Extract effective content
        body_effective = self.extract_effective_content(text)
        effective_lines = len(body_effective.split('\n'))

        # Calculate quote percentage
        quote_percentage = quoted_lines / total_lines if total_lines > 0 else 0.0

        logger.debug(
            "quote_analysis_complete",
            total_lines=total_lines,
            quoted_lines=quoted_lines,
            effective_lines=effective_lines,
            quote_percentage=f"{quote_percentage:.2%}",
            is_mostly_quoted=quote_percentage > self.quote_threshold
        )

        return QuoteAnalysis(
            total_lines=total_lines,
            quoted_lines=quoted_lines,
            effective_lines=effective_lines,
            quote_percentage=quote_percentage,
            body_effective=body_effective
        )

    def is_mostly_quoted(self, text: str) -> bool:
        """
        Check if email body is mostly quoted content.

        Args:
            text: Email body text

        Returns:
            True if quote percentage exceeds threshold
        """
        analysis = self.analyze(text)
        return analysis.quote_percentage > self.quote_threshold
