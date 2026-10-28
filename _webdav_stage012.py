# -*- coding: utf-8 -*-
"""阶段 0+1+2 补丁：正名、内容寻址文件名、gzip 压缩。"""
from pathlib import Path
import io, re, sys

BASE = Path(r"F:\workspace\quiz_py")
APP = BASE / "gui" / "static" / "app.js"
HTML = BASE / "gui" / "static" / "index.html"

s = APP.read_text(encoding="utf-8")
orig = s
changes = []


def rep(old, new, count=1, label=""):
    global s
    n = s.count(old)
    assert n == count, f"{label}: 期望 {count} 处，实际 {n} 处\n{old[:200]}"
    s = s.replace(old, new, count)
    changes.append(label)


# ---------- R1 文件名规则 ----------
old = r"const WEBDAV_BACKUP_FILE_RE_V378=/^shiroha-web-backup-(\d{8})-(\d{6})-([a-f0-9]{8})\.json$/i;"
new = (
    r"const WEBDAV_BACKUP_FILE_RE_V378=/^shiroha-web-([a-f0-9]{12})\.json(\.gz)?$/i;"
    "\n"
    r"const WEBDAV_LEGACY_FILE_RE_V378=/^shiroha-web-backup-(\d{8})-(\d{6})-([a-f0-9]{8})\.json$/i;"
    "\n"
    "function isWebdavBackupNameV378(name){const n=String(name||'');return WEBDAV_BACKUP_FILE_RE_V378.test(n)||WEBDAV_LEGACY_FILE_RE_V378.test(n)}"
)
rep(old, new, 1, "R1 文件名正则")

# ---------- R2 旧名日期解析 ----------
rep(
    r"const m=String(fileName||'').match(WEBDAV_BACKUP_FILE_RE_V378);if(!m)return '';",
    r"const m=String(fileName||'').match(WEBDAV_LEGACY_FILE_RE_V378);if(!m)return '';",
    1,
    "R2 旧名日期解析",
)

# ---------- R3 列表过滤（两处） ----------
rep(
    r"if(!WEBDAV_BACKUP_FILE_RE_V378.test(fileName))return;",
    r"if(!isWebdavBackupNameV378(fileName))return;",
    2,
    "R3 列表过滤",
)

# ---------- R4 latest.json 校验 ----------
rep(
    r"if(manifest&&WEBDAV_BACKUP_FILE_RE_V378.test(String(manifest.fileName||'')))",
    r"if(manifest&&isWebdavBackupNameV378(manifest.fileName))",
    1,
    "R4 latest 校验",
)

# ---------- R5 恢复入口校验 ----------
rep(
    r"if(!WEBDAV_BACKUP_FILE_RE_V378.test(String(fileName||'')))throw webdavErrorV378('远程文件名不符合 Shiroha Quiz 备份规则。',{code:'invalid_file'});",
    r"if(!isWebdavBackupNameV378(fileName))throw webdavErrorV378('远程文件名不符合 Shiroha Quiz 备份规则。',{code:'invalid_file'});",
    1,
    "R5 恢复入口校验",
)

# ---------- R6 恢复：支持 .gz + 新旧哈希位宽 ----------
old6 = (
    "  const bytes=new Uint8Array(await response.arrayBuffer()),sha=await sha256HexV378(bytes),"
    "expected=String(fileName).match(WEBDAV_BACKUP_FILE_RE_V378)[3].toLowerCase();"
    "if(sha.slice(0,8)!==expected)throw webdavErrorV378('备份文件 SHA-256 与文件名不一致，已停止恢复。',"
    "{code:'sha_mismatch',method:'GET',url:webdavUrlV378(config,remoteDir+'/'+fileName)});"
)
new6 = (
    "  let rawBytes=new Uint8Array(await response.arrayBuffer());"
    "if(/\\.gz$/i.test(fileName))rawBytes=await gunzipBytesV378(rawBytes);"
    "const bytes=rawBytes,sha=await sha256HexV378(bytes),"
    "newMatch=String(fileName).match(WEBDAV_BACKUP_FILE_RE_V378),"
    "legacyMatch=String(fileName).match(WEBDAV_LEGACY_FILE_RE_V378),"
    "expected=(newMatch?String(newMatch[1]):String((legacyMatch||[])[3]||'')).toLowerCase();"
    "if(!expected||sha.slice(0,expected.length)!==expected)throw webdavErrorV378('备份文件 SHA-256 与文件名不一致，已停止恢复。',"
    "{code:'sha_mismatch',method:'GET',url:webdavUrlV378(config,remoteDir+'/'+fileName)});"
)
rep(old6, new6, 1, "R6 恢复 .gz 与哈希校验")

