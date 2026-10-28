# -*- coding: utf-8 -*-
"""内容指纹改为只覆盖“数据本身”，排除导出元数据与派生时间戳。"""
from pathlib import Path

APP = Path(r"F:\workspace\quiz_py") / "gui" / "static" / "app.js"
HTML = Path(r"F:\workspace\quiz_py") / "gui" / "static" / "index.html"

s = APP.read_text(encoding="utf-8")

old = """function webdavPayloadDigestTextV378(payload){
  const omit=new Set(['exportedAt','appVersion']);
  try{return JSON.stringify(payload,(k,v)=>omit.has(k)?undefined:v)}catch(_){return JSON.stringify(payload)}
}
"""
assert s.count(old) == 1, "旧指纹函数未找到"
new = """function webdavPayloadDigestTextV378(payload){
  const p=payload||{};
  const pick={schemaVersion:p.schemaVersion,activeBankId:p.activeBankId,banks:p.banks||[],wrongBook:p.wrongBook||[],favorites:p.favorites||[],records:p.records||[],settings:p.settings||{}};
  try{return JSON.stringify(pick)}catch(_){return JSON.stringify(payload)}
}
"""
s = s.replace(old, new, 1)

# 说明注释：让后来者知道为什么不是整份 JSON
anchor = "async function uploadWebdavBackupV378(autoMode){"
assert s.count(anchor) == 1
s = s.replace(anchor, "// 指纹只算数据本身：exportedAt、appVersion、crossPlatform 里的 favoritedAt 每次导出都会变，不能参与命名。\n" + anchor, 1)

APP.write_text(s, encoding="utf-8")

h = HTML.read_text(encoding="utf-8")
assert "app.js?v=17" in h
h = h.replace("app.js?v=17", "app.js?v=18", 1)
HTML.write_text(h, encoding="utf-8")
print("OK")
