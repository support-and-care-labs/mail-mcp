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
Pony Mail API client for resolving archive URLs.

This module provides on-demand lookup of Pony Mail permalink IDs (mid) from
Message-IDs. The mid values are cached in Elasticsearch once retrieved.

NOTE: This is a workaround approach (Option D). A preferred future approach
(Option C) would be to resolve and store mid values during initial indexing,
which would eliminate runtime API calls but requires handling rate limiting
for large archive imports.

See: docs/adr/ for architecture decision on URL resolution strategy.
"""

from datetime import datetime

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Pony Mail API base URL for Apache
PONYMAIL_API_BASE = "https://lists.apache.org/api"

# Archive web UI base URL
PONYMAIL_THREAD_BASE = "https://lists.apache.org/thread"


def get_archive_url(mid: str) -> str:
    """
    Generate the archive URL for a given Pony Mail mid.

    Args:
        mid: The Pony Mail permalink ID (e.g., "241rf6j48ogn4ynmzszyo5535mq3v5v5")

    Returns:
        Full URL to the archived message/thread
    """
    return f"{PONYMAIL_THREAD_BASE}/{mid}"


async def lookup_mid_by_search(
    message_id: str,
    list_name: str = "dev@maven.apache.org",
    date: datetime | None = None,
    subject: str | None = None,
) -> str | None:
    """
    Look up the Pony Mail mid for a message by searching the archive.

    This uses the Pony Mail stats API to search for a message and extract
    the mid from the results. The search uses date range and subject to
    narrow down results.

    Args:
        message_id: The RFC Message-ID header value (with or without angle brackets)
        list_name: Mailing list address (e.g., "dev@maven.apache.org")
        date: Message date for narrowing search (optional)
        subject: Message subject for search query (optional)

    Returns:
        The Pony Mail mid if found, None otherwise
    """
    # Parse list name into list and domain
    if "@" in list_name:
        list_part, domain = list_name.split("@", 1)
    else:
        list_part = list_name
        domain = "maven.apache.org"

    # Normalize message_id (remove angle brackets for comparison)
    normalized_mid = message_id.strip("<>")

    # Build search parameters
    params = {
        "list": list_part,
        "domain": domain,
    }

    # Add date range if provided (search within that month)
    if date:
        # Search within the month of the message
        year_month = date.strftime("%Y-%m")
        params["d"] = year_month

    # Add subject as search query if provided
    if subject:
        # Use first few significant words from subject
        # Remove common prefixes like Re:, [VOTE], etc.
        clean_subject = subject
        for prefix in ["Re:", "RE:", "Fwd:", "FWD:", "[VOTE]", "[RESULT]", "[ANN]", "[DISCUSS]"]:
            clean_subject = clean_subject.replace(prefix, "")
        # Take first 5 words
        words = clean_subject.split()[:5]
        if words:
            params["q"] = " ".join(words)

    url = f"{PONYMAIL_API_BASE}/stats.lua"

    logger.debug(
        "ponymail_lookup_request",
        message_id=normalized_mid,
        url=url,
        params=params
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Search through results for matching message-id
            emails = data.get("emails", [])
            for email in emails:
                email_message_id = email.get("message-id", "").strip("<>")
                if email_message_id == normalized_mid:
                    mid = email.get("mid")
                    logger.info(
                        "ponymail_mid_found",
                        message_id=normalized_mid,
                        mid=mid
                    )
                    return mid

            logger.debug(
                "ponymail_mid_not_found",
                message_id=normalized_mid,
                results_count=len(emails)
            )
            return None

    except httpx.HTTPError as e:
        logger.warning(
            "ponymail_lookup_failed",
            message_id=normalized_mid,
            error=str(e)
        )
        return None
    except Exception as e:
        logger.error(
            "ponymail_lookup_error",
            message_id=normalized_mid,
            error=str(e),
            exc_info=True
        )
        return None


async def get_mid_by_api(mid: str) -> dict | None:
    """
    Fetch email details from Pony Mail API by mid.

    Args:
        mid: The Pony Mail permalink ID

    Returns:
        Email data dict if found, None otherwise
    """
    url = f"{PONYMAIL_API_BASE}/email.lua"
    params = {"id": mid}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        logger.warning("ponymail_api_failed", mid=mid, error=str(e))
        return None


class PonymailResolver:
    """
    Resolver for Pony Mail archive URLs with caching.

    This class handles looking up Pony Mail mid values and caching them
    in Elasticsearch for future use.
    """

    def __init__(self, es_client, index_prefix: str = "maven"):
        """
        Initialize the resolver.

        Args:
            es_client: Elasticsearch client instance
            index_prefix: Index prefix for email storage
        """
        self.es_client = es_client
        self.index_prefix = index_prefix

    async def resolve_url(
        self,
        message_id: str,
        list_name: str = "dev@maven.apache.org",
        date: datetime | None = None,
        subject: str | None = None,
    ) -> str | None:
        """
        Resolve the archive URL for a message, using cache if available.

        This method:
        1. Checks if we have a cached mid in Elasticsearch
        2. If not, queries the Pony Mail API
        3. Caches the result for future use
        4. Returns the full archive URL

        Args:
            message_id: The RFC Message-ID header value
            list_name: Mailing list address
            date: Message date (for search optimization)
            subject: Message subject (for search optimization)

        Returns:
            Archive URL if resolved, None otherwise
        """
        normalized_mid = message_id.strip("<>")

        # Check cache first
        cached_mid = await self._get_cached_mid(normalized_mid, list_name)
        if cached_mid:
            logger.debug("ponymail_cache_hit", message_id=normalized_mid)
            return get_archive_url(cached_mid)

        # Look up from Pony Mail API
        mid = await lookup_mid_by_search(
            message_id=message_id,
            list_name=list_name,
            date=date,
            subject=subject
        )

        if mid:
            # Cache the result
            await self._cache_mid(normalized_mid, list_name, mid)
            return get_archive_url(mid)

        return None

    async def _get_cached_mid(
        self,
        message_id: str,
        list_name: str
    ) -> str | None:
        """Get cached mid from Elasticsearch."""
        try:
            # The message_id is used as document ID in our index
            doc_id = f"<{message_id}>" if not message_id.startswith("<") else message_id
            doc = await self.es_client.get_document(list_name, doc_id)
            if doc:
                return doc.get("archive_mid")
        except Exception as e:
            logger.debug("cached_mid_lookup_failed", message_id=message_id, error=str(e))
        return None

    async def _cache_mid(
        self,
        message_id: str,
        list_name: str,
        mid: str
    ) -> None:
        """Cache mid in Elasticsearch by updating the document."""
        try:
            doc_id = f"<{message_id}>" if not message_id.startswith("<") else message_id
            await self.es_client.update_document(
                list_name,
                doc_id,
                {"archive_mid": mid}
            )
            logger.debug(
                "ponymail_mid_cached",
                message_id=message_id,
                mid=mid
            )
        except Exception as e:
            logger.warning(
                "ponymail_cache_failed",
                message_id=message_id,
                error=str(e)
            )
