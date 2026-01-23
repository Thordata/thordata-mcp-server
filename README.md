# ⚡ ThorData MCP Server (v0.2.0)

**The most powerful bridge between AI Agents and real-time structured web data.**

Built with the latest **ThorData Python SDK v1.5.0**, this server allows LLMs (Claude, Cursor, GPT-4) to perform high-fidelity scraping, video data extraction, and real-time search without being blocked.

## ✨ Why this server is different?

- **Smart Routing Engine**: Automatically detects URL types (Amazon, YouTube, etc.) and routes them to 34+ specialized high-speed scrapers.
- **Deep JSON Extraction**: Returns raw, structured data for products, social media posts, and videos instead of generic web snapshots.
- **Industrial Stability**: Built-in polling, retry logic, and fallback mechanisms.
- **Protocol Verified**: 100% success rate in industrial-grade acceptance testing across all categories.

## 🧰 Specialized Tools (34+ Built-in)

The `smart_scrape` tool automatically utilizes ThorData specialized engines for:

| Platform | Capabilities |
| :--- | :--- |
| **Amazon** | Product Details (ASIN), Reviews, Seller Info, Search Results |
| **YouTube** | Video Metadata (JSON), Subtitles/Transcripts, Comments, Profiles |
| **Social** | TikTok Video/Profile, Instagram Reels/Profiles, X/Twitter Posts, Reddit |
| **Professional** | LinkedIn Job Listings & Company Information |
| **Maps** | Google Maps Place Details & Customer Reviews |
| **General** | Clean Markdown fallback for any other website |

## 🚀 Quick Start

### 1. Build and Run (Docker)
```bash
docker build -t thordata-mcp:0.2.0 .
winpty docker run -i --rm --env-file .env thordata-mcp:0.2.0
```

### 2. Connect to Cursor
- **Type**: `Command`
- **Command**: `docker`
- **Args**: `run -i --rm --env-file D:/your/path/.env thordata-mcp:0.2.0`

## 📄 License
MIT.