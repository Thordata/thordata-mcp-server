# Thordata MCP Server (v0.3.0)

Official MCP Server for Thordata.

This repository exposes Thordata capabilities as MCP tools with:
- Clean tool naming
- Structured JSON outputs
- A simple, **non-MCP debug HTTP API** for fast, deterministic verification

Baseline: **thordata-python-sdk v1.6.0**

## Tool groups

- **SERP API**
  - `serp.search`

- **Web Unlocker (Universal API)**
  - `universal.fetch`
  - `universal.fetch_markdown`

- **Browser API**
  - `browser.get_connection_url`
  - `browser.screenshot`

- **Proxy Network**
  - `proxy.request.get`
  - `proxy.request.post`

- **Web Scraper Tasks API (120+ tools)**
  - `tasks.list`
  - `tasks.run`
  - `tasks.status`
  - `tasks.wait`
  - `tasks.result`

- **Control plane**
  - `account.get_usage_statistics`
  - `account.traffic_balance`
  - `account.wallet_balance`
  - `whitelist.list_ips` / `whitelist.add_ip` / `whitelist.delete_ip`
  - `proxy_users.list` / `proxy_users.create` / `proxy_users.update` / `proxy_users.delete`
  - `locations.countries` / `locations.states` / `locations.cities` / `locations.asn`
  - `unlimited.list_servers` / `unlimited.get_server_monitor` / `unlimited.bind_user` / `unlimited.unbind_user`

## Environment

Create a `.env` file (do not commit):

```env
THORDATA_SCRAPER_TOKEN=...
THORDATA_PUBLIC_TOKEN=...
THORDATA_PUBLIC_KEY=...

THORDATA_BROWSER_USERNAME=...
THORDATA_BROWSER_PASSWORD=...

THORDATA_RESIDENTIAL_USERNAME=...
THORDATA_RESIDENTIAL_PASSWORD=...
```

## Quick start (local, debug API)

### 1) Start server

```bash
cd /d/thordata_work/thordata-mcp-server
python -m thordata_mcp.main --transport streamable-http
```

### 2) List tools

```bash
curl -s -X POST http://127.0.0.1:8000/debug/tools/list -d '{}' | head
```

### 3) Call a tool

```bash
curl -s -X POST http://127.0.0.1:8000/debug/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"serp.search","input":{"query":"thordata proxy"}}' \
  | python -m json.tool | head
```

## Docker

### Build

```bash
docker build -t thordata-mcp:0.3.0 .
```

### Run

```bash
docker run --rm -p 8000:8000 --env-file .env thordata-mcp:0.3.0 \
  python -m thordata_mcp.main --transport streamable-http --host 0.0.0.0 --port 8000
```

### Smoke test

```bash
curl -s -X POST http://127.0.0.1:8000/debug/tools/list -d '{}' | head
```

## Notes

- The debug API is for local verification only. It bypasses MCP protocol handshake and session handling.
- For MCP hosts (Cursor / Claude Desktop), use `stdio` transport.