# ---------- R7 上传函数整体替换 ----------
i = s.find("async function uploadWebdavBackupV378")
j = s.find("function setWebdavAutoStatusV379")
assert i > 0 and j > i, "定位上传函数失败"

helpers = '''async function gzipBytesV378(bytes){
  if(typeof CompressionStream!=='function')return null;
  try{const stream=new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'));return new Uint8Array(await new Response(stream).arrayBuffer())}catch(_){return null}
}
async function gunzipBytesV378(bytes){
  if(typeof DecompressionStream!=='function')throw webdavErrorV378('当前浏览器不支持解压 gzip 备份，请升级浏览器后再恢复。',{code:'decompress_unavailable'});
  try{const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));return new Uint8Array(await new Response(stream).arrayBuffer())}catch(error){throw webdavErrorV378('备份文件解压失败，可能已损坏：'+(error&&error.message?error.message:String(error)),{code:'decompress_failed'})}
}
async function webdavFileExistsV378(config,password,relativePath){
  const head=await webdavRequestV378(config,password,relativePath,{method:'HEAD',acceptStatuses:[200,204,404,405,501]});
  if(head.status===200||head.status===204)return true;
  if(head.status===404)return false;
  const prop=await webdavRequestV378(config,password,relativePath,{method:'PROPFIND',headers:{Depth:'0','Content-Type':'application/xml; charset=utf-8'},body:'<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/></d:prop></d:propfind>',acceptStatuses:[200,207,404]});
  return prop.status===200||prop.status===207;
}
'''

