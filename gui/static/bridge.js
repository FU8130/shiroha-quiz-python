/* GUI 桥：把原前端的 localStorage 换成项目的 state.json / gui 段。
 * 约定：GET /api/state 读整份状态；POST /api/state 回写；GET/POST /api/kv 存 UI 偏好。
 * 接口不可用时退回浏览器存储，直接双击打开网页也能用。
 */
(function () {
  'use strict';
  var KEY = 'shiroha_quiz_state_v28_4_c1';
  var real = window.localStorage;
  var cached = null;   // state JSON 字符串
  var kv = {};         // 其余 UI 偏好
  var stateDirty = false;
  var kvDirty = false;
  var stateTimer = null;
  var kvTimer = null;

  function syncGet(url) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false);
      xhr.send(null);
      if (xhr.status >= 200 && xhr.status < 300) return JSON.parse(xhr.responseText);
    } catch (e) {}
    return null;
  }

  function post(url, body) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(body);
      return true;
    } catch (e) { return false; }
  }

  // 用于和 TUI 共享的数据：只保留题库元信息与答题记录，去掉每库全部题目
  function slim(state) {
    var out = {};
    for (var k in state) if (Object.prototype.hasOwnProperty.call(state, k)) out[k] = state[k];
    if (state.banks && typeof state.banks === 'object') {
      out.banks = {};
      for (var bid in state.banks) {
        if (!Object.prototype.hasOwnProperty.call(state.banks, bid)) continue;
        var b = state.banks[bid] || {};
        var nb = {};
        for (var f in b) if (f !== 'questions') nb[f] = b[f];
        out.banks[bid] = nb;
      }
    }
    delete out.questions;
    return out;
  }

  var boot = syncGet('/api/state') || {};
  if (boot && boot.banks) {
    cached = JSON.stringify(boot);
    if (boot.kv && typeof boot.kv === 'object') kv = boot.kv;
  } else {
    cached = real.getItem(KEY);
  }
  var seedKv = syncGet('/api/kv');
  if (seedKv && typeof seedKv === 'object') kv = seedKv;

  function scheduleState() {
    stateDirty = true;
    clearTimeout(stateTimer);
    stateTimer = setTimeout(function () {
      stateDirty = false;
      if (cached == null) return;
      try { if (post('/api/state', JSON.stringify(slim(JSON.parse(cached))))) { try { window.__shirohaAfterStateSave && window.__shirohaAfterStateSave(); } catch (e2) {} } } catch (e) {}
    }, 300);
  }

  function scheduleKv() {
    kvDirty = true;
    clearTimeout(kvTimer);
    kvTimer = setTimeout(function () {
      kvDirty = false;
      post('/api/kv', JSON.stringify(kv));
    }, 500);
  }

  function flushAll() {
    if (stateDirty && cached != null) {
      try { if (post('/api/state', JSON.stringify(slim(JSON.parse(cached))))) { try { window.__shirohaAfterStateSave && window.__shirohaAfterStateSave(); } catch (e2) {} } } catch (e) {}
      stateDirty = false;
    }
    if (kvDirty) { post('/api/kv', JSON.stringify(kv)); kvDirty = false; }
  }

  window.addEventListener('pagehide', flushAll);
  window.addEventListener('beforeunload', flushAll);

  // 只劫持 localStorage 的四个方法，避免影响 sessionStorage
  var proto = Storage.prototype;
  var origGet = proto.getItem, origSet = proto.setItem, origRemove = proto.removeItem, origClear = proto.clear;
  function isLocal(store) { return store === real; }

  proto.getItem = function (k) {
    if (!isLocal(this)) return origGet.call(this, k);
    if (k === KEY) return cached;
    return Object.prototype.hasOwnProperty.call(kv, k) ? kv[k] : null;
  };
  proto.setItem = function (k, v) {
    if (!isLocal(this)) { origSet.call(this, k, v); return; }
    v = String(v);
    if (k === KEY) { cached = v; scheduleState(); return; }
    kv[k] = v; scheduleKv();
  };
  proto.removeItem = function (k) {
    if (!isLocal(this)) { origRemove.call(this, k); return; }
    if (k === KEY) { cached = null; scheduleState(); return; }
    delete kv[k]; scheduleKv();
  };
  proto.clear = function () {
    if (!isLocal(this)) { origClear.call(this); return; }
    cached = null; kv = {}; scheduleState(); scheduleKv();
  };

  // ---- 夜间模式：默认深色；只改“白底/深字”，切回日间会逐项还原 ----
  var marked = [];          // 被临时改过样式的元素
  var MARKER_SEL = '.answered,.current,.done,.favorite,.option.selected';

  function rgbSum(c) {
    var m = (c || '').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    return m ? (+m[1] + +m[2] + +m[3]) : 999;
  }

  function whiteBg(el) {
    var cs = getComputedStyle(el);
    if (rgbSum(cs.backgroundColor) >= 680) return true;   // 平均 >226
    var img = cs.backgroundImage || '';
    var mm = img.match(/rgba?\(\d+,\s*\d+,\s*\d+/g) || [];
    for (var i = 0; i < mm.length; i++) {
      var p = mm[i].match(/\d+/g);
      if (+p[0] + +p[1] + +p[2] >= 680) return true;
    }
    return false;
  }

  function darken(el) {
    if (!el || el.nodeType !== 1) return;
    if (el.__nightDone) return;
    if (el.matches && el.matches(MARKER_SEL)) return;      // 保留答题卡状态色
    var cs = getComputedStyle(el);
    var bg = whiteBg(el);
    var ink = rgbSum(cs.color) < 330;                      // 深色文字
    if (!bg && !ink) return;
    el.__nightOrig = { color: el.style.getPropertyValue('color') };
    if (bg) {
      el.__nightOrig.background = el.style.getPropertyValue('background-color');
      el.__nightOrig.backgroundImage = el.style.getPropertyValue('background-image');
      el.style.setProperty('background-color', '#232527', 'important');
      el.style.setProperty('background-image', 'none', 'important');
    }
    if (ink) el.style.setProperty('color', '#e8e6e3', 'important');
    el.__nightDone = true;
    marked.push(el);
  }

  function darkenTree(root) {
    if (!root || root.nodeType !== 1) return;
    darken(root);
    var kids = root.querySelectorAll('*');
    for (var i = 0; i < kids.length; i++) darken(kids[i]);
  }

  function restoreAll() {
    for (var i = 0; i < marked.length; i++) {
      var el = marked[i], o = el.__nightOrig || {};
      ['color', 'background', 'backgroundImage'].forEach(function (k) {
        if (!(k in o)) return;
        if (o[k]) el.style.setProperty(k === 'background' ? 'background-color' : (k === 'backgroundImage' ? 'background-image' : k), o[k]);
        else el.style.removeProperty(k === 'background' ? 'background-color' : (k === 'backgroundImage' ? 'background-image' : k));
      });
      delete el.__nightDone;
      delete el.__nightOrig;
    }
    marked = [];
  }

  function darkOn() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  }

  function applyNight(on) {
    var root = document.documentElement;
    if (on) root.setAttribute('data-theme', 'dark');
    else root.removeAttribute('data-theme');
    var btn = document.getElementById('night-toggle');
    if (btn) {
      var ico = btn.querySelector('.nt-icon');
      var lab = btn.querySelector('.nt-label');
      if (ico) ico.textContent = on ? '☀️' : '🌙';
      if (lab) lab.textContent = on ? '日间模式' : '夜间模式';
    }
    if (on) darkenTree(document.body);
    else restoreAll();
  }

  function initNight() {
    var on = kv['night_mode'] === undefined ? true : kv['night_mode'] === '1';
    applyNight(on);
    var btn = document.getElementById('night-toggle');
    if (btn) {
      btn.addEventListener('click', function () {
        var next = document.documentElement.getAttribute('data-theme') !== 'dark';
        kv['night_mode'] = next ? '1' : '0';
        applyNight(next);
        scheduleKv();
      });
    }
    // 新插入/重新渲染的节点立即处理（在浏览器绘制前，不会闪白）
    var obs = new MutationObserver(function (records) {
      if (!darkOn()) return;
      for (var i = 0; i < records.length; i++) {
        var r = records[i];
        if (r.type === 'childList') {
          for (var j = 0; j < r.addedNodes.length; j++) darkenTree(r.addedNodes[j]);
        } else if (r.type === 'attributes') {
          darkenTree(r.target);
        }
      }
    });
    obs.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
  }
  // ---- 诊断日志：前端错误 + 夜间白帧观测，交给 /api/log 写系统目录 ----
  var LOG_LAST = {};
  function sendLog(level, msg, ctx) {
    try {
      var key = level + '|' + msg, now = Date.now();
      if (LOG_LAST[key] && now - LOG_LAST[key] < 5000) return;
      LOG_LAST[key] = now;
      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/log', true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(JSON.stringify({ level: level, msg: msg, ctx: ctx || null }));
    } catch (e) {}
  }
  window.addEventListener('error', function (e) {
    sendLog('error', 'js-error: ' + (e.message || ''), {
      src: (e.filename || '') + ':' + (e.lineno || 0) + ':' + (e.colno || 0),
      stack: ((e.error && e.error.stack) || '').slice(0, 800)
    });
  });
  window.addEventListener('unhandledrejection', function (e) {
    sendLog('error', 'unhandled-rejection', { reason: String(e.reason).slice(0, 400) });
  });

  var watchState = {};
  function lum(px) {
    var m = (px || '').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    return m ? (+m[1] + +m[2] + +m[3]) / 3 : 0;
  }
  function watchFlash() {
    if (document.documentElement.getAttribute('data-theme') !== 'dark') { watchState = {}; return; }
    var t = Date.now();
    var nodes = document.querySelectorAll('.option, #practice-nav-v26, #exam-answer-card-v30');
    if (nodes.length > 6) nodes = [].slice.call(nodes, 0, 6);
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i], cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      var white = lum(cs.backgroundColor) > 200 ||
        /rgba?\((2[3-5]\d),\s*(2[3-5]\d),\s*(2[3-5]\d)/.test(cs.backgroundImage || '');
      var key = el.id || (el.className || el.tagName).toString().split(' ')[0];
      if (white) {
        if (!watchState[key]) watchState[key] = t;
        else if (t - watchState[key] > 250) {
          sendLog('warn', 'white-frame: ' + key, { ms: t - watchState[key] });
          watchState[key] = t + 10000;
        }
      } else delete watchState[key];
    }
  }
  (function loopWatch() {
    try { watchFlash(); } catch (e) {}
    requestAnimationFrame(loopWatch);
  })();

  window.__TUI_GUI__ = {
    banks: (boot.banks ? Object.keys(boot.banks).length : 0),
    kvKeys: Object.keys(kv).length,
    reload: function () { flushAll(); location.reload(); }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initNight);
  else initNight();
})();
