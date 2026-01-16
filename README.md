# Thordata MCP Server

<div align="center">

<img src="https://img.shields.io/badge/Thordata-Official-blue?style=for-the-badge" alt="Thordata Logo">

**Official Model Context Protocol (MCP) Server for Thordata.**  
*Give LLMs (Claude, Cursor) the ability to search the web, scrape data, and perform complex tasks.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## ⚡ Capabilities

This server exposes Thordata's AI infrastructure as callable tools for AI models:

*   **🔍 Search**: Real-time Google search (`google_search`).
*   **📖 Read**: Turn any webpage (including JS-heavy SPAs) into clean Markdown (`read_url`).
*   **🗺️ Maps**: Extract business details from Google Maps links (`get_google_maps_details`).
*   **🎥 Media**: Retrieve YouTube/Instagram metadata (`get_youtube_video_info`).

## 🛠️ Installation

### Option 1: For Claude Desktop (Recommended)

1.  Clone this repository:
    ```bash
    git clone https://github.com/Thordata/thordata-mcp-server.git
    cd thordata-mcp-server
    ```

2.  Install dependencies:
    ```bash
    # Recommend using uv for speed, or pip
    pip install .
    ```

3.  Add to your `claude_desktop_config.json`:
    *   **MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
    *   **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

    ```json
    {
      "mcpServers": {
        "thordata": {
          "command": "python", 
          "args": ["-m", "thordata_mcp.main"],
          "cwd": "/absolute/path/to/thordata-mcp-server",
          "env": {
            "THORDATA_SCRAPER_TOKEN": "your_token",
            "THORDATA_PUBLIC_TOKEN": "your_public_token",
            "THORDATA_PUBLIC_KEY": "your_public_key"
          }
        }
      }
    }
    ```

### Option 2: Local Development

1.  Set up environment:
    ```bash
    cp .env.example .env
    # Edit .env with your tokens
    ```

2.  Run the MCP Inspector:
    ```bash
    mcp dev src/thordata_mcp/main.py
    ```

### Option 3: Docker

```bash
docker build -t thordata-mcp .
docker run -i --env-file .env thordata-mcp
```

### Option 4: Smithery (One-click Install)

If you use [Smithery](https://smithery.ai/), you can install this server directly:

```bash
npx -y @smithery/cli install @thordata/thordata-mcp-server --client claude
```
---

## 📄 License

MIT License.