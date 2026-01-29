# Thordata MCP Server

**Give your AI Agents real-time web superpowers.**

The official Thordata Model Context Protocol (MCP) server enables LLMs (Claude, Gemini, etc.) to access, discover, and extract web data in real-time. Seamlessly connect to the Thordata Proxy Network, SERP API, Universal Scraper, Scraping Browser, and Web Scraper API.

## 🚀 Features

-   **Competitor-style MCP UX:** Clean default tool surface (only 5 tools) optimized for Cursor/LLMs.
-   **SERP SCRAPER:** Real-time Google/Bing/Yandex results via `serp`.
-   **WEB UNLOCKER:** Convert any page to HTML/Markdown with JS rendering & anti-bot handling via `unlocker`.
-   **WEB SCRAPER:** 100+ structured tasks + task management via `web_scraper` (discoverable via `catalog/groups`).
-   **BROWSER SCRAPER:** Navigate + snapshot via `browser`.
-   **Smart scraping:** `smart_scrape` auto-selects a structured task and falls back to `unlocker`.

## 📦 Installation

This server requires **Python 3.10+**.

```bash
# Clone the repository
git clone https://github.com/thordata/thordata-mcp-server.git
cd thordata-mcp-server

# Install dependencies
pip install -e .

# Install Playwright browsers (for browser automation)
playwright install chromium
```

## 🔧 Configuration

Create a `.env` file in the root directory:

```env
# Required: Thordata Credentials
THORDATA_SCRAPER_TOKEN=your_scraper_token
THORDATA_PUBLIC_TOKEN=your_public_token
THORDATA_PUBLIC_KEY=your_public_key

# Optional: Browser Automation specific creds (if different)
THORDATA_BROWSER_USERNAME=cust-user
THORDATA_BROWSER_PASSWORD=your_password

# Optional: Residential Proxy credentials (for proxy.* tools)
THORDATA_RESIDENTIAL_USERNAME=cust-user
THORDATA_RESIDENTIAL_PASSWORD=your_password
```

## 🏃 Usage

### Tool Exposure Modes (Recommended)

By default, the server exposes a **compact, competitor-style tool surface** (clean + practical):

- **SERP SCRAPER**: `serp` (actions: `search`, `batch_search`)
- **WEB UNLOCKER**: `unlocker` (actions: `fetch`, `batch_fetch`)
- **WEB SCRAPER (100+ structured tasks + task management)**: `web_scraper` (actions: `catalog`, `groups`, `run`, `batch_run`, `status`, `status_batch`, `wait`, `result`, `result_batch`, `list_tasks`, `cancel`)
- **BROWSER SCRAPER**: `browser` (actions: `navigate`, `snapshot`)
- **Smart (auto tool + fallback)**: `smart_scrape`

If you need the full advanced namespaces (`universal.*`, `tasks.*`, `proxy.*`, `account.*`, ...), start with:

```bash
thordata-mcp --transport stdio --expose-all-tools
```

### Web Scraper discovery (100+ tools, no extra env required)

Use `web_scraper` with `action="catalog"` / `action="groups"` to discover tools.
This keeps Cursor/LLMs usable while still supporting **100+ tools** under a single entrypoint.

```env
# Default: curated + limit 60
THORDATA_TASKS_LIST_MODE=curated
THORDATA_TASKS_LIST_DEFAULT_LIMIT=60

# Which groups are included when mode=curated
THORDATA_TASKS_GROUPS=ecommerce,social,video,search,travel,code,professional

# Optional safety/UX: restrict which tools can actually run
# (comma-separated prefixes or exact tool keys)
# Example:
# THORDATA_TASKS_ALLOWLIST=thordata.tools.video.,thordata.tools.ecommerce.Amazon.ProductByAsin
THORDATA_TASKS_ALLOWLIST=
```

If you want Cursor to **never** see the full 300+ tool list, keep `THORDATA_TASKS_LIST_MODE=curated`
and optionally set `THORDATA_TASKS_ALLOWLIST` to the small subset you actually want to support.

### Deployment (Optional)

- **Docker**: See `DOCKER_TEST.md` and `Dockerfile`
- **Gateway (Caddy)**: See `Caddyfile` + `docker-compose.yml` for a simple reverse-proxy with header auth

### Running Locally (Stdio)

This is the standard mode for connecting to an MCP client (like Claude Desktop or Gemini).

```bash
python -m thordata_mcp.main --transport stdio
```

Or use the CLI entry point:

```bash
thordata-mcp
```

### Running with HTTP (SSE)

For remote debugging or specific client configurations:

```bash
thordata-mcp --transport streamable-http --port 8000
```

