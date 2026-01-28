# Thordata MCP Server

**Give your AI Agents real-time web superpowers.**

The official Thordata Model Context Protocol (MCP) server enables LLMs (Claude, Gemini, etc.) to access, discover, and extract web data in real-time. Seamlessly connect to the Thordata Proxy Network, SERP API, Universal Scraper, Scraping Browser, and Web Scraper API.

## 🚀 Features

-   **Web Search:** Real-time Google/Bing/Yandex search results via `serp.*` tools.
-   **Universal Scraping:** Convert any webpage to Markdown or HTML, handling JS rendering and CAPTCHAs via `universal.*` tools.
-   **Browser Automation:** Full control over a headless browser (Navigate, Click, Type, Snapshot) via `browser.*` tools.
-   **Structured Data:** 100+ pre-built Web Scraper Tasks (currently **111** discoverable via `tasks.list`) for Amazon, Google Maps, LinkedIn, Instagram, TikTok, YouTube, and more via `tasks.*` tools.
-   **Proxy Network:** Access web resources through Thordata's residential proxy network via `proxy.*` tools.
-   **Account Management:** Monitor usage, manage whitelists, and configure proxy users via `account.*`, `whitelist.*`, `proxy_users.*` tools.
-   **Enterprise Grade:** Built on top of the robust `thordata-python-sdk`.

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

By default, the server exposes a small **core toolset (6 tools)** optimized for MCP clients:
- `search`, `scrape`, `task_run`, `browser.navigate`, `browser.snapshot`, `tasks.list`

If you need the full structured namespaces (`serp.*`, `universal.*`, `tasks.*`, `proxy.*`, `account.*`, ...), start with:

```bash
thordata-mcp --transport stdio --expose-all-tools
```

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

### High-Level Entrypoints (Recommended for LLMs)

These tools provide a simplified API for common use cases:

-   **`search(query, num=10)`** - Single SERP search, returns structured results
-   **`search(requests=[...], concurrency=5)`** - Batch SERP searches
-   **`scrape(url, js_render=False)`** - Single URL scraping, returns HTML
-   **`scrape(requests=[...], concurrency=5)`** - Batch URL scraping
-   **`task_run(tool, param_json="{}", wait=True)`** - Run any Web Scraper Task by tool key

### Data-Plane Tools (Structured Namespace)

#### SERP Tools (`serp.*`)

-   **`serp.search(query, num=10, output_format="json")`** - Single SERP search
-   **`serp.batch_search(requests, concurrency=5)`** - Batch SERP searches

#### Universal Scraper Tools (`universal.*`)

-   **`universal.fetch(url, output_format="html", js_render=False)`** - Fetch URL as HTML
-   **`universal.fetch_markdown(url, js_render=True, wait_ms=2000)`** - Fetch URL as cleaned Markdown
-   **`universal.batch_fetch(requests, concurrency=5)`** - Batch URL fetching

#### Browser Automation Tools (`browser.*`)

-   **`browser.get_connection_url()`** - Get WebSocket URL for Scraping Browser
-   **`browser.screenshot(url, js_render=True)`** - Screenshot via Universal API
-   **`browser.navigate(url)`** - Navigate browser to URL (Playwright)
-   **`browser.snapshot(filtered=True)`** - Capture ARIA snapshot with refs
-   **`browser.click_ref(ref)`** - Click element by ref ID
-   **`browser.type_ref(ref, text, submit=False)`** - Type into element by ref ID
-   **`browser.screenshot_page(full_page=False)`** - Screenshot current page (Playwright)
-   **`browser.get_html(full_page=False)`** - Get HTML of current page
-   **`browser.scroll()`** - Scroll to bottom
-   **`browser.go_back()`** - Navigate back

#### Web Scraper Tasks (`tasks.*`)

-   **`tasks.list()`** - List all available Web Scraper Tasks (currently 111 via SDK discovery)
-   **`tasks.run(tool, params, wait=True)`** - Run a task by tool key with params dict
-   **`tasks.run_simple(tool, param_json="{}", wait=True)`** - Run a task with JSON string params
-   **`tasks.status(task_id)`** - Get task status
-   **`tasks.wait(task_id, max_wait_seconds=600)`** - Wait for task completion
-   **`tasks.result(task_id, file_type="json")`** - Get task result download URL

#### Proxy Network Tools (`proxy.*`)

-   **`proxy.request.get(url)`** - GET request through proxy network
-   **`proxy.request.post(url, data, json_data)`** - POST request through proxy network

### Control-Plane Tools (Account Management)

#### Account Tools (`account.*`)

-   **`account.get_usage_statistics(from_date, to_date)`** - Get usage stats
-   **`account.traffic_balance()`** - Get remaining traffic balance
-   **`account.wallet_balance()`** - Get wallet balance

#### Whitelist Tools (`whitelist.*`)

-   **`whitelist.list_ips()`** - List whitelisted IPs
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
    ├── entrypoints.py   # High-level entrypoints (search, scrape, task_run)
    ├── data/           # Data-plane tools (structured namespace)
    │   ├── serp.py     # serp.*
    │   ├── universal.py # universal.*
    │   ├── browser.py  # browser.*
    │   ├── tasks.py    # tasks.*
    │   └── proxy.py    # proxy.*
    └── control/         # Control-plane tools
        ├── account.py   # account.*
        ├── whitelist.py # whitelist.*
        ├── proxy_users.py # proxy_users.*
        ├── unlimited.py # unlimited.*
        └── locations.py # locations.*
```

## 🎯 Design Principles

1. **Structured Namespace**: All tools follow a `category.action` naming pattern (e.g., `serp.search`, `browser.navigate`)
2. **High-Level + Low-Level**: Provide both simplified entrypoints (`search`, `scrape`) and detailed tools (`serp.*`, `universal.*`)
3. **Unified Error Handling**: All tools return structured `{"ok": true/false, ...}` responses
4. **SDK Coverage**: Web Scraper Tasks are discoverable via `tasks.list` (core mode) and runnable via `tasks.*` (full mode)
5. **Competitive Benchmarking**: Designed to match or exceed BrightData/Oxylabs MCP capabilities

## 🛡️ License

MIT License. Copyright (c) 2026 Thordata.
