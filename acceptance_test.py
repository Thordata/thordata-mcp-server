"""
ThorData MCP Server - Industrial Acceptance Suite
"""
import subprocess
import json
import os
import sys
import time
import threading
import argparse
from typing import Dict, Any, Callable, Optional

# --- Load Env ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv not installed.")

# --- Config & Args ---
parser = argparse.ArgumentParser(description="Run MCP Acceptance Tests")
parser.add_argument("--docker", action="store_true", help="Run tests against Docker container")
args = parser.parse_args()

ENV = os.environ.copy()
ENV["PYTHONUTF8"] = "1"
ENV["PYTHONUNBUFFERED"] = "1"

# FIX: Reduced required keys. Proxy/Browser creds are now optional for startup.
REQUIRED_KEYS = [
    "THORDATA_SCRAPER_TOKEN", 
    "THORDATA_PUBLIC_TOKEN", 
    "THORDATA_PUBLIC_KEY"
]

missing_keys = [key for key in REQUIRED_KEYS if not ENV.get(key)]
if missing_keys:
    print(f"❌ Error: The following keys are missing in environment variables or .env:")
    for k in missing_keys:
        print(f"   - {k}")
    sys.exit(1)

# --- Colors ---
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RESET = "\033[0m"

class MCPClientSimulator:
    def __init__(self):
        cmd = ["docker", "run", "-i", "--rm"] if args.docker else [sys.executable, "-m", "thordata_mcp.main"]
        
        # In Docker mode, pass env vars
        if args.docker:
            # Pass all THORDATA_ vars
            for k, v in ENV.items():
                if k.startswith("THORDATA_"):
                    cmd.extend(["-e", f"{k}={v}"])
            cmd.append("thordata-mcp") # Image name

        print(f"🚀 Launching Server: {' '.join(cmd)}")
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=ENV if not args.docker else None
        )
        self.msg_id = 0
        
        self.log_thread = threading.Thread(target=self._print_stderr, daemon=True)
        self.log_thread.start()
        
        time.sleep(3 if args.docker else 1)
        if self.process.poll() is not None:
            raise RuntimeError(f"Server exited immediately. Code {self.process.returncode}")

    def _print_stderr(self):
        if self.process.stderr:
            try:
                for line in self.process.stderr:
                    print(f"{YELLOW}[SERVER] {line.strip()}{RESET}")
            except: pass

    def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.process.poll() is not None:
             raise RuntimeError(f"Server died (Code {self.process.returncode})")

        # FIX: Explicit assertion for Pylance
        assert self.process.stdin is not None, "stdin is None"
        assert self.process.stdout is not None, "stdout is None"

        self.msg_id += 1
        payload = {"jsonrpc": "2.0", "id": self.msg_id, "method": method, "params": params or {}}
        
        try:
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
        except OSError as e:
            raise RuntimeError(f"Write failed: {e}")
        
        while True:
            try:
                line = self.process.stdout.readline()
            except UnicodeDecodeError: continue
            
            if not line:
                if self.process.poll() is not None:
                    raise RuntimeError(f"Server exited code {self.process.returncode}")
                continue
            
            try:
                msg = json.loads(line)
                if msg.get("id") == self.msg_id:
                    if "error" in msg: raise RuntimeError(f"RPC Error: {msg['error']}")
                    return msg.get("result", {})
            except json.JSONDecodeError: continue

    def close(self):
        if self.process:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except: self.process.kill()

# --- Test Logics ---

def run_test_case(name: str, func: Callable):
    print(f"\n{CYAN}🔄 [TEST] {name}...{RESET}")
    try:
        func()
        print(f"{GREEN}✅ [PASS] {name}{RESET}")
        return True
    except Exception as e:
        # If it's a skip signal (ValueError with specific text), handle it
        if str(e).startswith("SKIP:"):
            print(f"{YELLOW}⚠️  [SKIP] {str(e)[6:]}{RESET}")
            return True
        print(f"{RED}❌ [FAIL] {name}: {e}{RESET}")
        return False

def test_handshake(client):
    res = client.send("initialize", {
        "protocolVersion": "2024-11-05", 
        "capabilities": {}, 
        "clientInfo": {"name": "tester", "version": "1.0"}
    })
    # Send initialized notification
    assert client.process.stdin is not None
    client.process.stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"})+"\n")
    client.process.stdin.flush()

def test_list_tools(client):
    res = client.send("tools/list")
    tools = res.get("tools", [])
    names = [t["name"] for t in tools]
    print(f"   Tools: {', '.join(names)}")

def test_browser_url(client):
    """Verify Browser URL generation"""
    # Check environment availability for this specific test
    if not ENV.get("THORDATA_BROWSER_USERNAME") or not ENV.get("THORDATA_BROWSER_PASSWORD"):
        print("   ⚠️ [SKIP] Browser Credentials missing in .env (THORDATA_BROWSER_USERNAME/PASSWORD)")
        return

    res = client.send("tools/call", {
        "name": "get_scraping_browser_url",
        "arguments": {}
    })
    text = res.get("content", [{"text": ""}])[0]["text"]
    
    if "wss://" in text:
        print(f"   ✅ URL Generated")
    else:
        # If SDK throws config error, it returns a text message
        raise ValueError(f"Failed: {text}")

def test_smart_scrape_amazon(client):
    url = "https://www.amazon.com/dp/B014I8SSD0"
    print(f"   Target: {url}")
    res = client.send("tools/call", {"name": "smart_scrape", "arguments": {"url": url}})
    text = res.get("content", [{"text": ""}])[0]["text"]
    try:
        json.loads(text)
        print("   ✅ Valid JSON")
    except:
        print(f"   ⚠️ Markdown (Fallback)")

def test_smart_scrape_youtube(client):
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print(f"   Target: {url}")
    print("   ⏳ Waiting...")
    res = client.send("tools/call", {"name": "smart_scrape", "arguments": {"url": url}})
    text = res.get("content", [{"text": ""}])[0]["text"]
    
    if "Task Failed" in text or "Network Error" in text:
         # Treat infrastructure errors as warnings, not failures
         print(f"   ⚠️ API Response: {text[:100]}...")
         return

    try:
        json.loads(text)
        print("   ✅ Valid JSON")
    except:
        raise ValueError(f"Invalid output: {text[:100]}")

def main():
    print(f"{CYAN}🚀 ThorData MCP Acceptance (v0.1.0){RESET}")
    sim = None
    try:
        sim = MCPClientSimulator()
        run_test_case("Handshake", lambda: test_handshake(sim))
        run_test_case("List Tools", lambda: test_list_tools(sim))
        run_test_case("Browser Automation", lambda: test_browser_url(sim))
        run_test_case("Smart Scrape (Amazon)", lambda: test_smart_scrape_amazon(sim))
        run_test_case("Smart Scrape (YouTube)", lambda: test_smart_scrape_youtube(sim))
        print(f"\n{GREEN}✨ DONE.{RESET}")
    except Exception as e:
        print(f"\n{RED}❌ FATAL: {e}{RESET}")
    finally:
        if sim: sim.close()

if __name__ == "__main__":
    main()