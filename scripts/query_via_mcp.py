#!/usr/bin/env python3
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

"""
Query Maven mailing list archives via MCP server.

This script demonstrates how to use the MCP client to query the mail-mcp
server programmatically. It's useful for testing the MCP tools and for
debugging search results.

Usage:
    poetry run python scripts/query_via_mcp.py <command> [options]

Commands:
    search <query>     - Search emails by keyword
    message <id>       - Get a specific message by Message-ID
    thread <id>        - Get the thread containing a message
    contributor <name> - Find emails from a contributor
    jira <issue>       - Find emails mentioning a JIRA issue
    github <pr>        - Find emails mentioning a GitHub PR

Prerequisites:
    - Elasticsearch must be running with indexed email data
    - The MCP server will be started automatically via stdio transport

Examples:
    # Search for release-related emails
    poetry run python scripts/query_via_mcp.py search "release 4.0"

    # Get a specific message
    poetry run python scripts/query_via_mcp.py message "<abc@example.com>"

    # Find emails from a contributor
    poetry run python scripts/query_via_mcp.py contributor "john@example.com"

    # Find emails about a JIRA issue
    poetry run python scripts/query_via_mcp.py jira "MNG-7891"
"""

import argparse
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def search_emails(session: ClientSession, query: str, size: int = 5):
    """Search emails using the MCP search_emails tool."""
    print(f"Searching for: {query}\n")
    print("=" * 80)

    result = await session.call_tool("search_emails", arguments={"query": query, "size": size})

    for content in result.content:
        if hasattr(content, "text"):
            print(content.text)


async def get_message(session: ClientSession, message_id: str):
    """Get a specific message using the MCP get_message tool."""
    print(f"Retrieving message: {message_id}\n")
    print("=" * 80)

    result = await session.call_tool("get_message", arguments={"message_id": message_id})

    for content in result.content:
        if hasattr(content, "text"):
            print(content.text)


async def get_thread(session: ClientSession, message_id: str, max_messages: int = 20):
    """Get a thread using the MCP get_thread tool."""
    print(f"Retrieving thread for: {message_id}\n")
    print("=" * 80)

    result = await session.call_tool(
        "get_thread", arguments={"message_id": message_id, "max_messages": max_messages}
    )

    for content in result.content:
        if hasattr(content, "text"):
            print(content.text)


async def search_contributor(session: ClientSession, contributor: str, size: int = 10):
    """Search emails from a contributor using the MCP search_by_contributor tool."""
    print(f"Searching for emails from: {contributor}\n")
    print("=" * 80)

    result = await session.call_tool(
        "search_by_contributor", arguments={"contributor": contributor, "size": size}
    )

    for content in result.content:
        if hasattr(content, "text"):
            print(content.text)


async def find_jira(session: ClientSession, issue: str, size: int = 10):
    """Find emails mentioning a JIRA issue."""
    print(f"Finding emails referencing: {issue}\n")
    print("=" * 80)

    result = await session.call_tool(
        "find_references", arguments={"reference": issue, "reference_type": "jira", "size": size}
    )

    for content in result.content:
        if hasattr(content, "text"):
            print(content.text)


async def find_github(session: ClientSession, pr: str, size: int = 10):
    """Find emails mentioning a GitHub PR."""
    print(f"Finding emails referencing GitHub PR: #{pr}\n")
    print("=" * 80)

    result = await session.call_tool(
        "find_references", arguments={"reference": pr, "reference_type": "github_pr", "size": size}
    )

    for content in result.content:
        if hasattr(content, "text"):
            print(content.text)


async def run_command(args):
    """Run the specified command via MCP client."""
    server_params = StdioServerParameters(
        command="poetry",
        args=["run", "maven-mail-mcp", "--transport", "stdio"],
        env=None,
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                if args.command == "search":
                    await search_emails(session, args.query, args.size)
                elif args.command == "message":
                    await get_message(session, args.id)
                elif args.command == "thread":
                    await get_thread(session, args.id, args.max_messages)
                elif args.command == "contributor":
                    await search_contributor(session, args.name, args.size)
                elif args.command == "jira":
                    await find_jira(session, args.issue, args.size)
                elif args.command == "github":
                    await find_github(session, args.pr, args.size)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nMake sure:", file=sys.stderr)
        print("  1. Elasticsearch is running: docker compose up -d elasticsearch", file=sys.stderr)
        print("  2. Data is indexed: poetry run index-mbox data/dev/*.mbox", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Query Maven mailing list archives via MCP server"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search command
    search_parser = subparsers.add_parser("search", help="Search emails by keyword")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--size", type=int, default=5, help="Number of results")

    # Message command
    msg_parser = subparsers.add_parser("message", help="Get a specific message")
    msg_parser.add_argument("id", help="Message-ID (with or without angle brackets)")

    # Thread command
    thread_parser = subparsers.add_parser("thread", help="Get thread containing a message")
    thread_parser.add_argument("id", help="Message-ID (with or without angle brackets)")
    thread_parser.add_argument("--max-messages", type=int, default=20, help="Max messages")

    # Contributor command
    contrib_parser = subparsers.add_parser("contributor", help="Find emails from contributor")
    contrib_parser.add_argument("name", help="Contributor name or email (partial match)")
    contrib_parser.add_argument("--size", type=int, default=10, help="Number of results")

    # JIRA command
    jira_parser = subparsers.add_parser("jira", help="Find emails mentioning JIRA issue")
    jira_parser.add_argument("issue", help="JIRA issue key (e.g., MNG-7891)")
    jira_parser.add_argument("--size", type=int, default=10, help="Number of results")

    # GitHub command
    gh_parser = subparsers.add_parser("github", help="Find emails mentioning GitHub PR")
    gh_parser.add_argument("pr", help="PR number (without #)")
    gh_parser.add_argument("--size", type=int, default=10, help="Number of results")

    args = parser.parse_args()
    asyncio.run(run_command(args))


if __name__ == "__main__":
    main()
