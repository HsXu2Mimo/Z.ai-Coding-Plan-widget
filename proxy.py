#!/usr/bin/env python3
"""
Z.ai 用量面板本地服务(纯标准库)

功能:
  1. 托管 widget 页面        http://127.0.0.1:8788/
  2. 转发官方用量接口        http://127.0.0.1:8788/proxy?url=<编码后的官方接口>
  3. 密钥管理(加密存储):
       GET  /key/status      查看状态(只返回打码指纹,不返回明文)
       POST /key {"key":...} 用 Windows DPAPI 加密后写入 key.enc,立即生效
  4. 自动注入 Authorization:请求没带该头时,按优先级取密钥:
       环境变量 ZAI_API_KEY > key.enc(DPAPI 加密)> key.txt(明文兜底)

用法:
  python proxy.py            # 默认 8788 端口
  python proxy.py 9000       # 指定端口
若端口已被占用(服务已在运行),直接退出,方便重复双击启动。
"""
import base64
import ctypes
import http.server
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
ROOT = os.path.dirname(os.path.abspath(__file__))
ALLOWED_HOSTS = {"api.z.ai", "open.bigmodel.cn", "dev.bigmodel.cn"}
FORWARD_HEADERS = ("Authorization", "Accept", "Accept-Language", "Content-Type")
KEY_ENC_PATH = os.path.join(ROOT, "key.enc")
KEY_TXT_PATH = os.path.join(ROOT, "key.txt")
VAULT_PATH = os.path.join(ROOT, "key.vault.json")


# ---------- Windows DPAPI(密钥绑定当前 Windows 用户,磁盘无明文) ----------

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def dpapi_protect(data: bytes) -> bytes:
    out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(_blob(data)), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def dpapi_unprotect(blob: bytes) -> bytes:
    out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(_blob(blob)), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def mask(key: str) -> str:
    if len(key) <= 6:
        return "****"
    return key[:2] + "****" + key[-4:]


def read_key_enc():
    """解密 key.enc;失败(如文件被复制到其他用户)返回 None"""
    try:
        with open(KEY_ENC_PATH, encoding="utf-8") as f:
            blob = base64.b64decode(f.read().strip())
        key = dpapi_unprotect(blob).decode("utf-8").strip()
        return key or None
    except Exception:  # noqa: BLE001
        return None


