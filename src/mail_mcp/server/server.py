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

"""MCP server implementation for Maven mailing list archives."""

# MUST import logging_config FIRST to configure stderr output

import structlog
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import mail_mcp.logging_config  # noqa: F401
from mail_mcp.config import settings
from mail_mcp.server.tools import (
    find_references,
    get_message,
    get_thread,
    search_by_contributor,
    search_emails,
)

logger = structlog.get_logger(__name__)


def create_server() -> FastMCP:
    """
    Create and configure the MCP server for Maven mailing list archives.

    Returns:
        Configured FastMCP server instance
    """
    # Create FastMCP server
    mcp = FastMCP(
        name="maven-mail-mcp",
        instructions="""
        Maven Mailing List Archive Server

        This server provides access to Apache Maven mailing list archives,
        with support for searching discussions, retrieving messages, and
        analyzing threads.

        Available tools:
        - search_emails: Full-text search across email archives (with optional from_address filter)
        - search_by_contributor: Find all emails from a specific contributor
        - get_message: Retrieve a specific message by ID
        - get_thread: Retrieve an entire email thread
        - find_references: Find emails referencing JIRA issues or GitHub PRs

        The archives include discussions from dev@maven.apache.org and other
        Maven project mailing lists, indexed with metadata extraction for
        JIRA references, GitHub references, version numbers, and decisions.
        """,
        debug=settings.log_level == "DEBUG",
    )

    # Register tools
    mcp.add_tool(search_emails)
    mcp.add_tool(search_by_contributor)
    mcp.add_tool(get_message)
    mcp.add_tool(get_thread)
    mcp.add_tool(find_references)

    # Register custom HTTP endpoints (included in streamable_http_app)
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> Response:
        """Health check endpoint for container orchestration."""
        return JSONResponse({
            "status": "healthy",
            "service": "maven-mail-mcp",
            "elasticsearch_url": settings.elasticsearch_url
        })

    @mcp.custom_route("/info", methods=["GET"])
    async def server_info_route(request: Request) -> Response:
        """Get MCP server information and capabilities."""
        return JSONResponse({
            "name": "maven-mail-mcp",
            "version": "1.0.0",
            "tools": [
                {"name": "search_emails", "description": "Search archives"},
                {"name": "search_by_contributor", "description": "Find by contributor"},
                {"name": "get_message", "description": "Get message by ID"},
                {"name": "get_thread", "description": "Get email thread"},
                {"name": "find_references", "description": "Find JIRA/GitHub refs"}
            ],
            "note": "For full MCP protocol support, use /mcp endpoint with an MCP client"
        })

    logger.info(
        "mcp_server_created",
        name="maven-mail-mcp",
        tools=[
            "search_emails", "search_by_contributor",
            "get_message", "get_thread", "find_references"
        ],
    )

    return mcp


# Create global server instance
server = create_server()
