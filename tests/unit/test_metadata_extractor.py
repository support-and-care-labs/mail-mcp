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

"""Unit tests for metadata extraction from email content."""

import re
from unittest.mock import MagicMock, patch

import pytest

from mail_mcp.extractors.metadata import (
    GITHUB_COMMIT_PATTERN,
    GITHUB_PR_PATTERN,
    VERSION_PATTERN,
    VOTE_PATTERN,
    VOTE_VALUE_PATTERN,
    MetadataExtractor,
)


@pytest.fixture
def mock_maven_projects():
    """Create a mock MavenProjects that returns test JIRA patterns."""
    mock = MagicMock()
    # Return a pattern matching common Maven JIRA keys
    mock.get_jira_pattern.return_value = re.compile(
        r"\b(?:MNG|MRESOLVER|MCOMPILER|SUREFIRE|MWAR|MJAR)-\d+\b"
    )
    return mock


@pytest.fixture
def extractor(mock_maven_projects):
    """Create MetadataExtractor with mocked Maven projects config."""
    with patch("mail_mcp.extractors.metadata.maven_projects", mock_maven_projects):
        yield MetadataExtractor()


class TestGitHubPRPattern:
    """Tests for GitHub PR/issue reference pattern."""

    def test_basic_pr_reference(self):
        """Test matching basic #123 format."""
        text = "Fixed in #123"
        matches = GITHUB_PR_PATTERN.findall(text)
        assert matches == ["123"]

    def test_multiple_pr_references(self):
        """Test matching multiple PR references."""
        text = "See #123, #456, and #789"
        matches = GITHUB_PR_PATTERN.findall(text)
        assert sorted(matches) == ["123", "456", "789"]

    def test_pr_in_sentence(self):
        """Test PR reference within text."""
        text = "This is related to issue #42 that was reported yesterday."
        matches = GITHUB_PR_PATTERN.findall(text)
        assert matches == ["42"]

    def test_pr_at_line_start(self):
        """Test PR reference at beginning of line."""
        text = "#100 is the main issue"
        matches = GITHUB_PR_PATTERN.findall(text)
        assert matches == ["100"]

    def test_no_match_in_hex_color(self):
        """Test that hex colors are not matched as PRs."""
        text = "Color is #ff0000"
        matches = GITHUB_PR_PATTERN.findall(text)
        # This will actually match "ff0000" since the pattern is \d+
        # The pattern only matches digits, so this passes
        assert matches == []

    def test_no_match_for_non_numeric(self):
        """Test that non-numeric hashtags are not matched."""
        text = "#bug #feature"
        matches = GITHUB_PR_PATTERN.findall(text)
        assert matches == []


class TestGitHubCommitPattern:
    """Tests for GitHub commit SHA pattern."""

    def test_short_sha(self):
        """Test matching 7-char SHA."""
        text = "Fixed in abc1234"
        matches = GITHUB_COMMIT_PATTERN.findall(text)
        assert "abc1234" in matches

    def test_full_sha(self):
        """Test matching 40-char SHA."""
        sha = "a" * 40
        text = f"Commit {sha} has the fix"
        matches = GITHUB_COMMIT_PATTERN.findall(text)
        assert sha in matches

    def test_sha_in_url(self):
        """Test matching SHA in GitHub URL."""
        text = "https://github.com/apache/maven/commit/abc1234def5678"
        matches = GITHUB_COMMIT_PATTERN.findall(text)
        assert "abc1234def5678" in matches

    def test_mixed_case_sha(self):
        """Test matching mixed case SHA."""
        text = "See commit AbC123dEf"
        matches = GITHUB_COMMIT_PATTERN.findall(text)
        assert "AbC123dEf" in matches


