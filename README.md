# 🔌 Thordata MCP Server

[![Docker](https://img.shields.io/badge/docker-ready-blue?logo=docker)](Dockerfile)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An official Model Context Protocol (MCP) server that connects AI assistants (Cursor, Claude Desktop) to the real-world web using **Thordata's Residential Proxy Network**.

## ✨ Features
- **Web Search**: Real-time Google/Bing search results.
- **Universal Scraper**: Fetch and clean content from any URL (bypass Cloudflare/Akamai).
- **Anti-Bot Bypass**: Automatic IP rotation and TLS fingerprinting.

## 🚀 Quick Start (Docker)

### Prerequisites
1. Get your **Scraper Token** from [Thordata Dashboard](https://dashboard.thordata.com/).
2. Install [Docker](https://www.docker.com/).

### Run
```bash
docker run -e THORDATA_SCRAPER_TOKEN=your_token_here \
           -e THORDATA_PUBLIC_TOKEN=your_public_token \
           -e THORDATA_PUBLIC_KEY=your_public_key \
           thordata/mcp-server
```

## 💻 Cursor Configuration
Add this to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "thordata": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "THORDATA_SCRAPER_TOKEN=...", "thordata/mcp-server"]
    }
  }
}
```