### Claude Desktop Configuration

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "thordata": {
      "command": "python",
      "args": ["-m", "thordata_mcp.main"],
      "env": {
        "THORDATA_SCRAPER_TOKEN": "...",
        "THORDATA_PUBLIC_TOKEN": "...",
        "THORDATA_PUBLIC_KEY": "...",

        "THORDATA_BROWSER_USERNAME": "...",
        "THORDATA_BROWSER_PASSWORD": "..."
      }
    }
  }
}
```

Notes:
- `THORDATA_BROWSER_USERNAME` / `THORDATA_BROWSER_PASSWORD` are required for `browser.*` tools (Scraping Browser).
- If you use residential proxy tools (`proxy.*`), those credentials are separate (`THORDATA_RESIDENTIAL_USERNAME` / `THORDATA_RESIDENTIAL_PASSWORD`).

## 🛠️ Available Tools

### Core Mode (Default, Recommended for Cursor/LLMs)

Only **5 tools** are exposed by default:

- **`serp`**: action `search`, `batch_search`
- **`unlocker`**: action `fetch`, `batch_fetch`
- **`web_scraper`**: action `catalog`, `groups`, `run`, `batch_run`, `status`, `status_batch`, `wait`, `result`, `result_batch`, `list_tasks`, `cancel`
- **`browser`**: action `navigate`, `snapshot`
- **`smart_scrape`**: auto-pick structured tool; fallback to unlocker

### Advanced Mode (`--expose-all-tools`)

Expose the full namespaces for debugging/admin:
- Data-plane: `serp.*`, `universal.*`, `browser.*`, `tasks.*`, `proxy.*`
- Control-plane: `account.*`, `whitelist.*`, `proxy_users.*`, `unlimited.*`, `locations.*`
-   **`whitelist.add_ip(ip)`** - Add IP to whitelist
-   **`whitelist.delete_ip(ip)`** - Delete IP from whitelist

#### Proxy Users Tools (`proxy_users.*`)

-   **`proxy_users.list()`** - List proxy sub-users
-   **`proxy_users.create(username, password, proxy_type=2)`** - Create proxy user
-   **`proxy_users.update(username, password, ...)`** - Update proxy user
-   **`proxy_users.delete(username)`** - Delete proxy user

#### Unlimited Tools (`unlimited.*`)

-   **`unlimited.list_servers()`** - List unlimited proxy servers
-   **`unlimited.get_server_monitor(ins_id, region, start_time, end_time)`** - Get server metrics
-   **`unlimited.bind_user(ip, username)`** - Bind user to server
-   **`unlimited.unbind_user(ip, username)`** - Unbind user from server

#### Locations Tools (`locations.*`)

-   **`locations.countries(proxy_type=2)`** - List available countries
-   **`locations.states(country_code, proxy_type=2)`** - List states for country
-   **`locations.cities(country_code, state_code=None, proxy_type=2)`** - List cities
-   **`locations.asn(country_code, proxy_type=2)`** - List ASN for country

## 🏗️ Architecture

The MCP server follows a clean, structured architecture:

```
thordata_mcp/
├── main.py              # Entry point
├── registry.py          # Tool registration orchestrator
├── config.py            # Configuration management
├── context.py           # Server context (client, browser session)
├── utils.py             # Common utilities (error handling, responses)
├── browser_session.py   # Browser session management (Playwright)
├── aria_snapshot.py     # ARIA snapshot filtering
└── tools/
    ├── product_compact.py  # Compact 5-tool surface for MCP (serp/unlocker/web_scraper/browser/smart_scrape)
    ├── product.py          # Full product-line tools (used in --expose-all-tools)
    ├── data/               # Data-plane tools (structured namespace)
    │   ├── serp.py         # serp.*
    │   ├── universal.py    # universal.*
    │   ├── browser.py      # browser.*
    │   ├── tasks.py        # tasks.*
    │   └── proxy.py        # proxy.*
    └── control/            # Control-plane tools
        ├── account.py      # account.*
        ├── whitelist.py    # whitelist.*
        ├── proxy_users.py  # proxy_users.*
        ├── unlimited.py    # unlimited.*
        └── locations.py    # locations.*
```

## 🎯 Design Principles

1. **Structured Namespace**: All tools follow a `category.action` naming pattern (e.g., `serp.search`, `browser.navigate`)
2. **Compact + Advanced**: Default compact surface (5 tools) with optional advanced namespaces via `--expose-all-tools`
3. **Unified Error Handling**: All tools return structured `{"ok": true/false, ...}` responses
4. **SDK Coverage**: All Web Scraper Tasks are discoverable via `web_scraper` (`catalog/groups`) and runnable via `web_scraper.run`
5. **Competitive Benchmarking**: Designed to match or exceed BrightData/Oxylabs MCP capabilities

## 🛡️ License

MIT License. Copyright (c) 2026 Thordata.