class TestVersionPattern:
    """Tests for version number pattern."""

    def test_simple_version(self):
        """Test matching simple X.Y.Z format."""
        text = "Maven 3.9.5 released"
        matches = VERSION_PATTERN.findall(text)
        assert "3.9.5" in matches

    def test_two_part_version(self):
        """Test matching X.Y format."""
        text = "Version 4.0 is coming"
        matches = VERSION_PATTERN.findall(text)
        assert "4.0" in matches

    def test_alpha_version(self):
        """Test matching alpha versions."""
        text = "Testing 4.0.0-alpha1"
        matches = VERSION_PATTERN.findall(text)
        assert "4.0.0-alpha1" in matches

    def test_beta_version(self):
        """Test matching beta versions."""
        text = "Try 3.9.0-beta2"
        matches = VERSION_PATTERN.findall(text)
        assert "3.9.0-beta2" in matches

    def test_rc_version(self):
        """Test matching release candidate versions."""
        text = "RC build is 4.0.0-rc1"
        matches = VERSION_PATTERN.findall(text)
        assert "4.0.0-rc1" in matches

    def test_snapshot_version(self):
        """Test matching SNAPSHOT versions."""
        text = "Current dev is 4.0.0-SNAPSHOT"
        matches = VERSION_PATTERN.findall(text)
        assert "4.0.0-SNAPSHOT" in matches

    def test_milestone_version(self):
        """Test matching milestone versions."""
        text = "Milestone 4.0.0-M1 available"
        matches = VERSION_PATTERN.findall(text)
        assert "4.0.0-M1" in matches

    def test_multiple_versions(self):
        """Test matching multiple versions."""
        text = "Upgrade from 3.8.6 to 3.9.5"
        matches = VERSION_PATTERN.findall(text)
        assert "3.8.6" in matches
        assert "3.9.5" in matches


class TestVotePatterns:
    """Tests for vote-related patterns."""

    def test_vote_marker(self):
        """Test matching [VOTE] marker."""
        text = "[VOTE] Release Maven 4.0.0"
        assert VOTE_PATTERN.search(text) is not None

    def test_result_marker(self):
        """Test matching [RESULT] marker."""
        text = "[RESULT] [VOTE] Release passed"
        assert VOTE_PATTERN.search(text) is not None

    def test_case_insensitive_vote(self):
        """Test case insensitive vote matching."""
        text = "[vote] Release"
        assert VOTE_PATTERN.search(text) is not None

    def test_plus_one_vote(self):
        """Test matching +1 vote."""
        text = "+1 (binding)"
        match = VOTE_VALUE_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "+1"

    def test_minus_one_vote(self):
        """Test matching -1 vote."""
        text = "-1 due to test failures"
        match = VOTE_VALUE_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "-1"

    def test_plus_zero_vote(self):
        """Test matching +0 vote."""
        text = "+0 (non-binding)"
        match = VOTE_VALUE_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "+0"

    def test_minus_zero_vote(self):
        """Test matching -0 vote."""
        text = "-0 some concerns"
        match = VOTE_VALUE_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "-0"

    def test_vote_at_line_start(self):
        """Test vote at start of line in multiline text."""
        text = "My review:\n+1 looks good\nThanks"
        match = VOTE_VALUE_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "+1"


class TestMetadataExtractorJira:
    """Tests for JIRA reference extraction."""

    def test_extract_single_jira(self, extractor):
        """Test extracting single JIRA reference."""
        text = "Fixed MNG-1234 in this commit"
        refs = extractor.extract_jira_references(text)
        assert refs == ["MNG-1234"]

    def test_extract_multiple_jira(self, extractor):
        """Test extracting multiple JIRA references."""
        text = "Relates to MNG-1234 and MRESOLVER-567"
        refs = extractor.extract_jira_references(text)
        assert "MNG-1234" in refs
        assert "MRESOLVER-567" in refs

    def test_extract_duplicate_jira(self, extractor):
        """Test that duplicates are removed."""
        text = "MNG-1234 is mentioned again: MNG-1234"
        refs = extractor.extract_jira_references(text)
        assert refs == ["MNG-1234"]

    def test_jira_in_url(self, extractor):
        """Test extracting JIRA from URL."""
        text = "See https://issues.apache.org/jira/browse/MNG-7891"
        refs = extractor.extract_jira_references(text)
        assert refs == ["MNG-7891"]

    def test_no_jira_match(self, extractor):
        """Test no match for non-JIRA references."""
        text = "No JIRA here, just ABC-123"
        refs = extractor.extract_jira_references(text)
        assert refs == []


