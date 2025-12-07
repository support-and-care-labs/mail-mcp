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

"""Integration tests for Elasticsearch client using Testcontainers."""

from datetime import datetime

import pytest

from mail_mcp.storage.schema import get_index_name


@pytest.mark.asyncio
async def test_elasticsearch_connection(es_client):
    """Test that we can connect to Elasticsearch."""
    assert es_client._client is not None
    info = await es_client._client.info()
    assert info["version"]["number"].startswith("8.11")


@pytest.mark.asyncio
async def test_create_index(es_client, test_settings, clean_elasticsearch):
    """Test creating an index with the correct schema."""
    list_name = "dev@maven.apache.org"

    # Create index
    await es_client.create_index(list_name)

    # Verify index exists
    # NOTE: ElasticsearchClient uses global settings, not test_settings
    index_name = get_index_name("maven", list_name)
    exists = await es_client._client.indices.exists(index=index_name)
    assert exists


@pytest.mark.asyncio
async def test_index_and_retrieve_document(es_client, test_settings, clean_elasticsearch):
    """Test indexing and retrieving an email document."""
    list_name = "dev@maven.apache.org"

    # Create index first
    await es_client.create_index(list_name)

    # Create a test document (as dict)
    doc = {
        "message_id": "<test@example.com>",
        "subject": "Test Email",
        "from_address": "sender@example.com",
        "from_name": "Test Sender",
        "date": datetime(2024, 1, 1, 12, 0, 0),
        "to": ["recipient@example.com"],
        "cc": [],
        "list_address": "dev@maven.apache.org",
        "in_reply_to": None,
        "references": [],
        "body_full": "This is a test email body.",
        "body_effective": "This is a test email body.",
        "quote_percentage": 0.0,
        "jira_references": ["MNG-1234"],
        "github_pr_references": [],
        "github_commit_references": [],
        "version_numbers": ["4.0.0"],
        "decision_keywords": [],
        "has_vote": False,
        "vote_value": None,
    }

    # Index the document
    await es_client.index_document(list_name, doc["message_id"], doc)

    # Refresh index to make document searchable
    # NOTE: ElasticsearchClient uses global settings, not test_settings
    index_name = get_index_name("maven", list_name)
    await es_client._client.indices.refresh(index=index_name)

    # Retrieve the document
    retrieved = await es_client.get_document(list_name, "<test@example.com>")

    assert retrieved is not None
    assert retrieved["message_id"] == "<test@example.com>"
    assert retrieved["subject"] == "Test Email"
    assert retrieved["from_address"] == "sender@example.com"
    assert retrieved["jira_references"] == ["MNG-1234"]
    assert retrieved["version_numbers"] == ["4.0.0"]


@pytest.mark.asyncio
async def test_search_all_documents(es_client, test_settings, clean_elasticsearch):
    """Test searching for all documents."""
    list_name = "dev@maven.apache.org"

    # Create index
    await es_client.create_index(list_name)

    # Index multiple documents
    for i in range(1, 4):
        doc = {
            "message_id": f"<test{i}@example.com>",
            "subject": f"Test Email {i}",
            "from_address": "sender@example.com",
            "from_name": "Test Sender",
            "date": datetime(2024, 1, i, 12, 0, 0),
            "to": ["recipient@example.com"],
            "cc": [],
            "list_address": "dev@maven.apache.org",
            "in_reply_to": None,
            "references": [],
            "body_full": f"This is test email number {i}.",
            "body_effective": f"This is test email number {i}.",
            "quote_percentage": 0.0,
            "jira_references": [],
            "github_pr_references": [],
            "github_commit_references": [],
            "version_numbers": [],
            "decision_keywords": [],
            "has_vote": False,
            "vote_value": None,
        }
        await es_client.index_document(list_name, doc["message_id"], doc)

    # Refresh index
    # NOTE: ElasticsearchClient uses global settings, not test_settings
    index_name = get_index_name("maven", list_name)
    await es_client._client.indices.refresh(index=index_name)

    # Search for all documents
    query = {"match_all": {}}
    results = await es_client.search(list_name, query, size=10)

    assert results["hits"]["total"]["value"] == 3
    assert len(results["hits"]["hits"]) == 3


