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

"""Main entry point for Maven MCP server."""

import argparse

import structlog

# MUST import logging_config FIRST to configure stderr output
import mail_mcp.logging_config  # noqa: F401
from mail_mcp.config import settings
from mail_mcp.server.server import server

logger = structlog.get_logger(__name__)


def run_server():
    """Entry point for running the server via command line."""
    parser = argparse.ArgumentParser(
        description="Maven Mail MCP Server - Access Apache Maven mailing list archives"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (default) or http"
    )
    parser.add_argument(
        "--host",
        default=settings.server_host,
        help=f"HTTP host to bind to (default: {settings.server_host})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.server_port,
        help=f"HTTP port to bind to (default: {settings.server_port})"
    )

    args = parser.parse_args()

    logger.info(
        "starting_mcp_server",
        transport=args.transport,
        elasticsearch_url=settings.elasticsearch_url,
        index_prefix=settings.elasticsearch_index_prefix,
    )

    if args.transport == "stdio":
        # FastMCP handles stdio transport automatically
        server.run()
    else:
        # HTTP transport using Streamable HTTP (MCP 2025-03-26 spec)
        # Custom routes (/health, /info) are registered via @server.custom_route in server.py
        # streamable_http_app() includes them and handles /mcp endpoint
        import uvicorn

        logger.info(
            "starting_http_server",
            host=args.host,
            port=args.port
        )

        # Get the app with proper lifespan handling for task group initialization
        app = server.streamable_http_app()

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=settings.log_level.lower()
        )


if __name__ == "__main__":
    run_server()