class TestMetadataExtractorGitHub:
    """Tests for GitHub reference extraction."""

    def test_extract_single_pr(self, extractor):
        """Test extracting single PR reference."""
        text = "Fixed in #123"
        refs = extractor.extract_github_pr_references(text)
        assert "123" in refs

    def test_extract_multiple_prs(self, extractor):
        """Test extracting multiple PR references."""
        text = "See #123 and #456"
        refs = extractor.extract_github_pr_references(text)
        assert len(refs) == 2
        assert "123" in refs
        assert "456" in refs

    def test_extract_commit_sha(self, extractor):
        """Test extracting commit SHA."""
        text = "Commit abc1234 has the fix"
        refs = extractor.extract_github_commit_references(text)
        assert "abc1234" in refs


class TestMetadataExtractorVersions:
    """Tests for version number extraction."""

    def test_extract_versions(self, extractor):
        """Test extracting version numbers."""
        text = "Upgrade from 3.8.6 to 3.9.5"
        versions = extractor.extract_version_numbers(text)
        assert "3.8.6" in versions
        assert "3.9.5" in versions

    def test_extract_snapshot_version(self, extractor):
        """Test extracting SNAPSHOT version."""
        text = "Current: 4.0.0-SNAPSHOT"
        versions = extractor.extract_version_numbers(text)
        assert "4.0.0-SNAPSHOT" in versions


class TestMetadataExtractorDecisions:
    """Tests for decision keyword extraction."""

    def test_extract_decision_keywords(self, extractor):
        """Test extracting decision keywords."""
        text = "It was decided to accept this proposal"
        keywords = extractor.extract_decision_keywords(text)
        assert "decided" in keywords
        assert "accept" not in keywords  # 'accept' is not in the list

    def test_extract_multiple_keywords(self, extractor):
        """Test extracting multiple decision keywords."""
        text = "After consensus, the team agreed to proceed"
        keywords = extractor.extract_decision_keywords(text)
        assert "consensus" in keywords
        assert "agreed" in keywords

    def test_case_insensitive_keywords(self, extractor):
        """Test case insensitive keyword matching."""
        text = "RESOLVED: We will implement this"
        keywords = extractor.extract_decision_keywords(text)
        assert "resolved" in keywords


class TestMetadataExtractorVotes:
    """Tests for vote extraction."""

    def test_extract_vote_info_with_vote(self, extractor):
        """Test extracting vote information."""
        text = "[VOTE] Release Maven 4.0.0\n\n+1 from me"
        has_vote, vote_value = extractor.extract_vote_info(text)
        assert has_vote is True
        assert vote_value == "+1"

    def test_extract_vote_info_no_vote(self, extractor):
        """Test when no vote present."""
        text = "Just a regular discussion"
        has_vote, vote_value = extractor.extract_vote_info(text)
        assert has_vote is False
        assert vote_value is None

    def test_extract_negative_vote(self, extractor):
        """Test extracting negative vote."""
        text = "[VOTE] Release\n-1 tests failing"
        has_vote, vote_value = extractor.extract_vote_info(text)
        assert has_vote is True
        assert vote_value == "-1"


class TestMetadataExtractorFull:
    """Tests for full metadata extraction."""

    def test_extract_all_metadata(self, extractor):
        """Test extracting all metadata from email."""
        text = """[VOTE] Release Maven 4.0.0

        Hi all,

        I would like to call a vote on releasing Maven 4.0.0.
        This release fixes MNG-7891 and MNG-7892.

        See PR #1234 for the main changes.
        Commit abc1234 has the critical fix.

        +1 (binding)

        Thanks,
        Release Manager
        """

        metadata = extractor.extract(text)

        assert "MNG-7891" in metadata.jira_references
        assert "MNG-7892" in metadata.jira_references
        assert "1234" in metadata.github_pr_references
        assert "abc1234" in metadata.github_commit_references
        assert "4.0.0" in metadata.version_numbers
        assert metadata.has_vote is True
        assert metadata.vote_value == "+1"

    def test_extract_empty_text(self, extractor):
        """Test extracting from empty text."""
        metadata = extractor.extract("")

        assert metadata.jira_references == []
        assert metadata.github_pr_references == []
        assert metadata.github_commit_references == []
        assert metadata.version_numbers == []
        assert metadata.decision_keywords == []
        assert metadata.has_vote is False
        assert metadata.vote_value is None