def read_key_txt():
    try:
        with open(KEY_TXT_PATH, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError:
        pass
    return ""


def load_key():
    env = os.environ.get("ZAI_API_KEY", "").strip()
    if env:
        return env
    enc = read_key_enc()
    if enc:
        return enc
    return read_key_txt()


# ---------- 密钥保险库(每个账号一个 DPAPI 加密条目,浏览器只持有引用句柄) ----------

def vault_load():
    try:
        with open(VAULT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def vault_save(vault):
    with open(VAULT_PATH, "w", encoding="utf-8") as f:
        json.dump(vault, f)


def vault_store(key: str) -> str:
    ref = "k_" + secrets.token_hex(8)
    vault = vault_load()
    vault[ref] = base64.b64encode(dpapi_protect(key.encode("utf-8"))).decode("ascii")
    vault_save(vault)
    return ref


def vault_get(ref: str):
    blob = vault_load().get(ref)
    if not blob:
        return None
    try:
        key = dpapi_unprotect(base64.b64decode(blob)).decode("utf-8").strip()
        return key or None
    except Exception:  # noqa: BLE001
        return None


# ---------- HTTP ----------

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self.serve_file("index.html", "text/html; charset=utf-8")
        if u.path == "/proxy":
            return self.forward(u.query)
        if u.path == "/key/status":
            return self.key_status()
        self.send_error(404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/key":
            return self.save_key()
        if u.path == "/key/store":
            return self.store_key()
        self.send_error(404)

    def do_DELETE(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/key/store":
            params = urllib.parse.parse_qs(u.query)
            ref = (params.get("ref") or [""])[0]
            vault = vault_load()
            if ref in vault:
                del vault[ref]
                vault_save(vault)
                return self._json(200, {"ok": True, "forgotten": ref})
            return self._json(200, {"ok": True, "forgotten": None})
        self.send_error(404)

    def store_key(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4096:
            return self.send_error(413)
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "invalid json"})
        key = (data.get("key") or "").strip()
        if not key:
            return self._json(400, {"ok": False, "error": "key is empty"})
        try:
            ref = vault_store(key)
        except OSError as e:
            return self._json(500, {"ok": False, "error": str(e)})
        return self._json(200, {"ok": True, "ref": ref, "masked": mask(key)})

    def serve_file(self, name, ctype):
        try:
            with open(os.path.join(ROOT, name), "rb") as f:
                self._send(200, f.read(), ctype)
        except OSError as e:
            self.send_error(500, str(e))

    def key_status(self):
        env = os.environ.get("ZAI_API_KEY", "").strip()
        if env:
            return self._json(200, {"configured": True, "source": "env", "masked": mask(env)})
        enc = read_key_enc()
        if enc:
            return self._json(200, {"configured": True, "source": "key.enc", "masked": mask(enc)})
        txt = read_key_txt()
        if txt:
            return self._json(200, {"configured": True, "source": "key.txt", "masked": mask(txt)})
        return self._json(200, {"configured": False, "source": None, "masked": None})

    def save_key(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4096:
            return self.send_error(413)
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "invalid json"})
        key = (data.get("key") or "").strip()
        if not key:
            # 空 key = 清除已保存的加密密钥
            try:
                os.remove(KEY_ENC_PATH)
                return self._json(200, {"ok": True, "cleared": True})
            except OSError:
                return self._json(200, {"ok": True, "cleared": False})
        try:
            blob = base64.b64encode(dpapi_protect(key.encode("utf-8")))
            with open(KEY_ENC_PATH, "w", encoding="utf-8") as f:
                f.write(blob.decode("ascii"))
        except OSError as e:
            return self._json(500, {"ok": False, "error": str(e)})
        return self._json(200, {"ok": True, "masked": mask(key)})

    def forward(self, query):
        params = urllib.parse.parse_qs(query)
        target = (params.get("url") or [""])[0]
        u = urllib.parse.urlparse(target)
        if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
            self.send_error(403, "only official Z.ai / bigmodel hosts are allowed")
            return

        req = urllib.request.Request(target, method="GET")
        has_auth = False
        for h in FORWARD_HEADERS:
            v = self.headers.get(h)
            if v:
                req.add_header(h, v)
                has_auth = has_auth or h == "Authorization"
        if not has_auth:
            # 账号级密钥引用(X-Key-Ref: 由 /key/store 加密库签发)优先,其次全局密钥
            ref = self.headers.get("X-Key-Ref")
            key = vault_get(ref) if ref else None
            if not key:
                key = load_key()
            if key:
                req.add_header("Authorization", key)
        req.add_header("User-Agent", "zai-usage-widget/1.0")

        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            body, status = e.read(), e.code
        except Exception as e:  # noqa: BLE001
            self._send(502, ("upstream error: %s" % e).encode(), "text/plain; charset=utf-8")
            return

        self._send(status, body, "application/json; charset=utf-8")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # 静默访问日志
        pass


class Server(http.server.ThreadingHTTPServer):
    # Windows 下 SO_REUSEADDR 会放行多个进程绑同一端口,必须显式关闭,
    # 这样重复启动时 bind 才会失败退出
    allow_reuse_address = False


if __name__ == "__main__":
    try:
        server = Server(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"port {PORT} already in use, server is probably running")
        sys.exit(0)
    print(f"Z.ai usage widget serving at http://127.0.0.1:{PORT}/?live=1")
    print(f"proxy endpoint   : http://127.0.0.1:{PORT}/proxy?url={{url}}")
    print("api key source   : env ZAI_API_KEY > key.enc (DPAPI) > key.txt")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
