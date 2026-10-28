# -*- coding: utf-8 -*-
"""阶段 3 修正：先看远端有没有新备份，再看本地数据有没有变（否则“数据未变”会掩盖远端更新）。"""
from pathlib import Path

APP = Path(r"F:\workspace\quiz_py") / "gui" / "static" / "app.js"
HTML = Path(r"F:\workspace\quiz_py") / "gui" / "static" / "index.html"

s = APP.read_text(encoding="utf-8")

unchanged = "  if(autoMode&&config.lastUploadSha===sha){setWebdavAutoStatusV379('数据没有变化，本次自动备份跳过。');return {skipped:true,reason:'unchanged'}}\n"
assert s.count(unchanged) == 1, "未变跳段未找到"
s = s.replace(unchanged, "", 1)

anchor = "  const gz=await gzipBytesV378(bytes),payloadBytes=gz||bytes;"
assert s.count(anchor) == 1
s = s.replace(anchor, unchanged + anchor, 1)

APP.write_text(s, encoding="utf-8")

h = HTML.read_text(encoding="utf-8")
assert "app.js?v=19" in h
h = h.replace("app.js?v=19", "app.js?v=20", 1)
HTML.write_text(h, encoding="utf-8")

# 顺序自检
i = s.find("async function uploadWebdavBackupV378(autoMode)")
frag = s[i:i + 3400]
print("远端判定先于未变判定:", frag.find("remoteChanged") < frag.find("数据没有变化"))
print("OK")
