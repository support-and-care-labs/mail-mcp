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

"""Integration tests for MCP tools using Testcontainers."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from mail_mcp.server import tools
from mail_mcp.storage.schema import get_index_name


@pytest.fixture
async def indexed_test_data(es_client, test_settings, clean_elasticsearch):
    """
    Create test index with sample data for MCP tool testing.

    Returns a dict with test data details for assertions.
    """
    list_name = "dev@maven.apache.org"

    # Create index
    await es_client.create_index(list_name)

    # Sample emails for testing
    test_emails = [
        {
            "message_id": "<release-vote@maven.apache.org>",
            "subject": "[VOTE] Release Maven 4.0.0",
            "from_address": "release-manager@apache.org",
            "from_name": "Release Manager",
            "date": datetime(2024, 10, 15, 10, 0, 0),
            "to": ["dev@maven.apache.org"],
            "cc": [],
            "list_address": "dev@maven.apache.org",
            "in_reply_to": None,
            "references": [],
            "body_full": "I would like to call a vote on releasing Maven 4.0.0.\n\nPlease vote +1, 0, or -1.",
            "body_effective": "I would like to call a vote on releasing Maven 4.0.0. Please vote +1, 0, or -1.",
            "quote_percentage": 0.0,
            "jira_references": ["MNG-7891"],
            "github_pr_references": ["1234"],
            "github_commit_references": [],
            "version_numbers": ["4.0.0"],
            "decision_keywords": ["vote"],
            "has_vote": True,
            "vote_value": "+1",
        },
        {
            "message_id": "<reply-vote@maven.apache.org>",
            "subject": "Re: [VOTE] Release Maven 4.0.0",
            "from_address": "contributor@example.com",
            "from_name": "John Contributor",
            "date": datetime(2024, 10, 15, 12, 0, 0),
            "to": ["dev@maven.apache.org"],
            "cc": [],
            "list_address": "dev@maven.apache.org",
            "in_reply_to": "<release-vote@maven.apache.org>",
            "references": ["<release-vote@maven.apache.org>"],
            "body_full": "+1 (binding)\n\nAll tests pass on my end.",
            "body_effective": "+1 (binding) All tests pass on my end.",
            "quote_percentage": 0.0,
            "jira_references": [],
            "github_pr_references": [],
            "github_commit_references": [],
            "version_numbers": ["4.0.0"],
            "decision_keywords": [],
            "has_vote": True,
            "vote_value": "+1",
        },
        {
            "message_id": "<bug-report@maven.apache.org>",
            "subject": "[BUG] NullPointerException in dependency resolution",
            "from_address": "user@example.com",
            "from_name": "Bug Reporter",
            "date": datetime(2024, 10, 10, 8, 0, 0),
            "to": ["dev@maven.apache.org"],
            "cc": [],
            "list_address": "dev@maven.apache.org",
            "in_reply_to": None,
            "references": [],
            "body_full": "I found a bug in Maven 3.9.5. See https://github.com/apache/maven/issues/5678",
            "body_effective": "I found a bug in Maven 3.9.5. See https://github.com/apache/maven/issues/5678",
            "quote_percentage": 0.0,
            "jira_references": ["MNG-5678"],
            "github_pr_references": ["5678"],
            "github_commit_references": [],
            "version_numbers": ["3.9.5"],
            "decision_keywords": [],
            "has_vote": False,
            "vote_value": None,
        },
        {
            "message_id": "<discussion@maven.apache.org>",
            "subject": "Discussion about build improvements",
            "from_address": "developer@apache.org",
            "from_name": "Apache Developer",
            "date": datetime(2024, 10, 5, 14, 0, 0),
            "to": ["dev@maven.apache.org"],
            "cc": [],
            "list_address": "dev@maven.apache.org",
            "in_reply_to": None,
            "references": [],
            "body_full": "Let's discuss how we can improve build performance.",
            "body_effective": "Let's discuss how we can improve build performance.",
            "quote_percentage": 0.0,
            "jira_references": [],
            "github_pr_references": [],
            "github_commit_references": [],
            "version_numbers": [],
            "decision_keywords": [],
            "has_vote": False,
            "vote_value": None,
        },
    ]

    # Index all test emails
    for email in test_emails:
        await es_client.index_document(list_name, email)

    # Refresh index to make documents searchable
    index_name = get_index_name(test_settings.elasticsearch_index_prefix, list_name)
    await es_client._client.indices.refresh(index=index_name)

    return {
        "list_name": list_name,
        "emails": test_emails,
        "count": len(test_emails),
    }


@pytest.fixture
def mock_es_client(es_client):
    """Patch the global ES client in tools module to use test client."""
    with patch.object(tools, "_es_client", es_client):
        with patch.object(tools, "get_es_client", AsyncMock(return_value=es_client)):
            yield es_client


class TestSearchEmails:
    """Tests for the search_emails tool."""

    @pytest.mark.asyncio
    async def test_search_basic_query(self, indexed_test_data, mock_es_client):
        """Test basic full-text search."""
        result = await tools.search_emails(
            query="release",
            list_name=indexed_test_data["list_name"],
            size=10,
        )

        assert "Found" in result
        assert "Release Maven 4.0.0" in result
        assert "release-manager@apache.org" in result

    @pytest.mark.asyncio
    async def test_search_with_jira_filter(self, indexed_test_data, mock_es_client):
        """Test search with JIRA reference filter."""
        result = await tools.search_emails(
            query="Maven",
            list_name=indexed_test_data["list_name"],
            has_jira=True,
            size=10,
        )

        assert "Found" in result
        # Should include emails with JIRA references
        assert "MNG-" in result

    @pytest.mark.asyncio
    async def test_search_with_vote_filter(self, indexed_test_data, mock_es_client):
        """Test search filtering for votes."""
        result = await tools.search_emails(
            query="Maven",
            list_name=indexed_test_data["list_name"],
            has_vote=True,
            size=10,
        )

        assert "Found" in result
        assert "VOTE" in result

    @pytest.mark.asyncio
    async def test_search_with_date_range(self, indexed_test_data, mock_es_client):
        """Test search with date range filter."""
        result = await tools.search_emails(
            query="Maven",
            list_name=indexed_test_data["list_name"],
            from_date="2024-10-14",
            to_date="2024-10-16",
            size=10,
        )

        assert "Found" in result
        # Only the vote emails from Oct 15 should match
        assert "Release Maven 4.0.0" in result

    @pytest.mark.asyncio
    async def test_search_with_from_address_filter(self, indexed_test_data, mock_es_client):
        """Test search filtering by sender."""
        result = await tools.search_emails(
            query="Maven",
            list_name=indexed_test_data["list_name"],
            from_address="release-manager",
            size=10,
        )

        assert "Found" in result
        assert "release-manager@apache.org" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, indexed_test_data, mock_es_client):
        """Test search with no matching results."""
        result = await tools.search_emails(
            query="nonexistent-unique-term-xyz123",
            list_name=indexed_test_data["list_name"],
            size=10,
        )

        assert "No results found" in result

    @pytest.mark.asyncio
    async def test_search_size_limit(self, indexed_test_data, mock_es_client):
        """Test that size parameter limits results."""
        result = await tools.search_emails(
            query="Maven",
            list_name=indexed_test_data["list_name"],
            size=1,
        )

        # Should show only 1 result
        assert "showing 1" in result


class TestGetMessage:
    """Tests for the get_message tool."""

    @pytest.mark.asyncio
    async def test_get_message_by_id(self, indexed_test_data, mock_es_client):
        """Test retrieving a specific message."""
        result = await tools.get_message(
            message_id="<release-vote@maven.apache.org>",
            list_name=indexed_test_data["list_name"],
        )

        assert "=== Email Message ===" in result
        assert "Release Maven 4.0.0" in result
        assert "release-manager@apache.org" in result
        assert "MNG-7891" in result
        assert "vote on releasing" in result

    @pytest.mark.asyncio
    async def test_get_message_without_brackets(self, indexed_test_data, mock_es_client):
        """Test retrieving message with ID without angle brackets."""
        result = await tools.get_message(
            message_id="release-vote@maven.apache.org",  # Without < >
            list_name=indexed_test_data["list_name"],
        )

        assert "=== Email Message ===" in result
        assert "Release Maven 4.0.0" in result

    @pytest.mark.asyncio
    async def test_get_message_not_found(self, indexed_test_data, mock_es_client):
        """Test retrieving non-existent message."""
        result = await tools.get_message(
            message_id="<nonexistent@example.com>",
            list_name=indexed_test_data["list_name"],
        )

        assert "Message not found" in result

    @pytest.mark.asyncio
    async def test_get_message_with_threading_info(self, indexed_test_data, mock_es_client):
        """Test that reply messages show threading info."""
        result = await tools.get_message(
            message_id="<reply-vote@maven.apache.org>",
            list_name=indexed_test_data["list_name"],
        )

        assert "In-Reply-To" in result
        assert "release-vote@maven.apache.org" in result


class TestGetThread:
    """Tests for the get_thread tool."""

    @pytest.mark.asyncio
    async def test_get_thread_from_root(self, indexed_test_data, mock_es_client):
        """Test retrieving thread starting from root message."""
        result = await tools.get_thread(
            message_id="<release-vote@maven.apache.org>",
            list_name=indexed_test_data["list_name"],
        )

        assert "=== Email Thread" in result
        assert "Release Maven 4.0.0" in result

    @pytest.mark.asyncio
    async def test_get_thread_from_reply(self, indexed_test_data, mock_es_client):
        """Test retrieving thread starting from a reply message."""
        result = await tools.get_thread(
            message_id="<reply-vote@maven.apache.org>",
            list_name=indexed_test_data["list_name"],
        )

        # Should find the thread and include related messages
        assert "Thread" in result or "Email Message" in result

    @pytest.mark.asyncio
    async def test_get_thread_single_message(self, indexed_test_data, mock_es_client):
        """Test retrieving 'thread' for standalone message."""
        result = await tools.get_thread(
            message_id="<discussion@maven.apache.org>",
            list_name=indexed_test_data["list_name"],
        )

        # Should return something (either thread or single message)
        assert "Discussion about build improvements" in result or "build performance" in result


class TestSearchByContributor:
    """Tests for the search_by_contributor tool."""

    @pytest.mark.asyncio
    async def test_search_by_email(self, indexed_test_data, mock_es_client):
        """Test searching by contributor email."""
        result = await tools.search_by_contributor(
            contributor="release-manager@apache.org",
            list_name=indexed_test_data["list_name"],
        )

        assert "Found" in result
        assert "Release Manager" in result

    @pytest.mark.asyncio
    async def test_search_by_partial_email(self, indexed_test_data, mock_es_client):
        """Test searching by partial email address."""
        result = await tools.search_by_contributor(
            contributor="release-manager",
            list_name=indexed_test_data["list_name"],
        )

        assert "Found" in result
        assert "release-manager@apache.org" in result

    @pytest.mark.asyncio
    async def test_search_by_name(self, indexed_test_data, mock_es_client):
        """Test searching by contributor name."""
        result = await tools.search_by_contributor(
            contributor="Contributor",
            list_name=indexed_test_data["list_name"],
        )

        assert "Found" in result
        assert "John Contributor" in result

    @pytest.mark.asyncio
    async def test_search_contributor_not_found(self, indexed_test_data, mock_es_client):
        """Test searching for non-existent contributor."""
        result = await tools.search_by_contributor(
            contributor="nonexistent-user-xyz",
            list_name=indexed_test_data["list_name"],
        )

        assert "No emails found" in result


class TestFindReferences:
    """Tests for the find_references tool."""

    @pytest.mark.asyncio
    async def test_find_jira_reference(self, indexed_test_data, mock_es_client):
        """Test finding emails by JIRA reference."""
        result = await tools.find_references(
            reference="MNG-7891",
            reference_type="jira",
            list_name=indexed_test_data["list_name"],
        )

        assert "Found" in result
        assert "MNG-7891" in result
        assert "Release Maven 4.0.0" in result

    @pytest.mark.asyncio
    async def test_find_github_pr_reference(self, indexed_test_data, mock_es_client):
        """Test finding emails by GitHub PR reference."""
        result = await tools.find_references(
            reference="5678",
            reference_type="github_pr",
            list_name=indexed_test_data["list_name"],
        )

        assert "Found" in result
        assert "5678" in result

    @pytest.mark.asyncio
    async def test_find_reference_not_found(self, indexed_test_data, mock_es_client):
        """Test finding non-existent reference."""
        result = await tools.find_references(
            reference="MNG-99999",
            reference_type="jira",
            list_name=indexed_test_data["list_name"],
        )

        assert "No emails found" in result

    @pytest.mark.asyncio
    async def test_find_reference_invalid_type(self, indexed_test_data, mock_es_client):
        """Test with invalid reference type."""
        result = await tools.find_references(
            reference="something",
            reference_type="invalid",
            list_name=indexed_test_data["list_name"],
        )

        assert "Invalid reference_type" in result