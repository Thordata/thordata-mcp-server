# Docker Build and Test Guide

## Quick Start

### 1. Build Docker Image

```bash
docker build -t thordata-mcp:0.4.0 .
```

### 2. Run Container

```bash
docker run -d \
  --name thordata-mcp \
  -p 8000:8000 \
  --env-file .env \
  thordata-mcp:0.4.0 \
  python -m thordata_mcp.main --transport streamable-http --host 0.0.0.0 --port 8000
```

### 3. Verify Health

```bash
curl http://127.0.0.1:8000/debug/healthz
```

Expected: `{"status": "ok"}`

### 4. Test Tools

#### List Available Tools
```bash
curl -X POST http://127.0.0.1:8000/debug/tools/list \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool
```

Expected: Should show **6 tools** in core mode.

#### Test SERP Search
```bash
curl -X POST http://127.0.0.1:8000/debug/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"search","input":{"query":"python","num":3}}' | python -m json.tool
```

#### Test Task List
```bash
curl -X POST http://127.0.0.1:8000/debug/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"tasks.list","input":{}}' | python -m json.tool | head -50
```

Expected: Should show 111 tools

#### Test Task Run (Amazon Product)
```bash
curl -X POST http://127.0.0.1:8000/debug/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "task_run",
    "input": {
      "tool": "thordata.tools.ecommerce.Amazon.ProductByAsin",
      "param_json": "{\"asin\": \"B0BZYCJK89\"}"
    }
  }' | python -m json.tool
```

## Full Test Suite

### Test All Core Tools

```bash
# 1. Health check
curl http://127.0.0.1:8000/debug/healthz

# 2. List tools (should be 6)
curl -X POST http://127.0.0.1:8000/debug/tools/list \
  -H "Content-Type: application/json" \
  -d '{}' | python -m json.tool | grep -c '"name"'

# 3. Test search
curl -X POST http://127.0.0.1:8000/debug/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"search","input":{"query":"test","num":1}}' | python -m json.tool

# 4. Test scrape
curl -X POST http://127.0.0.1:8000/debug/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"scrape","input":{"url":"https://example.com","output_format":"html"}}' | python -m json.tool

# 5. Test tasks.list
curl -X POST http://127.0.0.1:8000/debug/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name":"tasks.list","input":{}}' | python -m json.tool | python -c "import sys, json; data=json.load(sys.stdin); print(f'Total tools: {len(data[\"output\"][\"tools\"])}')"
```

## Troubleshooting

### Container Exits Immediately

Check logs:
```bash
docker logs thordata-mcp
```

Common issues:
- Missing environment variables
- Port already in use
- Python module not found

### Health Check Fails

1. Check container is running:
   ```bash
   docker ps -a | grep thordata-mcp
   ```

2. Check logs:
   ```bash
   docker logs thordata-mcp
   ```

3. Check port binding:
   ```bash
   docker port thordata-mcp
   ```

### Tools Not Available

1. Verify environment variables:
   ```bash
   docker exec thordata-mcp env | grep THORDATA
   ```

2. Check tool registration:
   ```bash
   docker exec thordata-mcp python -c "from thordata_mcp.tools.utils import iter_tool_request_types; print(len(iter_tool_request_types()))"
   ```

## Cleanup

```bash
# Stop container
docker stop thordata-mcp

# Remove container
docker rm thordata-mcp

# Remove image (optional)
docker rmi thordata-mcp:0.4.0
```
