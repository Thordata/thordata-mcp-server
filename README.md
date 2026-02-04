# Thordata MCP Server

**Give your AI Agents real-time web scraping superpowers.**

This MCP Server version has been **streamlined to focus on scraping**, concentrating on a compact, LLM‑friendly tool surface:

- **Search Engine** (LLM-friendly web search wrapper)
- **SERP API** (Search result scraping, internal plumbing)
- **Web Unlocker / Universal Scraper** (Universal page unlocking & scraping)
- **Scraping Browser** (Browser-level scraping)

Earlier versions exposed `proxy.*` / `account.*` / `proxy_users.*` proxy and account management tools, and a large `web_scraper` task surface. This version removes those control plane interfaces from MCP, keeping only scraping-related capabilities that are easy for LLMs to use.

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
# Required: Thordata Credentials (scraping only)
THORDATA_SCRAPER_TOKEN=your_scraper_token
THORDATA_PUBLIC_TOKEN=your_public_token
THORDATA_PUBLIC_KEY=your_public_key

# Optional: Browser Automation creds (Scraping Browser)
THORDATA_BROWSER_USERNAME=cust-user
THORDATA_BROWSER_PASSWORD=your_password
```

## 🏃 Usage

### Tool Exposure Modes

Current implementation provides a **compact scraping tool surface**, optimized for Cursor / LLM tool callers:

- **`search_engine`** (recommended for LLMs): high-level web search wrapper, returns a light `results[]` array with `title/link/description`. Internally delegates to the SERP backend.
- **`search_engine_batch`**: batch variant of `search_engine` with per-item `ok/error` results.
- **`unlocker`**: actions `fetch`, `batch_fetch` – universal page unlock & content extraction (HTML/Markdown), with per-item error reporting for batch.
- **`browser`**: action `snapshot` – navigate (optional `url`) and capture an ARIA-focused snapshot for interactive elements.
- **`smart_scrape`**: auto-picks the best scraper (SERP, Web Scraper, Unlocker) for a given URL and returns a unified, LLM-friendly response.

Internally, the server still uses structured SERP and Web Scraper capabilities, but they are not exposed as large tool surfaces by default to avoid overwhelming LLMs.

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

## 🛠️ Available Tools (Compact Surface)

By default, the MCP server exposes a **small, LLM-friendly tool set**:

- **`search_engine`**: single-query web search (`params.q`, optional `params.num`, `params.engine`).
- **`search_engine_batch`**: batch web search with per-item `ok/error` in `results[]`.
- **`unlocker`**: universal scraping via `fetch` / `batch_fetch`.
- **`browser`**: `snapshot` with optional `url`, `max_items`, and `max_chars`.
- **`smart_scrape`**: smart router for `url` with optional preview limit parameters.

Advanced / internal tools (e.g. low-level `serp.*`, full `web_scraper.*` surfaces, proxy/account control plane) remain available via HTTP APIs and SDKs, but are not exposed directly as MCP tools to keep the surface manageable for agents and LLMs.

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
        ├── product_compact.py  # Streamlined MCP entrypoint (search_engine / unlocker / browser / smart_scrape, plus batch variants)
        ├── product.py          # Full product implementation for internal use (reused by compact version)
        ├── data/               # Data plane tools (only scraping-related namespaces retained)
        │   ├── serp.py         # SERP backend integration
        │   ├── universal.py    # Universal / Unlocker backend integration
        │   ├── browser.py      # Browser / Playwright helpers
        │   └── tasks.py        # Structured scraping tasks (used by smart_scrape and internal flows)
```

## 🎯 Design Principles

1. **Structured Namespace**: All tools follow a `category.action` naming pattern (e.g., `serp.search`, `browser.navigate`)
2. **Compact + Advanced**: Default compact surface (5 tools) with optional advanced namespaces via `--expose-all-tools`
3. **Unified Error Handling**: All tools return structured `{"ok": true/false, ...}` responses
4. **SDK Coverage**: All Web Scraper Tasks are discoverable via `web_scraper` (`catalog/groups`) and runnable via `web_scraper.run`
5. **Competitive Benchmarking**: Designed to match or exceed BrightData/Oxylabs MCP capabilities

## 🛡️ License

MIT License. Copyright (c) 2026 Thordata.
