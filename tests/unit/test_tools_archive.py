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

"""Unit tests for archive URL resolution in MCP tools."""

from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


class TestResolveArchiveUrl:
    """Tests for resolve_archive_url function."""

    @pytest.mark.asyncio
    async def test_returns_cached_url(self):
        """Test that cached archive_mid is used without API call."""
        from mail_mcp.server.tools import resolve_archive_url

        source = {
            "message_id": "<test@example.com>",
            "archive_mid": "cached123",
        }
        mock_es = AsyncMock()

        result = await resolve_archive_url(source, "dev@maven.apache.org", mock_es)

        assert result == "https://lists.apache.org/thread/cached123"

    @pytest.mark.asyncio
    async def test_resolves_when_not_cached(self):
        """Test that mid is resolved via API when not cached."""
        from mail_mcp.server.tools import resolve_archive_url

        source = {
            "message_id": "<test@example.com>",
            "subject": "Test Subject",
            "date": "2024-12-01T10:00:00+00:00",
        }
        mock_es = AsyncMock()

        with patch("mail_mcp.server.tools.settings") as mock_settings:
            mock_settings.resolve_archive_urls = True

            with patch("mail_mcp.server.tools.PonymailResolver") as MockResolver:
                mock_resolver_instance = AsyncMock()
                mock_resolver_instance.resolve_url = AsyncMock(
                    return_value="https://lists.apache.org/thread/newmid456"
                )
                MockResolver.return_value = mock_resolver_instance

                result = await resolve_archive_url(
                    source, "dev@maven.apache.org", mock_es
                )

                assert result == "https://lists.apache.org/thread/newmid456"
                mock_resolver_instance.resolve_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_respects_disabled_setting(self):
        """Test that resolution is skipped when setting is disabled."""
        from mail_mcp.server.tools import resolve_archive_url

        source = {
            "message_id": "<test@example.com>",
            "subject": "Test Subject",
        }
        mock_es = AsyncMock()

        with patch("mail_mcp.server.tools.settings") as mock_settings:
            mock_settings.resolve_archive_urls = False

            with patch("mail_mcp.server.tools.PonymailResolver") as MockResolver:
                result = await resolve_archive_url(
                    source, "dev@maven.apache.org", mock_es
                )

                assert result is None
                # Resolver should not be instantiated
                MockResolver.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_resolution_error(self):
        """Test graceful handling of resolution errors."""
        from mail_mcp.server.tools import resolve_archive_url

        source = {
            "message_id": "<test@example.com>",
            "subject": "Test Subject",
        }
        mock_es = AsyncMock()

        with patch("mail_mcp.server.tools.settings") as mock_settings:
            mock_settings.resolve_archive_urls = True

            with patch("mail_mcp.server.tools.PonymailResolver") as MockResolver:
                mock_resolver_instance = AsyncMock()
                mock_resolver_instance.resolve_url = AsyncMock(
                    side_effect=Exception("Network error")
                )
                MockResolver.return_value = mock_resolver_instance

                result = await resolve_archive_url(
                    source, "dev@maven.apache.org", mock_es
                )

                # Should return None, not raise exception
                assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_message_id(self):
        """Test that None is returned when message_id is missing."""
        from mail_mcp.server.tools import resolve_archive_url

        source = {
            "subject": "Test Subject",
            # No message_id
        }
        mock_es = AsyncMock()

        with patch("mail_mcp.server.tools.settings") as mock_settings:
            mock_settings.resolve_archive_urls = True

            result = await resolve_archive_url(
                source, "dev@maven.apache.org", mock_es
            )

            assert result is None


class TestFormatArchiveUrl:
    """Tests for format_archive_url function."""

    def test_returns_url_when_cached(self):
        """Test URL generation from cached mid."""
        from mail_mcp.server.tools import format_archive_url

        source = {"archive_mid": "abc123"}
        result = format_archive_url(source)

        assert result == "https://lists.apache.org/thread/abc123"

    def test_returns_none_when_not_cached(self):
        """Test None is returned when no cached mid."""
        from mail_mcp.server.tools import format_archive_url

        source = {"message_id": "<test@example.com>"}
        result = format_archive_url(source)

        assert result is None

    def test_returns_none_for_empty_source(self):
        """Test None is returned for empty source dict."""
        from mail_mcp.server.tools import format_archive_url

        result = format_archive_url({})

        assert result is None


class TestSettingsToggle:
    """Tests for the MAIL_MCP_RESOLVE_ARCHIVE_URLS setting."""

    def test_default_is_true(self):
        """Test that resolve_archive_urls defaults to True."""
        from mail_mcp.config import Settings

        settings = Settings()
        assert settings.resolve_archive_urls is True

    def test_can_be_disabled_via_env(self):
        """Test that setting can be disabled via environment variable."""
        import os
        from mail_mcp.config import Settings

        with patch.dict(os.environ, {"MAIL_MCP_RESOLVE_ARCHIVE_URLS": "false"}):
            settings = Settings()
            assert settings.resolve_archive_urls is False

    def test_can_be_enabled_via_env(self):
        """Test that setting can be explicitly enabled via environment variable."""
        import os
        from mail_mcp.config import Settings

        with patch.dict(os.environ, {"MAIL_MCP_RESOLVE_ARCHIVE_URLS": "true"}):
            settings = Settings()
            assert settings.resolve_archive_urls is True
