# -*- coding: utf-8 -*-
"""阶段 3：远端与本地不一致时，自动备份跳过、手动上传需二次确认。"""
from pathlib import Path

APP = Path(r"F:\workspace\quiz_py") / "gui" / "static" / "app.js"
HTML = Path(r"F:\workspace\quiz_py") / "gui" / "static" / "index.html"

s = APP.read_text(encoding="utf-8")
log = []


def rep(old, new, label):
    global s
    n = s.count(old)
    assert n == 1, f"{label}: 期望 1 处，实际 {n}\n---\n{old[:260]}"
    s = s.replace(old, new, 1)
    log.append(label)


# ---- 1. 配置增加“上次见到的远端指纹/时间” ----
rep(
    "lastUploadSha:'',lastAutoAt:'',lastAutoResult:''}",
    "lastUploadSha:'',lastRemoteSha:'',lastRemoteUpdatedAt:'',lastAutoAt:'',lastAutoResult:''}",
    "默认配置增加 lastRemoteSha / lastRemoteUpdatedAt",
)

# ---- 2. 上传前做冲突判定 ----
old2 = """  const remoteDir=normalizeWebdavRemoteDirV378(config.remoteDir);
  const gz=await gzipBytesV378(bytes),payloadBytes=gz||bytes;"""
new2 = """  const remoteDir=normalizeWebdavRemoteDirV378(config.remoteDir);
  let remoteManifest=null;
  try{const r=await webdavRequestV378(config,password,remoteDir+'/latest.json',{method:'GET',acceptStatuses:[200,404]});if(r.status===200)remoteManifest=JSON.parse(await r.text())}catch(_){remoteManifest=null}
  const remoteSha=remoteManifest?String(remoteManifest.sha256||'').toLowerCase():'',knownRemoteSha=String(config.lastRemoteSha||'').toLowerCase();
  const remoteChanged=!!(remoteManifest&&remoteSha&&remoteSha!==sha&&remoteSha!==knownRemoteSha);
  if(remoteManifest)webdavRuntimeV378.latestManifest=remoteManifest;
  if(remoteChanged){
    const info=`远端最新备份：${remoteManifest.updatedAt?fmt(remoteManifest.updatedAt):'时间未知'}｜${remoteManifest.fileName||'—'}｜${remoteManifest.questionCount||'?'} 道题`;
    if(autoMode){setWebdavAutoStatusV379(`远端备份与本地不同（可能是别的设备传过），已跳过本次自动备份。${info}`,'warn');storeWebdavConfigV378({...config,lastAutoAt:now(),lastAutoResult:'跳过：远端有不同备份'},password);return {skipped:true,reason:'remote-changed',remote:remoteManifest}}
    if(!window.confirm(`远端已经有一份不同的备份，继续上传会把远端最新指针改成本机内容。\\n${info}\\n\\n仍要上传吗？（选“取消”可先在下面列表里下载远端备份看看）`)){setWebdavStatusV378('已取消上传：远端备份与本地不同，可先下载远端备份。','warn');return {skipped:true,reason:'cancelled',remote:remoteManifest}}
  }
  const gz=await gzipBytesV378(bytes),payloadBytes=gz||bytes;"""
rep(old2, new2, "上传前冲突判定（auto 跳过 / 手动确认）")

# ---- 3. 上传成功后记录远端指纹 ----
old3 = "lastUploadSha:sha,lastAutoAt:autoMode?manifest.updatedAt:(config.lastAutoAt||'')"
new3 = "lastUploadSha:sha,lastRemoteSha:sha,lastRemoteUpdatedAt:manifest.updatedAt,lastAutoAt:autoMode?manifest.updatedAt:(config.lastAutoAt||'')"
rep(old3, new3, "成功后记录 lastRemoteSha")

# ---- 4. 面板显示远端最新 ----
old4 = "const summary=$('#webdav-last-summary-v378');if(summary)summary.textContent=config.lastUploadAt?`最近上传：${fmt(config.lastUploadAt)}｜${config.lastUploadFile||'—'}｜${formatBytesV376(config.lastUploadSize||0)}｜SHA-256 ${String(config.lastUploadSha||'').slice(0,12)}…`:'尚无成功上传记录。';"
new4 = ("const summary=$('#webdav-last-summary-v378');if(summary){let text=config.lastUploadAt?`最近上传：${fmt(config.lastUploadAt)}｜${config.lastUploadFile||'—'}｜${formatBytesV376(config.lastUploadSize||0)}｜SHA-256 ${String(config.lastUploadSha||'').slice(0,12)}…`:'尚无成功上传记录。';"
        "const remoteManifest=webdavRuntimeV378.latestManifest;if(remoteManifest&&remoteManifest.updatedAt){const localSha=String(config.lastUploadSha||'').toLowerCase(),remoteSha=String(remoteManifest.sha256||'').toLowerCase();const changed=!!(localSha&&remoteSha&&localSha!==remoteSha);text+=`${text.endsWith('。')?'':'｜'}远端最新：${fmt(remoteManifest.updatedAt)}（${remoteManifest.fileName||'—'}）${changed?' ⚠ 与本地不同，自动备份会跳过':''}`}summary.textContent=text}")
rep(old4, new4, "面板显示远端最新与不一致提示")

APP.write_text(s, encoding="utf-8")

h = HTML.read_text(encoding="utf-8")
assert "app.js?v=18" in h
h = h.replace("app.js?v=18", "app.js?v=19", 1)
HTML.write_text(h, encoding="utf-8")

print("OK")
for x in log:
    print(" -", x)
