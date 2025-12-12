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

"""Custom middleware for Maven Mail MCP server."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


class StaleSessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to return 404 for stale/invalid session IDs.

    The MCP SDK returns 400 "Bad Request: No valid session ID provided" when
    a client sends a session ID that is not found in the server's registry
    (e.g., after server restart). This middleware transforms that response
    to 404 "Not Found: Invalid or expired session ID" which better signals
    to clients that they should re-initialize their session.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Check if this is a 400 response for invalid session
        if response.status_code == 400:
            # Read the response body to check the message
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            body_text = body.decode("utf-8", errors="replace")

            # Transform "No valid session ID" errors to 404
            if "No valid session ID" in body_text:
                return PlainTextResponse(
                    "Not Found: Invalid or expired session ID",
                    status_code=404,
                )

            # For other 400 errors, we need to recreate the response
            # since we consumed the body iterator
            return PlainTextResponse(
                body_text,
                status_code=400,
                headers=dict(response.headers),
            )

        return response
