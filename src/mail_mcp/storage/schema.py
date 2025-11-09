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

"""Elasticsearch schema definitions for mail archive data."""

# Email message index settings and mappings
EMAIL_INDEX_SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0,  # Single node development
    "analysis": {
        "analyzer": {
            "email_analyzer": {
                "type": "standard",
                "stopwords": "_english_"
            }
        }
    }
}

EMAIL_INDEX_MAPPING = {
    "properties": {
        # Message identification
        "message_id": {
            "type": "keyword",
            "doc_values": True
        },

        # Threading information
        "in_reply_to": {
            "type": "keyword",
            "doc_values": True
        },
        "references": {
            "type": "keyword",
            "doc_values": True
        },

        # Sender information
        "from_address": {
            "type": "keyword",
            "fields": {
                "text": {
                    "type": "text",
                    "analyzer": "email_analyzer"
                }
            }
        },
        "from_name": {
            "type": "text",
            "analyzer": "email_analyzer",
            "fields": {
                "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                }
            }
        },

        # Recipients
        "to": {
            "type": "keyword"
        },
        "cc": {
            "type": "keyword"
        },

        # Subject and body
        "subject": {
            "type": "text",
            "analyzer": "email_analyzer",
            "fields": {
                "keyword": {
                    "type": "keyword",
                    "ignore_above": 512
                }
            }
        },
        "body_full": {
            "type": "text",
            "analyzer": "email_analyzer"
        },
        "body_effective": {
            "type": "text",
            "analyzer": "email_analyzer"
        },

        # Temporal information
        "date": {
            "type": "date"
        },
        "indexed_at": {
            "type": "date"
        },

        # List information
        "list_address": {
            "type": "keyword"
        },
        "list_name": {
            "type": "keyword"
        },

        # Metadata extraction results
        "jira_references": {
            "type": "keyword"
        },
        "github_pr_references": {
            "type": "keyword"
        },
        "github_commit_references": {
            "type": "keyword"
        },
        "version_numbers": {
            "type": "keyword"
        },
        "decision_keywords": {
            "type": "keyword"
        },
        "has_vote": {
            "type": "boolean"
        },
        "vote_value": {
            "type": "keyword"  # "+1", "-1", "+0", etc.
        },

        # Content analysis
        "quote_percentage": {
            "type": "float"
        },
        "is_mostly_quoted": {
            "type": "boolean"
        },
        "has_attachment": {
            "type": "boolean"
        },

        # Source information
        "mbox_file": {
            "type": "keyword"
        },
        "mbox_offset": {
            "type": "long"
        }
    }
}


def get_index_name(prefix: str, list_name: str) -> str:
    """
    Generate index name for a mailing list.

    Args:
        prefix: Index prefix (e.g., "maven")
        list_name: Mailing list name (e.g., "dev@maven.apache.org")

    Returns:
        Index name (e.g., "maven-dev")
    """
    # Extract list name part before @ and sanitize
    list_part = list_name.split("@")[0].lower()
    # Replace any non-alphanumeric characters with hyphen
    list_part = "".join(c if c.isalnum() else "-" for c in list_part)
    return f"{prefix}-{list_part}"


def get_index_config(prefix: str, list_name: str) -> dict:
    """
    Get complete index configuration for a mailing list.

    Args:
        prefix: Index prefix
        list_name: Mailing list name

    Returns:
        Dictionary with index name, settings, and mappings
    """
    return {
        "index": get_index_name(prefix, list_name),
        "settings": EMAIL_INDEX_SETTINGS,
        "mappings": EMAIL_INDEX_MAPPING
    }
