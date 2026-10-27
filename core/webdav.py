# -*- coding: utf-8 -*-
"""极简 WebDAV 客户端（仅标准库）：列出、上传、下载、建目录。"""
import base64
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DAV_NS = "{DAV:}"


class WebDAVError(RuntimeError):
    pass


class WebDAVClient:
    def __init__(self, base_url, user="", password="", timeout=30):
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password
        self.timeout = timeout

    # ---------- 基础 ----------
    def _url(self, path=""):
        path = (path or "").strip("/")
        if not path:
            return self.base_url + "/"
        parts = [urllib.parse.quote(p) for p in path.split("/") if p]
        return self.base_url + "/" + "/".join(parts)

    def _request(self, method, path="", data=None, headers=None, depth=None):
        req = urllib.request.Request(self._url(path), data=data, method=method)
        if self.user:
            token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            req.add_header("Authorization", "Basic " + token)
        if depth is not None:
            req.add_header("Depth", str(depth))
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            raise WebDAVError(f"{method} {path or '/'} -> HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise WebDAVError(f"连接失败：{exc.reason}") from exc

    # ---------- 操作 ----------
    def test(self):
        self._request("PROPFIND", "", depth=0, headers={"Content-Type": "application/xml"})
        return True

    def mkcol(self, path):
        try:
            self._request("MKCOL", path)
        except WebDAVError:
            pass  # 已存在也当成功

    def put(self, path, data: bytes):
        self._request("PUT", path, data=data,
                      headers={"Content-Type": "application/zip"})
        return len(data)

    def delete(self, path):
        self._request("DELETE", path)

    def get(self, path) -> bytes:
        _, body = self._request("GET", path)
        return body

    def stat(self, path=""):
        """返回 (size, last_modified)；不支持时返回 None。"""
        try:
            _, body = self._request("PROPFIND", path, depth=0,
                                    headers={"Content-Type": "application/xml"})
        except WebDAVError:
            return None
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return None
        size_el = root.find(f".//{DAV_NS}getcontentlength")
        mod_el = root.find(f".//{DAV_NS}getlastmodified")
        size = int(size_el.text) if (size_el is not None and (size_el.text or "").isdigit()) else -1
        mod = (mod_el.text or "").strip() if mod_el is not None else ""
        return size, mod

    def list_dir(self, path=""):
        try:
            _, body = self._request("PROPFIND", path, depth=1,
                                    headers={"Content-Type": "application/xml"})
        except WebDAVError:
            return []
        out = []
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return []
        base = path.strip("/")
        for resp in root.findall(f"{DAV_NS}response"):
            href_el = resp.find(f"{DAV_NS}href")
            if href_el is None or not href_el.text:
                continue
            href = urllib.parse.unquote(href_el.text.strip())
            name = href.rstrip("/").split("/")[-1]
            if not name or name == base.split("/")[-1]:
                continue
            size = 0
            length_el = resp.find(f".//{DAV_NS}getcontentlength")
            if length_el is not None and (length_el.text or "").isdigit():
                size = int(length_el.text)
            is_dir = resp.find(f".//{DAV_NS}collection") is not None
            out.append({"name": name, "size": size, "is_dir": is_dir, "href": href})
        return out

    def ensure_dir(self, path):
        if not path:
            return
        parts = [p for p in path.strip("/").split("/") if p]
        acc = ""
        for p in parts:
            acc = f"{acc}/{p}" if acc else p
            self.mkcol(acc)