class TestGitHubURLExtraction:
    """
    Tests for extracting GitHub URLs with repository information.

    These patterns extract both repository names and issue/PR numbers from
    full GitHub URLs, which provides more context than just PR numbers.
    """

    # Patterns from analyze_github_refs.py for extracting repo + PR
    GITHUB_URL_PATTERN = re.compile(
        r'github\.com/apache/(maven[^/\s\)]*)/(?:issues|pull)/(\d+)',
        re.IGNORECASE
    )
    BRACKET_NOTATION_PATTERN = re.compile(
        r'\[(maven[^]#]+)#(\d+)\]',
        re.IGNORECASE
    )

    def test_extract_github_issue_url(self):
        """Test extracting GitHub issue URL with repo."""
        text = "See https://github.com/apache/maven/issues/1234"
        match = self.GITHUB_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "maven"
        assert match.group(2) == "1234"

    def test_extract_github_pr_url(self):
        """Test extracting GitHub PR URL with repo."""
        text = "PR at https://github.com/apache/maven-compiler-plugin/pull/567"
        match = self.GITHUB_URL_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "maven-compiler-plugin"
        assert match.group(2) == "567"

    def test_extract_multiple_github_urls(self):
        """Test extracting multiple GitHub URLs."""
        text = """
        Check https://github.com/apache/maven/issues/100
        and https://github.com/apache/maven-resolver/pull/200
        """
        matches = self.GITHUB_URL_PATTERN.findall(text)
        assert len(matches) == 2
        assert ("maven", "100") in matches
        assert ("maven-resolver", "200") in matches

    def test_extract_bracket_notation(self):
        """Test extracting [repo#123] notation."""
        text = "Fixed in [maven-compiler-plugin#42]"
        match = self.BRACKET_NOTATION_PATTERN.search(text)
        assert match is not None
        assert match.group(1) == "maven-compiler-plugin"
        assert match.group(2) == "42"

    def test_extract_bracket_notation_various_repos(self):
        """Test bracket notation with various Maven repos."""
        # Pattern requires characters after 'maven' (e.g., maven-something)
        # so [maven#100] won't match but [maven-*#100] will
        texts = [
            "[maven-core#100]",
            "[maven-surefire-plugin#200]",
            "[maven-war-plugin#300]",
        ]
        for text in texts:
            match = self.BRACKET_NOTATION_PATTERN.search(text)
            assert match is not None, f"Failed to match: {text}"

    def test_bracket_notation_plain_maven_no_match(self):
        """Test that plain [maven#100] doesn't match (requires suffix)."""
        # The pattern is designed for maven-* repos, not plain 'maven'
        text = "[maven#100]"
        match = self.BRACKET_NOTATION_PATTERN.search(text)
        # This pattern requires at least one char after 'maven' before '#'
        assert match is None

    def test_github_url_in_email_body(self):
        """Test extracting GitHub URL from realistic email body."""
        text = """
        Hi all,

        I've opened a PR to fix the issue we discussed:
        https://github.com/apache/maven/pull/1234

        This is related to the resolver changes in:
        https://github.com/apache/maven-resolver/issues/567

        Please review when you have a chance.

        Thanks,
        Developer
        """
        matches = self.GITHUB_URL_PATTERN.findall(text)
        repos = {repo: pr for repo, pr in matches}

        assert repos["maven"] == "1234"
        assert repos["maven-resolver"] == "567"