upload = '''async function uploadWebdavBackupV378(autoMode){
  const config=autoMode?readWebdavConfigV378():webdavConfigFromFormV378();
  const password=autoMode?readWebdavPasswordV378(config):webdavPasswordFromFormV378();
  if(autoMode&&(!config.autoSync||!config.endpoint||!password))return {skipped:true,reason:'auto-off'};
  let text;try{text=JSON.stringify(buildBackupPayloadV23(state.banks||[],'all_data',true))}catch(error){if(typeof isStringTooLargeErrorV376==='function'&&isStringTooLargeErrorV376(error))throw webdavErrorV378('当前完整备份过大，浏览器无法生成上传文本。请先减少大图片或拆分成多个题库。',{code:'payload_too_large'});throw error}
  const bytes=new TextEncoder().encode(text),sha=await sha256HexV378(bytes);
  if(autoMode&&config.lastUploadSha===sha){setWebdavAutoStatusV379('数据没有变化，本次自动备份跳过。');return {skipped:true,reason:'unchanged'}}
  const remoteDir=normalizeWebdavRemoteDirV378(config.remoteDir);
  const gz=await gzipBytesV378(bytes),payloadBytes=gz||bytes;
  const fileName=`shiroha-web-${sha.slice(0,12)}.json${gz?'.gz':''}`,filePath=remoteDir+'/'+fileName;
  await ensureWebdavDirectoryV378(config,password);
  let reused=false;
  try{reused=await webdavFileExistsV378(config,password,filePath)}catch(error){reused=false;setWebdavDiagnosticV378('探测远端是否已存在',error)}
  let fileResponse=null;
  if(!reused)fileResponse=await webdavRequestV378(config,password,filePath,{method:'PUT',headers:{'Content-Type':gz?'application/gzip':'application/json; charset=utf-8'},body:payloadBytes,timeoutMs:120000,acceptStatuses:[200,201,204]});
  const questionCount=(state.banks||[]).reduce((n,b)=>n+(b.questions||[]).length,0),manifest={kind:'shiroha_quiz_webdav_latest',version:2,app:'Shiroha Quiz',appVersion:APP_VERSION,updatedAt:now(),fileName,sha256:sha,sizeBytes:payloadBytes.byteLength,rawSizeBytes:bytes.byteLength,gzip:!!gz,reused,bankCount:(state.banks||[]).length,questionCount};
  let manifestWarning='';try{await webdavRequestV378(config,password,remoteDir+'/latest.json',{method:'PUT',headers:{'Content-Type':'application/json; charset=utf-8'},body:JSON.stringify(manifest),acceptStatuses:[200,201,204]})}catch(error){manifestWarning='；备份文件已上传，但 latest.json 更新失败';setWebdavDiagnosticV378('更新 latest.json',error)}
  const saved={...config,lastUploadAt:manifest.updatedAt,lastUploadFile:fileName,lastUploadSize:payloadBytes.byteLength,lastUploadSha:sha,lastAutoAt:autoMode?manifest.updatedAt:(config.lastAutoAt||''),lastAutoResult:autoMode?('成功：'+fileName):(config.lastAutoResult||'')};storeWebdavConfigV378(saved,password);
  try{await loadWebdavBackupListV378(config,password)}catch(error){manifestWarning+='；远程列表刷新失败';setWebdavDiagnosticV378('刷新列表',error)}
  if(!manifestWarning)setWebdavDiagnosticV378(reused?'跳过上传':'上传备份',null,{method:reused?'HEAD':'PUT',url:webdavUrlV378(config,filePath),status:reused?200:(fileResponse?fileResponse.status:0),summary:reused?'远端已有同内容文件，本次未传输数据。':'完整备份及 latest.json 已上传。'});
  const sizeText=formatBytesV376(payloadBytes.byteLength)+(gz?'（压前 '+formatBytesV376(bytes.byteLength)+'）':'');
  if(autoMode){setWebdavAutoStatusV379(`自动备份完成：${fileName}（${sizeText}）${reused?'·远端已存在，未重复传输':''}${manifestWarning}`,manifestWarning?'warn':'ok');return {ok:true,fileName,warning:manifestWarning,reused}}
  setWebdavStatusV378(`上传成功：${fileName}（${sizeText}）${reused?'·远端已存在同内容，未重复传输':''}${manifestWarning}`,manifestWarning?'warn':'ok');toast(manifestWarning?'备份已上传，但索引或列表更新不完整。':(reused?'远端已有相同内容，本次未重复上传。':'WebDAV 完整备份上传成功。'),manifestWarning?'warn':'ok');
  return {ok:true,fileName,warning:manifestWarning,reused};
}

'''

s = s[:i] + helpers + upload + s[j:]
changes.append("R7 上传函数（内容寻址 + gzip + HEAD 去重）")

# ---------- R8 正名：自动同步 → 自动备份 ----------
n_rename = s.count("自动同步")
s = s.replace("自动同步", "自动备份")
changes.append(f"R8 正名 自动同步→自动备份（{n_rename} 处）")

# ---------- R9 版本号 ----------
old9 = "const APP_VERSION='V38：单题AI解析与追问版';"
assert old9 in s, "APP_VERSION 未找到"
s = s.replace(old9, "const APP_VERSION='V39：云备份内容寻址版';", 1)
changes.append("R9 APP_VERSION")

assert s != orig
APP.write_text(s, encoding="utf-8")

# ---------- 页面资源版本 ----------
h = HTML.read_text(encoding="utf-8")
assert "app.js?v=15" in h, "app.js?v=15 未找到"
h = h.replace("app.js?v=15", "app.js?v=16", 1)
HTML.write_text(h, encoding="utf-8")

print("OK")
for c in changes:
    print(" -", c)
print("app.js 行数:", s.count("\n") + 1)
