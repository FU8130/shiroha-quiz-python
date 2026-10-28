# -*- coding: utf-8 -*-
"""局域网访问 / 访问口令自测（纯标准库：unittest + threading + http.client）。

跑法：python tests/test_lan_token.py
服务在 127.0.0.1 的临时端口上起，不碰正在运行的 8799。
"""
import http.client
import os
import sys
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.server import AUTH_COOKIE, _build_server  # noqa: E402

TOKEN = "s3cret-中文口令"
TOKEN_QUOTED = urllib.parse.quote(TOKEN, safe="")


class _ServerCase(unittest.TestCase):
    """每个用例起一个独立服务实例（端口 0 = 系统分配）。"""

    token = ""

    def setUp(self):
        self.httpd = _build_server(0, "127.0.0.1", self.token)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def request(self, path, headers=None, method="GET", body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, dict(resp.getheaders()), data
        finally:
            conn.close()

    def cookie_headers(self):
        return {"Cookie": f"{AUTH_COOKIE}={TOKEN_QUOTED}"}


class NoTokenTest(_ServerCase):
    """没设口令：行为与旧版一致，全部放行。"""

    token = ""

    def test_static_and_api_open(self):
        for path in ("/", "/index.html", "/app.js", "/api/health"):
            status, _h, _b = self.request(path)
            self.assertEqual(status, 200, f"{path} 应可直接访问")

    def test_nosniff_header(self):
        _s, headers, _b = self.request("/api/health")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_query_token_ignored(self):
        # 没设口令时 ?k= 只是普通查询参数，不影响访问
        status, _h, _b = self.request("/?k=whatever")
        self.assertEqual(status, 200)


class TokenGateTest(_ServerCase):
    """设了口令：无 k/Cookie → 401；正确 k → 302 + Cookie；Cookie → 200；错误 k → 401。"""

    token = TOKEN

    def test_no_token_401_for_static_and_api(self):
        for path in ("/", "/index.html", "/app.js", "/api/health", "/api/state"):
            status, headers, body = self.request(path)
            self.assertEqual(status, 401, f"{path} 未带口令应 401")
            self.assertIn("text/html; charset=utf-8", headers.get("Content-Type", ""))
            self.assertIn("需要访问口令".encode("utf-8"), body)
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_correct_k_302_with_cookie(self):
        status, headers, _b = self.request(f"/?k={TOKEN_QUOTED}")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("Location"), "/")
        cookie = headers.get("Set-Cookie", "")
        self.assertIn(f"{AUTH_COOKIE}={TOKEN_QUOTED}", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Max-Age=2592000", cookie)  # 30 天

    def test_cookie_grants_access(self):
        for path in ("/", "/app.js", "/api/health", "/api/state"):
            status, _h, _b = self.request(path, self.cookie_headers())
            self.assertEqual(status, 200, f"{path} 带正确 Cookie 应 200")

    def test_wrong_k_401(self):
        status, _h, body = self.request("/?k=wrong-token")
        self.assertEqual(status, 401)
        self.assertIn("需要访问口令".encode("utf-8"), body)

    def test_wrong_cookie_401(self):
        status, _h, _b = self.request("/", {"Cookie": f"{AUTH_COOKIE}=nope"})
        self.assertEqual(status, 401)

    def test_302_keeps_other_query_params(self):
        status, headers, _b = self.request(f"/app.js?k={TOKEN_QUOTED}&v=1")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("Location"), "/app.js?v=1")

    def test_post_gated_too(self):
        payload = b'{"level":"info","msg":"probe"}'
        # 无口令：POST 也要 401，且客户端能正常收到响应（请求体已被读掉）
        status, _h, _b = self.request("/api/log", {"Content-Length": str(len(payload))},
                                      method="POST", body=payload)
        self.assertEqual(status, 401)
        # 带 Cookie：过了闸门，走到原来的路由逻辑（未知 /api 路径不会 401）
        status2, _h2, _b2 = self.request(
            "/api/not-a-real-endpoint",
            dict(self.cookie_headers(), **{"Content-Length": "0"}),
            method="POST", body=b"",
        )
        self.assertNotEqual(status2, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
