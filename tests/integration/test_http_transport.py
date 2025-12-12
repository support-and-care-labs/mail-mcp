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

"""Integration tests for HTTP transport (Streamable HTTP)."""

import json

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from mail_mcp.server.server import create_server


@pytest.fixture
def mcp_server():
    """Create a fresh MCP server instance for each test."""
    return create_server()


@pytest.fixture
def mcp_app(mcp_server):
    """Get the MCP ASGI app for testing with middleware."""
    from mail_mcp.server.middleware import StaleSessionMiddleware

    app = mcp_server.streamable_http_app()
    # Add middleware to transform stale session errors from 400 to 404
    app.add_middleware(StaleSessionMiddleware)
    return app


@pytest.fixture
async def async_client(mcp_app):
    """
    Create an async HTTP client for testing the app with lifespan support.

    Uses LifespanManager to properly initialize the app's lifespan handler,
    which initializes the task group required by Streamable HTTP transport.
    """
    async with LifespanManager(mcp_app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test"
        ) as client:
            yield client


class TestCustomEndpoints:
    """Tests for custom HTTP endpoints (/health, /info)."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client):
        """Test health check endpoint returns healthy status."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "maven-mail-mcp"
        assert "elasticsearch_url" in data

    @pytest.mark.asyncio
    async def test_info_endpoint(self, async_client):
        """Test info endpoint returns server information."""
        response = await async_client.get("/info")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "maven-mail-mcp"
        assert data["version"] == "1.0.0"
        assert "tools" in data
        assert len(data["tools"]) == 5

        tool_names = [t["name"] for t in data["tools"]]
        assert "search_emails" in tool_names
        assert "get_message" in tool_names
        assert "get_thread" in tool_names
        assert "find_references" in tool_names
        assert "search_by_contributor" in tool_names


class TestMcpEndpoint:
    """Tests for MCP protocol endpoint."""

    @pytest.mark.asyncio
    async def test_mcp_endpoint_requires_accept_header(self, async_client):
        """Test MCP endpoint requires proper Accept header."""
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"}
                }
            },
            headers={"Content-Type": "application/json"}
        )

        # Should fail without proper Accept header
        assert response.status_code == 406
        assert "Not Acceptable" in response.text

    @pytest.mark.asyncio
    async def test_mcp_initialize(self, async_client):
        """Test MCP initialize request with proper headers."""
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"}
                }
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )

        assert response.status_code == 200

        # Response is SSE format
        content = response.text
        assert content.startswith("event: message")
        assert "data:" in content

        # Parse the data line
        for line in content.split("\n"):
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                assert data["jsonrpc"] == "2.0"
                assert data["id"] == 1
                assert "result" in data

                result = data["result"]
                assert result["protocolVersion"] == "2024-11-05"
                assert result["serverInfo"]["name"] == "maven-mail-mcp"
                assert "capabilities" in result
                assert "tools" in result["capabilities"]
                break
        else:
            pytest.fail("No data line found in SSE response")

    @pytest.mark.asyncio
    async def test_mcp_tools_list(self, async_client):
        """Test listing available MCP tools."""
        # First initialize
        init_response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"}
                }
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        assert init_response.status_code == 200

        # Get session ID from response header
        session_id = init_response.headers.get("mcp-session-id")

        # Then list tools
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if session_id:
            headers["mcp-session-id"] = session_id

        tools_response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            },
            headers=headers
        )

        assert tools_response.status_code == 200

        # Parse SSE response
        content = tools_response.text
        for line in content.split("\n"):
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                if "result" in data and "tools" in data["result"]:
                    tools = data["result"]["tools"]
                    tool_names = [t["name"] for t in tools]
                    assert "search_emails" in tool_names
                    assert "get_message" in tool_names
                    assert "get_thread" in tool_names
                    break


class TestSessionHandling:
    """Tests for MCP session handling."""

    @pytest.mark.asyncio
    async def test_stale_session_returns_404(self, async_client):
        """Test that a stale/invalid session ID returns 404 Not Found.

        This verifies the expected behavior after server restart:
        clients sending old session IDs should receive 404,
        prompting them to re-initialize their session.

        The StaleSessionMiddleware transforms the MCP SDK's default 400 response
        to 404 "Invalid or expired session ID" for better client handling.
        """
        response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": "stale-session-id-after-restart"
            }
        )

        # Our middleware transforms SDK's 400 to 404 for stale sessions
        assert response.status_code == 404
        assert "Invalid or expired session ID" in response.text


class TestTransportInitialization:
    """Tests for transport initialization (task group)."""

    @pytest.mark.asyncio
    async def test_app_starts_correctly(self, mcp_app):
        """Test that the ASGI app initializes correctly with lifespan."""
        # This test verifies the fix for "Task group is not initialized" error
        async with LifespanManager(mcp_app) as manager:
            async with AsyncClient(
                transport=ASGITransport(app=manager.app),
                base_url="http://test"
            ) as client:
                # If the app starts without error, lifespan is working
                response = await client.get("/health")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_multiple_requests_in_session(self, async_client):
        """Test that multiple requests can be made in the same session."""
        # Health check
        health_response = await async_client.get("/health")
        assert health_response.status_code == 200

        # Info check
        info_response = await async_client.get("/info")
        assert info_response.status_code == 200

        # MCP request
        mcp_response = await async_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0.0"}
                }
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        assert mcp_response.status_code == 200
