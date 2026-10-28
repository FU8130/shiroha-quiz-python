/* 练习设置记忆：记住上次选的题型/来源/顺序/起点/题量（含自定义数量）与考试题量。
   数据走 bridge 的 localStorage 劫持，最终存到项目内 state.json 的 gui 段（便携）。 */
(function () {
  'use strict';
  var KEY = 'quiz_practice_prefs_v1';
  var MAP = [
    ['practice-type', 'type'],
    ['practice-source', 'source'],
    ['practice-order', 'order'],
    ['practice-start-mode-v58916', 'startMode'],
    ['practice-limit', 'limit'],
    ['practice-custom-count', 'customCount'],
    ['practice-number-range-v58916', 'numberRange'],
    ['exam-count', 'examCount'],
    ['wrong-practice-limit', 'wrongLimit'],
    ['wrong-practice-custom-count', 'wrongCustomCount']
  ];

  function load() {
    try {
      var raw = localStorage.getItem(KEY);
      return raw ? (JSON.parse(raw) || {}) : {};
    } catch (e) { return {}; }
  }

  function save(obj) {
    try { localStorage.setItem(KEY, JSON.stringify(obj)); } catch (e) {}
  }

  function fire(el, type) {
    try { el.dispatchEvent(new Event(type, { bubbles: true })); } catch (e) {}
  }

  function restore() {
    var saved = load();
    var has = false;
    for (var k in saved) { has = true; break; }
    if (!has) return;
    var touched = [];
    MAP.forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      if (!el) return;
      var v = saved[pair[1]];
      if (v === undefined || v === null || v === '') return;
      if (el.tagName === 'SELECT') {
        var ok = false;
        for (var i = 0; i < el.options.length; i++) if (el.options[i].value === String(v)) { ok = true; break; }
        if (!ok) return;
      }
      el.value = String(v);
      touched.push(el);
    });
    // 先统一赋值，再触发 change，避免自定义题量被“自定义”联动重置
    touched.forEach(function (el) { fire(el, 'input'); fire(el, 'change'); });
  }

  function bind() {
    MAP.forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      if (!el || el.__practiceMemBound) return;
      el.__practiceMemBound = true;
      var handler = function () {
        var cur = load();
        cur[pair[1]] = el.value;
        save(cur);
      };
      el.addEventListener('change', handler);
      el.addEventListener('input', handler);
    });
  }

  function boot() {
    if (!document.getElementById('practice-type')) return;
    restore();
    bind();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(boot, 60); });
  } else {
    setTimeout(boot, 60);
  }
  // 页面内切换视图后补绑（节点若被重建）
  document.addEventListener('click', function () { setTimeout(bind, 300); }, true);
})();
