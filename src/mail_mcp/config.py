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

"""Configuration management for mail-mcp."""

import re
import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Elasticsearch configuration
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_prefix: str = "maven"
    elasticsearch_timeout: int = 30
    elasticsearch_max_retries: int = 3

    # Data paths
    data_path: Path = Path("./data")
    mbox_cache_enabled: bool = True

    # Maven JIRA projects configuration
    maven_jira_projects_config: Path = Path("maven-jira-projects.toml")

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    # MCP server (future)
    server_host: str = "0.0.0.0"
    server_port: int = 8080

    model_config = SettingsConfigDict(
        env_prefix="MAIL_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


class MavenProjects:
    """Maven JIRA project configuration loader."""

    def __init__(self, config_path: Path):
        """
        Load Maven project configuration from TOML file.

        Args:
            config_path: Path to maven-projects.toml
        """
        self.config_path = config_path
        self._config = None
        self._jira_pattern = None

    def load(self) -> dict:
        """
        Load configuration from TOML file.

        Returns:
            Configuration dictionary
        """
        if self._config is None:
            if not self.config_path.exists():
                raise FileNotFoundError(f"Maven projects config not found: {self.config_path}")

            with open(self.config_path, "rb") as f:
                self._config = tomllib.load(f)

        return self._config

    def get_all_project_keys(self) -> list[str]:
        """
        Get all Maven JIRA project keys by flattening all categories.

        Returns:
            List of project keys (e.g., ["MNG", "MRESOLVER", ...])
        """
        config = self.load()
        projects = config.get("projects", {})

        # Flatten all keys from all categories
        all_keys = []
        for category_data in projects.values():
            keys = category_data.get("keys", [])
            all_keys.extend(keys)

        return all_keys

    def get_jira_pattern(self) -> re.Pattern:
        """
        Get compiled regex pattern for matching JIRA references.

        Returns:
            Compiled regex pattern that matches any Maven JIRA reference
        """
        if self._jira_pattern is None:
            keys = self.get_all_project_keys()
            # Create pattern like (?:MNG|MRESOLVER|...)-\d+
            # Use non-capturing group (?:...) to match full reference
            keys_pattern = "|".join(re.escape(key) for key in keys)
            self._jira_pattern = re.compile(rf"\b(?:{keys_pattern})-\d+\b")

        return self._jira_pattern

    def get_projects_by_category(self, category: str) -> list[str]:
        """
        Get project keys for a specific category.

        Args:
            category: Category name (e.g., "core", "core_plugins")

        Returns:
            List of project keys in that category
        """
        config = self.load()
        projects = config.get("projects", {})
        if category in projects:
            return projects[category].get("keys", [])
        return []


# Global settings instance
settings = Settings()

# Global Maven JIRA projects configuration
maven_projects = MavenProjects(settings.maven_jira_projects_config)
