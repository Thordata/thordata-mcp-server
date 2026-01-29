# Cursor IDE Configuration

This directory contains configuration files for using Thordata MCP Server with Cursor IDE.

## Setup Instructions

### 1. Copy Configuration File

**Windows:**
```powershell
Copy-Item cursor-config\mcp.json "$env:APPDATA\Cursor\User\globalStorage\mcp.json"
```

**macOS:**
```bash
cp cursor-config/mcp.json ~/Library/Application\ Support/Cursor/User/globalStorage/mcp.json
```

**Linux:**
```bash
cp cursor-config/mcp.json ~/.config/Cursor/User/globalStorage/mcp.json
```

### 2. Set Environment Variables

Set the following environment variables in your system:

**Windows (PowerShell):**
```powershell
$env:THORDATA_SCRAPER_TOKEN="your_scraper_token"
$env:THORDATA_PUBLIC_TOKEN="your_public_token"
$env:THORDATA_PUBLIC_KEY="your_public_key"
$env:THORDATA_BROWSER_USERNAME="your_browser_username"
$env:THORDATA_BROWSER_PASSWORD="your_browser_password"
```

**macOS/Linux:**
```bash
export THORDATA_SCRAPER_TOKEN="your_scraper_token"
export THORDATA_PUBLIC_TOKEN="your_public_token"
export THORDATA_PUBLIC_KEY="your_public_key"
export THORDATA_BROWSER_USERNAME="your_browser_username"
export THORDATA_BROWSER_PASSWORD="your_browser_password"
```

Or add them to your `~/.bashrc` or `~/.zshrc` file.

### 3. Restart Cursor IDE

After copying the configuration file and setting environment variables, restart Cursor IDE.

## Configuration Options

### `thordata` (Core Mode)
- **Tools**: **5 core tools** (competitor-style, clean + practical)
  - `serp` - SERP SCRAPER (actions: `search`, `batch_search`)
  - `unlocker` - WEB UNLOCKER (actions: `fetch`, `batch_fetch`)
  - `web_scraper` - WEB SCRAPER 100+ tasks + task management (actions: `catalog`, `groups`, `run`, `batch_run`, `status`, `result`, ...)
  - `browser` - BROWSER SCRAPER (actions: `navigate`, `snapshot`)
  - `smart_scrape` - Smart entry (auto pick WEB SCRAPER tool; fallback to WEB UNLOCKER)

## Verification

After setup, verify the configuration:

1. Open Cursor IDE
2. Check MCP server status (should show "Connected")
3. Try using a tool:
   ```
   Use serp tool to search for "python"
   ```

## Troubleshooting

### MCP Server Not Connecting
- Check environment variables are set correctly
- Verify Python path is correct
- Check Cursor IDE logs for errors

### Tools Not Available
- Ensure you're using the correct configuration (`thordata`)
- Restart Cursor IDE after configuration changes
- Check environment variables are accessible to Cursor

### Token Errors
- Verify all three tokens are set correctly
- Ensure `PUBLIC_TOKEN` and `PUBLIC_KEY` are paired
- Check tokens are from the same account

## Files

- `mcp.json` - Cursor IDE MCP server configuration
- `README.md` - This file
