#!/usr/bin/env python
"""
Interactive test script for MCP tools.

This script tests the MCP tools directly without the MCP protocol layer.
It requires Elasticsearch to be running with indexed data.
"""

import asyncio
import sys

from mail_mcp.server.tools import (
    find_references,
    get_message,
    get_thread,
    search_emails,
)


async def test_search():
    """Test the search_emails tool."""
    print("=" * 80)
    print("TEST 1: Search for emails about 'release'")
    print("=" * 80)

    result = await search_emails(query="release", size=5)
    print(result)
    print("\n")


async def test_search_with_filters():
    """Test search with filters."""
    print("=" * 80)
    print("TEST 2: Search for emails with JIRA references")
    print("=" * 80)

    result = await search_emails(query="fix", has_jira=True, size=3)
    print(result)
    print("\n")


async def test_search_with_votes():
    """Test search for votes."""
    print("=" * 80)
    print("TEST 3: Search for emails with votes")
    print("=" * 80)

    result = await search_emails(query="vote", has_vote=True, size=3)
    print(result)
    print("\n")


async def test_find_references():
    """Test finding JIRA references."""
    print("=" * 80)
    print("TEST 4: Find emails mentioning MNG-7891")
    print("=" * 80)

    result = await find_references(
        reference="MNG-7891", reference_type="jira", size=3
    )
    print(result)
    print("\n")


async def test_date_range():
    """Test date range search."""
    print("=" * 80)
    print("TEST 5: Search emails from 2024")
    print("=" * 80)

    result = await search_emails(
        query="dependency",
        from_date="2024-01-01",
        to_date="2024-12-31",
        size=3,
    )
    print(result)
    print("\n")


async def interactive_test():
    """Run interactive test allowing user to input queries."""
    print("\n" + "=" * 80)
    print("INTERACTIVE MODE")
    print("=" * 80)
    print("Enter a search query (or 'quit' to exit):")

    while True:
        try:
            query = input("\nQuery> ").strip()
            if query.lower() in ("quit", "exit", "q"):
                break

            if not query:
                continue

            print("\nSearching...")
            result = await search_emails(query=query, size=5)
            print(result)

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("MCP TOOLS TEST SUITE")
    print("=" * 80)
    print("\nThis will test the MCP tools against your Elasticsearch instance.")
    print("Make sure:")
    print("  1. Elasticsearch is running (docker compose up -d elasticsearch)")
    print("  2. Data is indexed (poetry run index-mbox data/dev/YYYY-MM.mbox)")
    print("\n")

    try:
        # Run all tests
        await test_search()
        await test_search_with_filters()
        await test_search_with_votes()
        await test_find_references()
        await test_date_range()

        # Ask if user wants interactive mode
        print("=" * 80)
        response = input("Run interactive mode? (y/n): ").strip().lower()
        if response in ("y", "yes"):
            await interactive_test()

        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"\nError running tests: {e}", file=sys.stderr)
        print("\nMake sure Elasticsearch is running and data is indexed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
