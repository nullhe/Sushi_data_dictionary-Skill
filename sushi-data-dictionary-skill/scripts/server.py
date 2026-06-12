#!/usr/bin/env python3
"""
数据字典本地服务器
提供 HTML 静态服务 + 注释编辑 API。

用法:
    python server.py [--port 8080]

浏览器打开 http://localhost:8080
"""

import argparse
import json
import os
import re
import socket
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class DualStackHTTPServer(HTTPServer):
    """同时监听 IPv4 和 IPv6 的 HTTP 服务器。"""

    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()

BASE_DIR = Path(__file__).parent.resolve()
TABLES_DIR = BASE_DIR / "tables"


class DictHandler(SimpleHTTPRequestHandler):
    """处理静态文件和 API 请求。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/save-comment":
            self._handle_save_comment()
        else:
            self.send_error(404, "Not Found")

    def _handle_save_comment(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)

            table_name = data.get("table", "").strip()
            field_name = data.get("field", "").strip()
            comment = data.get("comment", "")

            if not table_name:
                self._json_response(False, "缺少表名")
                return

            md_path = TABLES_DIR / f"{table_name}.md"
            if not md_path.exists():
                self._json_response(False, f"文件不存在: {md_path}")
                return

            with open(md_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if field_name:
                success = self._update_field_comment(lines, field_name, comment)
            else:
                success = self._update_table_comment(lines, comment)

            if success:
                with open(md_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                self._json_response(True, "保存成功")
            else:
                self._json_response(False, f"未找到字段: {field_name}" if field_name else "未找到表注释")

        except json.JSONDecodeError:
            self._json_response(False, "无效的 JSON")
        except Exception as e:
            self._json_response(False, str(e))

    def _update_field_comment(self, lines, field_name, new_comment):
        """更新字段注释。定位字段所在行，修改注释列。"""
        for i, line in enumerate(lines):
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.split("|")]
            # 跳过表头和分隔行
            if len(cells) < 8:
                continue
            if cells[1] == "#":
                continue
            if all(c.replace("-", "").replace(":", "") == "" for c in cells[1:-1]):
                continue

            # 字段名在第 2 列 (index 2)
            if len(cells) > 2 and cells[2] == field_name:
                # 注释在第 7 列 (index 7)
                if len(cells) > 7:
                    cells[7] = f" {new_comment} "
                    lines[i] = "|".join(cells) + "\n"
                    return True
        return False

    def _update_table_comment(self, lines, new_comment):
        """更新表注释。定位 > 开头的描述行。"""
        for i, line in enumerate(lines):
            if line.startswith("> "):
                desc = line[2:].strip()
                parts = [p.strip() for p in desc.split("|")]
                if parts:
                    parts[0] = new_comment
                    lines[i] = "> " + " | ".join(parts) + "\n"
                    return True
        return False

    def _json_response(self, ok, message=""):
        status = 200 if ok else 400
        body = json.dumps({"ok": ok, "message": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """处理 CORS 预检请求。"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        """简化日志格式。"""
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    parser = argparse.ArgumentParser(description="数据字典本地服务器")
    parser.add_argument("--port", type=int, default=8080, help="端口号 (默认 8080)")
    args = parser.parse_args()

    if not (BASE_DIR / "index.html").exists():
        print(f"错误: 未找到 {BASE_DIR / 'index.html'}")
        print("请先运行数据字典生成脚本。")
        sys.exit(1)

    try:
        server = DualStackHTTPServer(("::", args.port), DictHandler)
    except OSError:
        server = HTTPServer(("0.0.0.0", args.port), DictHandler)
    print(f"数据字典服务器已启动")
    print(f"访问地址: http://localhost:{args.port}")
    print(f"按 Ctrl+C 停止")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        server.server_close()


if __name__ == "__main__":
    main()
