---
name: WebSocket artifact routing
description: Preview WebSocket connections need explicit path forwarding in the API artifact metadata.
---

The shared preview proxy only forwards WebSocket upgrades for paths explicitly listed in the API service artifact routing configuration.

**Why:** A normal HTTP API can appear healthy while an unlisted WebSocket silently fails because the upgrade never reaches the server.

**How to apply:** When adding a live WebSocket endpoint, register its path alongside the REST API path before verifying the client connection.