@pytest.mark.asyncio
async def test_search_by_subject(es_client, test_settings, clean_elasticsearch):
    """Test full-text search on subject field."""
    list_name = "dev@maven.apache.org"

    # Create index
    await es_client.create_index(list_name)

    # Index documents with different subjects
    docs = [
        {
            "message_id": "<maven@example.com>",
            "subject": "Maven Release 4.0.0",
            "from_address": "dev@maven.apache.org",
            "from_name": "Maven Dev",
            "date": datetime(2024, 1, 1, 12, 0, 0),
            "to": ["users@maven.apache.org"],
            "cc": [],
            "list_address": "dev@maven.apache.org",
            "body_full": "We are releasing Maven 4.0.0 with new features.",
            "body_effective": "We are releasing Maven 4.0.0 with new features.",
            "jira_references": ["MNG-1234"],
            "version_numbers": ["4.0.0"],
            "has_vote": False,
        },
        {
            "message_id": "<gradle@example.com>",
            "subject": "Gradle Build Tool",
            "from_address": "user@example.com",
            "from_name": "User",
            "date": datetime(2024, 1, 2, 12, 0, 0),
            "to": ["dev@maven.apache.org"],
            "cc": [],
            "list_address": "dev@maven.apache.org",
            "body_full": "Discussing Gradle as an alternative build tool.",
            "body_effective": "Discussing Gradle as an alternative build tool.",
            "jira_references": [],
            "version_numbers": [],
            "has_vote": False,
        },
    ]

    for doc in docs:
        await es_client.index_document(list_name, doc["message_id"], doc)

    # Refresh index
    # NOTE: ElasticsearchClient uses global settings, not test_settings
    index_name = get_index_name("maven", list_name)
    await es_client._client.indices.refresh(index=index_name)

    # Search for "Maven"
    query = {"match": {"subject": "Maven"}}
    results = await es_client.search(list_name, query, size=10)

    assert results["hits"]["total"]["value"] == 1
    assert results["hits"]["hits"][0]["_source"]["message_id"] == "<maven@example.com>"


@pytest.mark.asyncio
async def test_search_with_jira_filter(es_client, test_settings, clean_elasticsearch):
    """Test search with JIRA reference filter."""
    list_name = "dev@maven.apache.org"

    # Create index
    await es_client.create_index(list_name)

    # Index documents - only first has JIRA reference
    for i in range(1, 4):
        doc = {
            "message_id": f"<test{i}@example.com>",
            "subject": f"Test {i}",
            "from_address": f"sender{i}@example.com",
            "from_name": f"Sender {i}",
            "date": datetime(2024, 1, i, 12, 0, 0),
            "to": ["recipient@example.com"],
            "list_address": "dev@maven.apache.org",
            "body_full": f"Body {i}",
            "body_effective": f"Body {i}",
            "jira_references": ["MNG-1234"] if i == 1 else [],
            "has_vote": False,
        }
        await es_client.index_document(list_name, doc["message_id"], doc)

    # Refresh index
    # NOTE: ElasticsearchClient uses global settings, not test_settings
    index_name = get_index_name("maven", list_name)
    await es_client._client.indices.refresh(index=index_name)

    # Search for documents with JIRA references
    query = {"bool": {"must": [{"exists": {"field": "jira_references"}}]}}
    results = await es_client.search(list_name, query, size=10)

    assert results["hits"]["total"]["value"] == 1
    assert results["hits"]["hits"][0]["_source"]["message_id"] == "<test1@example.com>"


@pytest.mark.asyncio
async def test_index_naming_no_double_prefix(es_client, test_settings, clean_elasticsearch):
    """Test that indexing creates correct index name without double prefix."""
    list_name = "dev@maven.apache.org"

    # Create index
    await es_client.create_index(list_name)

    # Index a document
    message_id = "<test@example.com>"
    doc = {
        "message_id": message_id,
        "subject": "Test",
        "from_address": "sender@example.com",
        "from_name": "Sender",
        "date": datetime(2024, 1, 1, 12, 0, 0),
        "to": ["recipient@example.com"],
        "list_address": "dev@maven.apache.org",
        "body_full": "Body",
        "body_effective": "Body",
        "jira_references": [],
        "has_vote": False,
    }
    await es_client.index_document(list_name, message_id, doc)

    # Get all indices
    indices = await es_client._client.indices.get(index="*")
    index_names = list(indices.keys())

    # Expected index name: maven-dev (current global settings use "maven" prefix)
    # NOTE: ElasticsearchClient uses global settings, not test_settings
    expected_index = "maven-dev"

    # Check that correct index exists
    assert expected_index in index_names, f"Expected index '{expected_index}' not found. Found: {index_names}"

    # Check that NO double-prefixed index exists (maven-maven-dev)
    double_prefix = "maven-maven-dev"
    assert double_prefix not in index_names, f"Found incorrect double-prefixed index: {double_prefix}"

    # Verify document is in correct index
    await es_client._client.indices.refresh(index=expected_index)
    result = await es_client.get_document(list_name, message_id)
    assert result is not None
    assert result["message_id"] == message_id
