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

"""Metadata extractors for email content analysis."""

from mail_mcp.extractors.metadata import ExtractedMetadata, MetadataExtractor
from mail_mcp.extractors.quotes import QuoteAnalysis, QuoteDetector

__all__ = [
    "MetadataExtractor",
    "ExtractedMetadata",
    "QuoteDetector",
    "QuoteAnalysis",
]
