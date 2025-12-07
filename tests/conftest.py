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

"""Pytest fixtures for mail-mcp tests."""

import pytest
from testcontainers.elasticsearch import ElasticSearchContainer

from mail_mcp.config import Settings
from mail_mcp.storage.elasticsearch import ElasticsearchClient


@pytest.fixture(scope="session")
def elasticsearch_container():
    """
    Start an Elasticsearch container for testing.

    Uses Testcontainers to spin up a real Elasticsearch instance.
    The container is shared across all tests in the session for performance.
    """
    container = ElasticSearchContainer("elasticsearch:8.11.0")
    container.start()

    yield container

    container.stop()


@pytest.fixture(scope="session")
def elasticsearch_url(elasticsearch_container):
    """Get the URL for the test Elasticsearch instance."""
    return elasticsearch_container.get_url()


@pytest.fixture
def test_settings(elasticsearch_url):
    """
    Create test settings that point to the Testcontainers Elasticsearch.

    Each test gets a fresh settings instance.
    """
    return Settings(
        elasticsearch_url=elasticsearch_url,
        elasticsearch_index_prefix="test",
        elasticsearch_timeout=30,
        elasticsearch_max_retries=3,
    )


@pytest.fixture
async def es_client(test_settings):
    """
    Create an Elasticsearch client connected to the test container.

    The client is automatically connected and closed.
    """
    client = ElasticsearchClient(url=test_settings.elasticsearch_url)
    await client.connect()

    yield client

    await client.close()


@pytest.fixture
async def clean_elasticsearch(es_client):
    """
    Clean up Elasticsearch indices before each test.

    Ensures tests start with a clean slate.
    """
    # Get all indices
    if es_client._client:
        indices = await es_client._client.indices.get(index="*")
        # Delete all test indices (both test- and maven- prefixes)
        # NOTE: ElasticsearchClient uses global settings with "maven" prefix
        for index_name in indices.keys():
            if index_name.startswith("test-") or index_name.startswith("maven-"):
                await es_client._client.indices.delete(index=index_name)

    yield

    # Clean up after test as well
    if es_client._client:
        indices = await es_client._client.indices.get(index="*")
        for index_name in indices.keys():
            if index_name.startswith("test-") or index_name.startswith("maven-"):
                await es_client._client.indices.delete(index=index_name)
