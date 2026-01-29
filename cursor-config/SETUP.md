# Cursor IDE Setup Guide

## Quick Setup

### Step 1: Copy Configuration File

**Windows:**
```powershell
# Create directory if it doesn't exist
New-Item -ItemType Directory -Force -Path "$env:APPDATA\Cursor\User\globalStorage"

# Copy configuration file
Copy-Item cursor-config\mcp.json "$env:APPDATA\Cursor\User\globalStorage\mcp.json"
```

**macOS:**
```bash
mkdir -p ~/Library/Application\ Support/Cursor/User/globalStorage
cp cursor-config/mcp.json ~/Library/Application\ Support/Cursor/User/globalStorage/mcp.json
```

**Linux:**
```bash
mkdir -p ~/.config/Cursor/User/globalStorage
cp cursor-config/mcp.json ~/.config/Cursor/User/globalStorage/mcp.json
```

### Step 2: Set Environment Variables

Set these environment variables **before** starting Cursor IDE:

**Windows (PowerShell - Current Session):**
```powershell
$env:THORDATA_SCRAPER_TOKEN="your_scraper_token"
$env:THORDATA_PUBLIC_TOKEN="your_public_token"
$env:THORDATA_PUBLIC_KEY="your_public_key"
$env:THORDATA_BROWSER_USERNAME="your_browser_username"
$env:THORDATA_BROWSER_PASSWORD="your_browser_password"
```

**Windows (Permanent - System Environment):**
1. Press `Win + R`, type `sysdm.cpl`, press Enter
2. Go to "Advanced" tab → "Environment Variables"
3. Add all variables under "User variables" or "System variables"

**macOS/Linux:**
```bash
# Add to ~/.bashrc or ~/.zshrc
export THORDATA_SCRAPER_TOKEN="your_scraper_token"
export THORDATA_PUBLIC_TOKEN="your_public_token"
export THORDATA_PUBLIC_KEY="your_public_key"
export THORDATA_BROWSER_USERNAME="your_browser_username"
export THORDATA_BROWSER_PASSWORD="your_browser_password"
```

### Step 3: Restart Cursor IDE

Close and restart Cursor IDE to load the new configuration.

## Verify Setup

After restarting Cursor IDE:

1. Open Cursor IDE
2. Check MCP server status (should show "Connected" for `thordata`)
3. Test a tool:
   ```
   Use serp tool to search for "python"
   ```

## Configuration Options

### Core Mode (`thordata`)
- **5 tools**: `serp`, `unlocker`, `web_scraper`, `browser`, `smart_scrape`
- **Best for**: Cursor/LLMs (clean tool surface; 100+ tasks are discoverable via `web_scraper` → `catalog/groups`)

## Troubleshooting

### MCP Server Not Connecting

1. **Check environment variables:**
   ```powershell
   # Windows PowerShell
   $env:THORDATA_SCRAPER_TOKEN
   ```

2. **Verify Python is in PATH:**
   ```bash
   python --version
   ```

3. **Check Cursor logs:**
   - Open Cursor IDE
   - View → Output → Select "MCP" from dropdown
   - Look for error messages

### Tools Not Available

1. **Restart Cursor IDE** after configuration changes
2. **Check you're using the correct server** (`thordata`)
3. **Verify environment variables** are accessible to Cursor

### Token Errors

1. **Verify all three tokens** are set:
   - `THORDATA_SCRAPER_TOKEN`
   - `THORDATA_PUBLIC_TOKEN`
   - `THORDATA_PUBLIC_KEY`

2. **Ensure tokens are paired**: `PUBLIC_TOKEN` and `PUBLIC_KEY` must be from the same account

3. **Check token format**: No extra spaces or quotes

## Files

- `mcp.json` - Cursor IDE MCP server configuration
- `SETUP.md` - This setup guide
- `README.md` - Overview and quick reference
