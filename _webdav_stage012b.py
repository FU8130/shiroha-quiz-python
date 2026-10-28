# -*- coding: utf-8 -*-
"""阶段 1 修正：指纹只算数据内容（排除 exportedAt / appVersion），恢复侧同步校验。"""
from pathlib import Path

BASE = Path(r"F:\workspace\quiz_py")
APP = BASE / "gui" / "static" / "app.js"
HTML = BASE / "gui" / "static" / "index.html"

s = APP.read_text(encoding="utf-8")
log = []


def rep(old, new, count=1, label=""):
    global s
    n = s.count(old)
    assert n == count, f"{label}: 期望 {count}，实际 {n}\n---\n{old[:300]}"
    s = s.replace(old, new, count)
    log.append(label)


# ---- 1. 新增指纹辅助函数 ----
anchor = "async function gzipBytesV378(bytes){"
assert s.count(anchor) == 1
helper = '''function webdavPayloadDigestTextV378(payload){
  const omit=new Set(['exportedAt','appVersion']);
  try{return JSON.stringify(payload,(k,v)=>omit.has(k)?undefined:v)}catch(_){return JSON.stringify(payload)}
}
'''
s = s.replace(anchor, helper + anchor, 1)
log.append("新增 webdavPayloadDigestTextV378")

# ---- 2. 上传：先建 payload，指纹只算数据 ----
old = (
    "  let text;try{text=JSON.stringify(buildBackupPayloadV23(state.banks||[],'all_data',true))}"
    "catch(error){if(typeof isStringTooLargeErrorV376==='function'&&isStringTooLargeErrorV376(error))"
    "throw webdavErrorV378('当前完整备份过大，浏览器无法生成上传文本。请先减少大图片或拆分成多个题库。',{code:'payload_too_large'});throw error}\n"
    "  const bytes=new TextEncoder().encode(text),sha=await sha256HexV378(bytes);"
)
assert s.count(old) == 1, "上传 payload 段未找到"
new = (
    "  let payload,text;try{payload=buildBackupPayloadV23(state.banks||[],'all_data',true);text=JSON.stringify(payload)}"
    "catch(error){if(typeof isStringTooLargeErrorV376==='function'&&isStringTooLargeErrorV376(error))"
    "throw webdavErrorV378('当前完整备份过大，浏览器无法生成上传文本。请先减少大图片或拆分成多个题库。',{code:'payload_too_large'});throw error}\n"
    "  const bytes=new TextEncoder().encode(text),sha=await sha256HexV378(new TextEncoder().encode(webdavPayloadDigestTextV378(payload)));"
)
rep(old, new, 1, "上传指纹改为内容摘要")

# ---- 3. 恢复：先解析，再按新/旧规则校验 ----
old3 = (
    "  let rawBytes=new Uint8Array(await response.arrayBuffer());"
    "if(/\\.gz$/i.test(fileName))rawBytes=await gunzipBytesV378(rawBytes);"
    "const bytes=rawBytes,sha=await sha256HexV378(bytes),"
    "newMatch=String(fileName).match(WEBDAV_BACKUP_FILE_RE_V378),"
    "legacyMatch=String(fileName).match(WEBDAV_LEGACY_FILE_RE_V378),"
    "expected=(newMatch?String(newMatch[1]):String((legacyMatch||[])[3]||'')).toLowerCase();"
    "if(!expected||sha.slice(0,expected.length)!==expected)throw webdavErrorV378('备份文件 SHA-256 与文件名不一致，已停止恢复。',"
    "{code:'sha_mismatch',method:'GET',url:webdavUrlV378(config,remoteDir+'/'+fileName)});"
)
assert s.count(old3) == 1, "恢复校验段未找到"
new3 = (
    "  let rawBytes=new Uint8Array(await response.arrayBuffer());"
    "if(/\\.gz$/i.test(fileName))rawBytes=await gunzipBytesV378(rawBytes);"
    "const bytes=rawBytes;"
    "let data;try{data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes))}catch(_){throw webdavErrorV378('远程备份不是有效的 UTF-8 JSON。',{code:'json_invalid'})}"
    "const newMatch=String(fileName).match(WEBDAV_BACKUP_FILE_RE_V378),legacyMatch=String(fileName).match(WEBDAV_LEGACY_FILE_RE_V378);"
    "let sha;"
    "if(newMatch){sha=await sha256HexV378(new TextEncoder().encode(webdavPayloadDigestTextV378(data)));"
    "const expected=String(newMatch[1]).toLowerCase();"
    "if(sha.slice(0,expected.length)!==expected)throw webdavErrorV378('备份内容指纹与文件名不一致，已停止恢复。',{code:'sha_mismatch',method:'GET',url:webdavUrlV378(config,remoteDir+'/'+fileName)})}"
    "else{sha=await sha256HexV378(bytes);const expected=String((legacyMatch||[])[3]||'').toLowerCase();"
    "if(!expected||sha.slice(0,8)!==expected)throw webdavErrorV378('备份文件 SHA-256 与文件名不一致，已停止恢复。',{code:'sha_mismatch',method:'GET',url:webdavUrlV378(config,remoteDir+'/'+fileName)})}"
)
rep(old3, new3, 1, "恢复校验：内容指纹 + 旧格式兼容")

# ---- 4. 去掉后面重复的解析 ----
old4 = (
    "  let data;try{data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes))}"
    "catch(_){throw webdavErrorV378('远程备份不是有效的 UTF-8 JSON。',{code:'json_invalid'})}\n"
)
if s.count(old4) == 1:
    s = s.replace(old4, "", 1)
    log.append("移除重复解析")
else:
    # 可能已被第 3 步替换掉（同一行内合并），记录实际状态
    log.append(f"重复解析检查：出现 {s.count(old4)} 次，未处理")

# ---- 5. 文案 ----
rep(
    "仅显示本应用生成的时间戳备份；V37.8 不提供远端删除。",
    "仅显示本应用生成的内容指纹备份；不提供远端删除。",
    1,
    "列表文案",
)

# ---- 6. 版本 ----
rep("const APP_VERSION='V39：云备份内容寻址版';", "const APP_VERSION='V40：云备份内容寻址版';", 1, "APP_VERSION")

APP.write_text(s, encoding="utf-8")

h = HTML.read_text(encoding="utf-8")
assert "app.js?v=16" in h
h = h.replace("app.js?v=16", "app.js?v=17", 1)
HTML.write_text(h, encoding="utf-8")

print("OK")
for x in log:
    print(" -", x)
# 残留检查
for pat in ["WEBDAV_BACKUP_FILE_RE_V378.test(fileName)", "自动同步"]:
    print(f"残留 {pat}: {s.count(pat)}")
