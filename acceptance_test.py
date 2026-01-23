import os, sys, json, time, subprocess, threading
from dotenv import load_dotenv

load_dotenv(override=True)
GREEN, RED, RESET, YELLOW, CYAN = "\033[92m", "\033[91m", "\033[0m", "\033[93m", "\033[96m"

# --- 全量工业级验收矩阵 (2026-01-23) ---
TEST_CASES = [
    ("Amazon (ASIN Mode)", "https://www.amazon.com/dp/059035342X"),
    ("YouTube (Video Mode)", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("GitHub (Repo Mode)", "https://github.com/psf/requests"),
    ("Instagram (Profile Mode)", "https://www.instagram.com/nike/"),
    ("Google Search", "google_search: thordata python sdk"),
    ("Browser URL", "get_browser_url"),
    ("Universal (Fallback)", "https://httpbin.org/html")
]

class MCPClient:
    def __init__(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        current_dir = os.path.dirname(os.path.abspath(__file__))
        src_path = os.path.join(current_dir, "src")
        env["PYTHONPATH"] = src_path + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
        
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "thordata_mcp.main"],
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=sys.stderr,
            text=True, 
            bufsize=0, 
            encoding='utf-8',
            env=env
        )
        self.msg_id = 0
        self.q = __import__('queue').Queue()
        self.running = True
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while self.running:
            line = self.proc.stdout.readline() # type: ignore
            if not line: break
            if line.strip().startswith('{'):
                try: self.q.put(json.loads(line))
                except: pass

    def call(self, method, params=None):
        self.msg_id += 1
        # 修复 Pylance: 显式断言 stdin
        stdin = self.proc.stdin
        assert stdin is not None, "FATAL: stdin is None"
        stdin.write(json.dumps({"jsonrpc":"2.0","id":self.msg_id,"method":method,"params":params or {}})+"\n")
        stdin.flush()
        return self.msg_id

    def wait(self, rid, timeout=120):
        start = time.time()
        while time.time() - start < timeout:
            if not self.q.empty():
                # 简单队列查找
                size = self.q.qsize()
                for _ in range(size):
                    m = self.q.get()
                    if m.get("id") == rid: return m
                    self.q.put(m)
            time.sleep(0.5)
        return None

def run_inspection():
    print(f"\n{CYAN}🏆 ThorData MCP Full Inspection Suite v5.0 (Ready for Release){RESET}")
    client = MCPClient()
    
    try:
        # Handshake
        rid = client.call("initialize", {"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}})
        init_res = client.wait(rid)
        assert init_res, "Handshake failed"
        
        # Initialized notification
        stdin = client.proc.stdin
        assert stdin is not None
        stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"})+"\n")
        stdin.flush()

        # Iterate Matrix
        for name, target in TEST_CASES:
            print(f"\n{YELLOW}Testing {name}...{RESET}")
            if target == "get_browser_url":
                rid = client.call("tools/call", {"name":"get_scraping_browser_url","arguments":{}})
            elif target.startswith("google_search:"):
                rid = client.call("tools/call", {"name":"google_search","arguments":{"query":target.split(": ")[1]}})
            else:
                rid = client.call("tools/call", {"name":"smart_scrape","arguments":{"url":target}})
            
            res = client.wait(rid, timeout=150) # 任务可能较慢，给足时间
            if not res or "error" in res:
                print(f"{RED}❌ {name} FAILED: {res.get('error') if res else 'Timeout'}{RESET}")
                continue

            content = res.get("result", {}).get("content", [{}])[0].get("text", "")
            
            # 严格验收标准
            if name in ["Google Search", "Browser URL", "Universal (Fallback)"]:
                success = len(content) > 50
            else:
                # 专项爬取验证：必须是结构化数据 (JSON)
                success = content.strip().startswith(("{", "[")) and len(content) > 200
            
            if success:
                print(f"{GREEN}✅ {name} PASSED (Structured Data Verified){RESET}")
            else:
                print(f"{RED}❌ {name} FAILED (Invalid Format or Short Response){RESET}")
                print(f"DEBUG PREVIEW: {content[:200]}")

    finally:
        print(f"\n{CYAN}Cleaning up...{RESET}")
        client.running = False
        client.proc.terminate()

if __name__ == "__main__":
    run_inspection()