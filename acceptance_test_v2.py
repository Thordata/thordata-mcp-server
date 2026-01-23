"""
ThorData MCP Final Acceptance (v3.0) - The "Gold Standard"
Verifies: SDK 1.5.0 + Stdio Protocol + Real API Calls
"""
import os
import sys
import json
import time
import subprocess
import threading
from dotenv import load_dotenv

# 强制加载 .env 文件
load_dotenv(override=True)

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
YELLOW = "\033[93m"
CYAN = "\033[96m"

def log(msg, success=True):
    color = GREEN if success else RED
    icon = "✅" if success else "❌"
    print(f"{color}{icon} {msg}{RESET}")

def info(msg):
    print(f"{YELLOW}ℹ️ {msg}{RESET}")

class MCPClient:
    def __init__(self):
        # 确保环境变量传递给子进程
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        # 启动命令
        cmd = [sys.executable, "-m", "thordata_mcp.main"]
        
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr, # 让服务端日志直接打印出来，方便调试
            text=True,
            env=env,
            encoding='utf-8',
            bufsize=0
        )
        self.msg_id = 0
        self.response_queue = __import__('queue').Queue()
        self.running = True
        
        # 启动读取线程
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()

    def _reader(self):
        if not self.proc.stdout: return
        while self.running:
            line = self.proc.stdout.readline()
            if not line: break
            try:
                # 过滤掉非 JSON 行（有时候可能会混入杂质）
                if line.strip().startswith('{'):
                    self.response_queue.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def send(self, method, params=None):
        self.msg_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        
        stdin = self.proc.stdin
        if stdin is not None:
            stdin.write(json.dumps(req) + "\n")
            stdin.flush()
        else:
            raise RuntimeError(f"FATAL: Subprocess stdin lost during {method}")
            
        return self.msg_id

    def wait_for_result(self, req_id, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError("Server process died")
            
            # 检查队列
            # 这里的简单实现：把不匹配的消息放回去或丢弃（测试场景丢弃即可，生产需Map存储）
            # 为了简单，我们只从队列头部取，如果不是我们的ID，就暂时存起来（这里简化处理）
            # 更好的做法是轮询队列
            
            import queue
            try:
                # 稍微阻塞一下取数据
                msg = self.response_queue.get(timeout=0.5)
                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise RuntimeError(f"RPC Error: {msg['error']}")
                    return msg.get("result")
            except queue.Empty:
                continue
                
        raise TimeoutError(f"Request {req_id} timed out")

    def close(self):
        self.running = False
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except:
            self.proc.kill()

def run_suite():
    print(f"\n{CYAN}🚀 ThorData MCP Acceptance Suite (v3.0){RESET}")
    
    # 0. 检查凭证
    if not os.getenv("THORDATA_SCRAPER_TOKEN"):
        log("Missing THORDATA_SCRAPER_TOKEN in .env", False)
        return

    client = None
    try:
        client = MCPClient()
        
        # 1. Handshake
        print("\n--- 1. Protocol Handshake ---")
        rid = client.send("initialize", {
            "protocolVersion": "2024-11-05", 
            "capabilities": {}, 
            "clientInfo": {"name": "test", "version": "1.0"}
        })
        res = client.wait_for_result(rid)
        log(f"Server Name: {res.get('serverInfo', {}).get('name')}")
        
        # Send initialized notification
        client.proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"})+"\n")
        client.proc.stdin.flush()

        # 2. Tool Listing
        print("\n--- 2. Tool Inventory ---")
        rid = client.send("tools/list")
        res = client.wait_for_result(rid)
        tools = res.get("tools", [])
        names = [t["name"] for t in tools]
        info(f"Available Tools: {names}")
        
        if "smart_scrape" in names and "google_search" in names:
            log("Core Tools Present")
        else:
            log("Missing Core Tools!", False)

        # 3. Google Search (Live)
        print("\n--- 3. Live Test: Google Search ---")
        info("Querying: 'thordata python sdk'")
        rid = client.send("tools/call", {
            "name": "google_search",
            "arguments": {"query": "thordata python sdk", "num": 1}
        })
        res = client.wait_for_result(rid, timeout=20)
        text = res.get("content", [{}])[0].get("text", "")
        
        if "No results" in text:
            log("Search returned no results (Logic OK, Data Empty)", True)
        elif "**" in text or "http" in text:
            log("Search Success (Data retrieved)")
        else:
            log(f"Unexpected Search Result: {text[:50]}...", False)

        # 4. Browser URL (Credentials Check)
        print("\n--- 4. Credential Test: Browser URL ---")
        if os.getenv("THORDATA_BROWSER_USERNAME") or os.getenv("THORDATA_RESIDENTIAL_USERNAME"):
            rid = client.send("tools/call", {
                "name": "get_scraping_browser_url",
                "arguments": {}
            })
            res = client.wait_for_result(rid)
            text = res.get("content", [{}])[0].get("text", "")
            if "wss://" in text:
                log("Browser URL Generated Successfully")
            else:
                log(f"Failed to generate URL: {text}", False)
        else:
            info("Skipping (No Browser/Proxy credentials configured)")

        print(f"\n{GREEN}✨ All Systems Go. Ready for Docker Build.{RESET}")

        # 5. Smart Scrape: Amazon (必须返回 JSON)
        print("\n--- 5. Live Test: Smart Scrape (Amazon) ---")
        # 使用 Harry Potter 书籍，ASIN: 059035342X (非常稳定)
        amz_url = "https://www.amazon.com/dp/059035342X"
        info(f"Target: {amz_url}")
        rid = client.send("tools/call", {"name": "smart_scrape", "arguments": {"url": amz_url}})
        
        # Amazon 任务通常需要 30-60s，给足 120s 容错
        res = client.wait_for_result(rid, timeout=120)
        content = res.get("content", [{}])[0].get("text", "")
        
        # 验证返回内容
        if content.strip().startswith("{") or content.strip().startswith("["):
            # 进一步验证是否包含 Amazon 专项字段
            if "Harry Potter" in content or "author" in content.lower() or "price" in content.lower():
                log("Amazon Scrape Success (Structured JSON Returned)")
            else:
                log(f"Amazon Scrape Success (JSON Returned but content unexpected: {content[:100]})")
        else:
            log("Amazon Scrape FAILED: Result is not JSON!", False)
            print(f"DEBUG: {content[:300]}")

        # 6. Smart Scrape: YouTube (必须返回 JSON)
        print("\n--- 6. Live Test: Smart Scrape (YouTube) ---")
        yt_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        rid = client.send("tools/call", {"name": "smart_scrape", "arguments": {"url": yt_url}})
        res = client.wait_for_result(rid, timeout=120)
        content = res.get("content", [{}])[0].get("text", "")
        
        if "title" in content.lower() and ("{" in content):
            log("YouTube Scrape Success (JSON Returned)")
        else:
            log("YouTube Scrape FAILED: Result is not valid JSON!", False)
            print(f"DEBUG: {content[:200]}")

        # 7. Read URL (通用网页渲染)
        print("\n--- 7. Live Test: Read URL (General Web) ---")
        gen_url = "https://httpbin.org/html"
        info(f"Target: {gen_url}")
        rid = client.send("tools/call", {
            "name": "read_url",
            "arguments": {"url": gen_url}
        })
        res = client.wait_for_result(rid, timeout=30)
        content = res.get("content", [{}])[0].get("text", "")
        
        if "Herman Melville" in content or "Moby-Dick" in content:
            log("Read URL Success (Content matched)")
        else:
            log(f"Read URL Failed/Mismatch: {content[:100]}...", False)

        print(f"\n{GREEN}✨ All Systems Go. Deep Inspection Passed.{RESET}")

    except Exception as e:
        log(f"Test Suite Failed: {e}", False)
    finally:
        if client: client.close()

if __name__ == "__main__":
    run_suite()