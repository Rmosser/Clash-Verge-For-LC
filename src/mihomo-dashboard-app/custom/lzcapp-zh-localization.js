;(function () {
  "use strict";

  var FORCE_LANG = "zh";
  var COOKIE_KEY = "metacubexd_lang";
  var RELOAD_GUARD_KEY = "lzc_zh_reload_once";

  // Remaining non-i18n literals in upstream bundles.
  var TEXT_MAP = {
    "Mihomo Dashboard, The Official One": "Mihomo 官方控制面板",
    "Ready to connect": "等待连接后端",
    "Language": "语言",
    "Theme": "主题",
    "open sidebar": "打开侧边栏",
    "close sidebar": "关闭侧边栏",
    "Mobile bottom navigation": "移动端底部导航",
    "Press a key...": "按下按键...",
    "customized": "已自定义",
    "Apply anyway": "仍然应用",
    "Reset to Defaults": "恢复默认",
    "Smart Recommendation": "智能推荐",
    "No score yet": "暂无评分",
  };

  var ATTR_MAP = {
    "Navigate to": "前往",
    "Change language": "切换语言",
  };

  function setLangStorage() {
    try {
      localStorage.setItem("lang", FORCE_LANG);
      localStorage.setItem(COOKIE_KEY, FORCE_LANG);
    } catch (_e) {}

    try {
      document.cookie = COOKIE_KEY + "=" + FORCE_LANG + "; path=/; max-age=" + 60 * 60 * 24 * 365;
    } catch (_e) {}

    if (document.documentElement) {
      document.documentElement.lang = "zh-CN";
    }
  }

  function maybeReloadForLang() {
    try {
      var current = localStorage.getItem(COOKIE_KEY) || localStorage.getItem("lang") || "";
      var guard = sessionStorage.getItem(RELOAD_GUARD_KEY);
      if (current !== FORCE_LANG && guard !== "1") {
        sessionStorage.setItem(RELOAD_GUARD_KEY, "1");
        setLangStorage();
        location.reload();
        return true;
      }
    } catch (_e) {}
    return false;
  }

  function cleanTextValue(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function replaceExact(text) {
    var clean = cleanTextValue(text);
    if (!clean) return text;
    if (Object.prototype.hasOwnProperty.call(TEXT_MAP, clean)) {
      return text.replace(clean, TEXT_MAP[clean]);
    }
    return text;
  }

  function replaceAttr(value) {
    var out = String(value || "");
    Object.keys(ATTR_MAP).forEach(function (k) {
      if (out.indexOf(k) >= 0) {
        out = out.replace(new RegExp(k, "g"), ATTR_MAP[k]);
      }
    });
    return out;
  }

  function getNodeType(node) {
    try {
      if (!node || typeof node.nodeType !== "number") return 0;
      return node.nodeType;
    } catch (_e) {
      return 0;
    }
  }

  function isTraversableNode(node) {
    var nodeType = getNodeType(node);
    return nodeType === 1 || nodeType === 9 || nodeType === 11;
  }

  function translateTextNodes(root) {
    if (!isTraversableNode(root)) return;

    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node || !node.parentNode) return NodeFilter.FILTER_REJECT;
        var p = node.parentNode;
        var tag = p.nodeName;
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT") return NodeFilter.FILTER_REJECT;
        if (!cleanTextValue(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    var node;
    while ((node = walker.nextNode())) {
      var replaced = replaceExact(node.nodeValue);
      if (replaced !== node.nodeValue) {
        node.nodeValue = replaced;
      }
    }
  }

  function translateAttrs(root) {
    if (!root || !root.querySelectorAll) return;

    var nodes = root.querySelectorAll("[title],[aria-label],[placeholder]");
    for (var i = 0; i < nodes.length; i += 1) {
      var el = nodes[i];
      ["title", "aria-label", "placeholder"].forEach(function (attr) {
        var val = el.getAttribute(attr);
        if (!val) return;
        var next = replaceAttr(val);
        if (next !== val) el.setAttribute(attr, next);
      });
    }
  }

  function translate(root) {
    try {
      var rootType = getNodeType(root);
      if (!rootType) return;

      var target = root;
      if (rootType === 3) {
        target = root.parentNode;
      }

      var targetType = getNodeType(target);
      if (targetType !== 1 && targetType !== 9 && targetType !== 11) return;

      translateTextNodes(target);
      translateAttrs(targetType === 1 ? target : document);
    } catch (_e) {}
  }

  function startObserver() {
    var obs = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i += 1) {
        try {
          var m = mutations[i];
          if (m.type === "childList") {
            for (var j = 0; j < m.addedNodes.length; j += 1) {
              var n = m.addedNodes[j];
              var nType = getNodeType(n);
              if (nType === 1 || nType === 3 || nType === 11) {
                var target = nType === 3 ? n.parentNode : n;
                if (target) {
                  translate(target);
                }
              }
            }
          } else if (m.type === "characterData") {
            var parent = m.target && m.target.parentNode;
            if (parent) {
              translate(parent);
            }
          }
        } catch (_e) {}
      }
    });

    obs.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  function boot() {
    if (maybeReloadForLang()) return;
    setLangStorage();
    translate(document.body || document.documentElement);
    startObserver();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
