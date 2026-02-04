# Cursor Configuration (MCP)

This folder contains a minimal, **direct-value** Cursor MCP configuration for the Thordata MCP Server.

## Recommended setup (direct values, no system env vars)

1. Open **Cursor**.
2. Go to **Settings** -> search for **MCP** -> open **MCP Servers**.
3. Add a new server (or edit your existing one) and paste the config from `cursor-config/mcp.json`.
4. Replace all `YOUR_*` placeholders with your real credentials.
5. Restart the MCP server from Cursor (or restart Cursor).

## Verify

In Cursor, run a simple test call:

- `serp` with `action="search"`

If the server is connected but tool calls fail, check Cursor's MCP output log.

## Notes

- This repository intentionally keeps the Cursor config **small**:
  - One `mcp.json` template
  - One short README
- Avoid using `${VAR}` placeholders unless you explicitly want to depend on system environment variables.
