---
name: Python service isolation
description: Python dependency setup can create workspace-level uv scaffolding even when the intended service is a subdirectory.
---

Keep Python service dependencies and run instructions inside the service directory when the service must remain independent of the pnpm workspace.

**Why:** The workspace package installer initializes root-level uv metadata as a side effect, which can add unrelated files to a TypeScript monorepo.

**How to apply:** Prefer a service-local requirements file and run command; remove unrelated generated root scaffolding after installing the Python runtime.