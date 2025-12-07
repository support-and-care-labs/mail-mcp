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

"""Metadata extraction from email content."""

import re
from dataclasses import dataclass

import structlog

from mail_mcp.config import maven_projects

logger = structlog.get_logger(__name__)


# GitHub reference patterns
GITHUB_PR_PATTERN = re.compile(r'#(\d+)\b')
GITHUB_COMMIT_PATTERN = re.compile(r'\b([0-9a-f]{7,40})\b', re.IGNORECASE)

# Version number patterns
VERSION_PATTERN = re.compile(
    r'\b\d+\.\d+(?:\.\d+)?(?:-(?:alpha|beta|rc|SNAPSHOT|M)\d*)?(?:-\d+)?\b',
    re.IGNORECASE
)

# Decision keywords (case-insensitive)
DECISION_KEYWORDS = [
    "decided", "consensus", "agreed", "resolved", "wontfix",
    "approved", "rejected", "accepted", "declined"
]

# Vote patterns
VOTE_PATTERN = re.compile(r'\[VOTE\]|\[RESULT\]', re.IGNORECASE)
VOTE_VALUE_PATTERN = re.compile(r'(?:^|\s)([+-][01])(?:\s|$)', re.MULTILINE)


@dataclass
class ExtractedMetadata:
    """Container for extracted metadata from email content."""

    # External references
    jira_references: list[str]
    github_pr_references: list[str]
    github_commit_references: list[str]

    # Version information
    version_numbers: list[str]

    # Decision indicators
    decision_keywords: list[str]
    has_vote: bool
    vote_value: str | None  # "+1", "-1", "+0", "-0"


class MetadataExtractor:
    """Extractor for structured metadata from email content."""

    def __init__(self):
        """Initialize metadata extractor."""
        # Get JIRA pattern from configuration
        self._jira_pattern = maven_projects.get_jira_pattern()

        # Compile decision keyword pattern
        keywords_pattern = "|".join(re.escape(kw) for kw in DECISION_KEYWORDS)
        self._decision_pattern = re.compile(rf'\b({keywords_pattern})\b', re.IGNORECASE)

    def extract_jira_references(self, text: str) -> list[str]:
        """
        Extract JIRA issue references from text.

        Args:
            text: Text to search

        Returns:
            List of JIRA references (e.g., ["MNG-1234", "MRESOLVER-567"])
        """
        matches = self._jira_pattern.findall(text)
        # Remove duplicates while preserving order
        seen = set()
        unique_matches = []
        for match in matches:
            if match not in seen:
                seen.add(match)
                unique_matches.append(match)

        return unique_matches

    def extract_github_pr_references(self, text: str) -> list[str]:
        """
        Extract GitHub PR/issue references from text.

        Args:
            text: Text to search

        Returns:
            List of PR/issue numbers (e.g., ["123", "456"])
        """
        matches = GITHUB_PR_PATTERN.findall(text)
        # Remove duplicates
        return list(set(matches))

    def extract_github_commit_references(self, text: str) -> list[str]:
        """
        Extract potential GitHub commit SHA references from text.

        Note: This may have false positives as it matches any hex string.
        Consider filtering by length (typically 7 or 40 chars) or context.

        Args:
            text: Text to search

        Returns:
            List of potential commit SHAs
        """
        matches = GITHUB_COMMIT_PATTERN.findall(text)

        # Filter to likely commit SHAs (7-40 hex chars)
        # Exclude very common hex patterns that aren't commits
        filtered = []
        for match in matches:
            # Only include if 7-40 characters and looks like a commit
            if 7 <= len(match) <= 40:
                # Exclude common non-commit hex patterns
                if match.lower() not in ('ffffff', 'deadbeef', '0000000'):
                    filtered.append(match)

        # Remove duplicates
        return list(set(filtered))

    def extract_version_numbers(self, text: str) -> list[str]:
        """
        Extract version numbers from text.

        Args:
            text: Text to search

        Returns:
            List of version numbers (e.g., ["3.9.0", "4.0.0-alpha-1"])
        """
        matches = VERSION_PATTERN.findall(text)

        # Remove duplicates and filter out dates that match pattern
        versions = []
        for match in set(matches):
            # Skip if it looks like a date (first component > 12)
            parts = match.split('.')[0].split('-')[0]
            if parts.isdigit() and int(parts) > 31:
                continue
            versions.append(match)

        return sorted(versions)

    def extract_decision_keywords(self, text: str) -> list[str]:
        """
        Extract decision-related keywords from text.

        Args:
            text: Text to search

        Returns:
            List of found keywords (lowercase)
        """
        matches = self._decision_pattern.findall(text)
        # Return unique lowercase keywords
        return list(set(kw.lower() for kw in matches))

    def extract_vote_info(self, text: str) -> tuple[bool, str | None]:
        """
        Extract voting information from text.

        Args:
            text: Text to search

        Returns:
            Tuple of (has_vote, vote_value)
            - has_vote: True if [VOTE] or [RESULT] markers found
            - vote_value: "+1", "-1", "+0", "-0" if found, else None
        """
        has_vote = bool(VOTE_PATTERN.search(text))

        vote_value = None
        vote_match = VOTE_VALUE_PATTERN.search(text)
        if vote_match:
            vote_value = vote_match.group(1)

        return has_vote, vote_value

    def extract(self, text: str) -> ExtractedMetadata:
        """
        Extract all metadata from text.

        Args:
            text: Text to analyze (typically email body or subject)

        Returns:
            ExtractedMetadata object with all extracted information
        """
        logger.debug("extracting_metadata", text_length=len(text))

        jira_refs = self.extract_jira_references(text)
        github_prs = self.extract_github_pr_references(text)
        github_commits = self.extract_github_commit_references(text)
        versions = self.extract_version_numbers(text)
        keywords = self.extract_decision_keywords(text)
        has_vote, vote_value = self.extract_vote_info(text)

        logger.debug(
            "metadata_extracted",
            jira_count=len(jira_refs),
            github_pr_count=len(github_prs),
            github_commit_count=len(github_commits),
            version_count=len(versions),
            keyword_count=len(keywords),
            has_vote=has_vote
        )

        return ExtractedMetadata(
            jira_references=jira_refs,
            github_pr_references=github_prs,
            github_commit_references=github_commits,
            version_numbers=versions,
            decision_keywords=keywords,
            has_vote=has_vote,
            vote_value=vote_value
        )
