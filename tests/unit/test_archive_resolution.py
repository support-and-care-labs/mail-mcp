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

"""Unit tests for archive URL resolution."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mail_mcp.ponymail import (
    get_archive_url,
    lookup_mid_by_search,
    PonymailResolver,
)


class TestGetArchiveUrl:
    """Tests for get_archive_url function."""

    def test_generates_correct_url(self):
        """Test that archive URL is correctly generated from mid."""
        mid = "abc123def456"
        url = get_archive_url(mid)
        assert url == "https://lists.apache.org/thread/abc123def456"

    def test_handles_empty_mid(self):
        """Test with empty mid."""
        url = get_archive_url("")
        assert url == "https://lists.apache.org/thread/"


class TestLookupMidBySearch:
    """Tests for lookup_mid_by_search function."""

    @pytest.mark.asyncio
    async def test_returns_mid_when_found(self):
        """Test successful mid lookup."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "emails": [
                {"message-id": "<test@example.com>", "mid": "found123"},
                {"message-id": "<other@example.com>", "mid": "other456"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await lookup_mid_by_search(
                message_id="<test@example.com>",
                list_name="dev@maven.apache.org",
            )

            assert result == "found123"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Test when message is not in search results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "emails": [
                {"message-id": "<other@example.com>", "mid": "other456"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await lookup_mid_by_search(
                message_id="<notfound@example.com>",
                list_name="dev@maven.apache.org",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_handles_http_error(self):
        """Test graceful handling of HTTP errors."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )

            result = await lookup_mid_by_search(
                message_id="<test@example.com>",
                list_name="dev@maven.apache.org",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """Test graceful handling of timeout."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )

            result = await lookup_mid_by_search(
                message_id="<test@example.com>",
                list_name="dev@maven.apache.org",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_normalizes_message_id(self):
        """Test that angle brackets are handled correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "emails": [
                {"message-id": "test@example.com", "mid": "found123"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            # Test with brackets
            result = await lookup_mid_by_search(
                message_id="<test@example.com>",
                list_name="dev@maven.apache.org",
            )
            assert result == "found123"


class TestPonymailResolver:
    """Tests for PonymailResolver class."""

    @pytest.mark.asyncio
    async def test_returns_cached_mid(self):
        """Test that cached mid is returned without API call."""
        mock_es = AsyncMock()
        mock_es.get_document = AsyncMock(return_value={
            "message_id": "<test@example.com>",
            "archive_mid": "cached123",
        })

        resolver = PonymailResolver(mock_es)

        with patch("mail_mcp.ponymail.lookup_mid_by_search") as mock_lookup:
            result = await resolver.resolve_url(
                message_id="<test@example.com>",
                list_name="dev@maven.apache.org",
            )

            assert result == "https://lists.apache.org/thread/cached123"
            # Verify no API call was made
            mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_looks_up_and_caches_mid(self):
        """Test that mid is looked up and cached when not in cache."""
        mock_es = AsyncMock()
        mock_es.get_document = AsyncMock(return_value={
            "message_id": "<test@example.com>",
            # No archive_mid - not cached
        })
        mock_es.update_document = AsyncMock(return_value=True)

        resolver = PonymailResolver(mock_es)

        with patch(
            "mail_mcp.ponymail.lookup_mid_by_search",
            new_callable=AsyncMock,
            return_value="newmid456"
        ):
            result = await resolver.resolve_url(
                message_id="<test@example.com>",
                list_name="dev@maven.apache.org",
            )

            assert result == "https://lists.apache.org/thread/newmid456"
            # Verify cache was updated
            mock_es.update_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_lookup_fails(self):
        """Test graceful handling when lookup returns None."""
        mock_es = AsyncMock()
        mock_es.get_document = AsyncMock(return_value={
            "message_id": "<test@example.com>",
        })

        resolver = PonymailResolver(mock_es)

        with patch(
            "mail_mcp.ponymail.lookup_mid_by_search",
            new_callable=AsyncMock,
            return_value=None
        ):
            result = await resolver.resolve_url(
                message_id="<test@example.com>",
                list_name="dev@maven.apache.org",
            )

            assert result is None
