;(function () {
  "use strict";

  var STORAGE_KEY = "lzc-subscription-sources-v2";
  var NOTICE_ID = "lzc-dashboard-enhance-notice";
  var SCAN_MODAL_ID = "lzc-dashboard-enhance-scan-modal";
  var STYLE_ID = "lzc-dashboard-enhance-style";
  var MASK_PATCH_ATTR = "data-lzc-mask-patched";
  var APPLY_TIMEOUT_MS = 25000;
  var FALLBACK_SPINNER_MASK =
    "url('data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A//www.w3.org/2000/svg%27%20viewBox%3D%270%200%2024%2024%27%3E%3Ccircle%20cx%3D%274%27%20cy%3D%2712%27%20r%3D%272%27%20fill%3D%27currentColor%27%3E%3Canimate%20attributeName%3D%27opacity%27%20dur%3D%270.75s%27%20values%3D%271%3B0.5%3B1%27%20repeatCount%3D%27indefinite%27%20begin%3D%270%27/%3E%3C/circle%3E%3Ccircle%20cx%3D%2712%27%20cy%3D%2712%27%20r%3D%272%27%20fill%3D%27currentColor%27%3E%3Canimate%20attributeName%3D%27opacity%27%20dur%3D%270.75s%27%20values%3D%271%3B0.5%3B1%27%20repeatCount%3D%27indefinite%27%20begin%3D%270.15s%27/%3E%3C/circle%3E%3Ccircle%20cx%3D%2720%27%20cy%3D%2712%27%20r%3D%272%27%20fill%3D%27currentColor%27%3E%3Canimate%20attributeName%3D%27opacity%27%20dur%3D%270.75s%27%20values%3D%271%3B0.5%3B1%27%20repeatCount%3D%27indefinite%27%20begin%3D%270.3s%27/%3E%3C/circle%3E%3C/svg%3E')";

  var I18N = {
    zh: {
      loadLocalFile: "加载本地文件",
      localLoaded: "本地配置已加载",
      localLoadFailed: "加载本地配置失败",
      loading: "加载中...",
      providerName: "机场名称",
      groupName: "分组",
      defaultGroup: "默认",
      saveSource: "保存订阅",
      updateHint: "同名机场会自动覆盖更新",
      selectSource: "已保存订阅",
      fillInput: "填入输入框",
      applyNow: "拉取并应用",
      enhancedFetch: "增强拉取",
      deleteSource: "删除",
      noSource: "暂无保存的订阅源",
      savedOk: "订阅已保存（同名已覆盖）",
      deletedOk: "订阅已删除",
      requiredName: "请先填写机场名称",
      requiredUrl: "请先填写订阅链接",
      selectFirst: "请先选择一个订阅",
      blockedTip: "如远程拉取返回 403，可先在本机下载 YAML 再点“加载本地文件”导入。",
      remoteFetchWarning:
        "默认远程订阅由 Mihomo 核心拉取（避免浏览器跨域限制）；“增强拉取”会通过同源代理拉取后上传配置。若订阅方拦截代理/VPN，核心拉取可能返回 403。",
      applySuccess: "远程订阅拉取并应用成功",
      applyFailed: "远程订阅拉取失败",
      apply403: "订阅源返回 403，疑似拦截代理/VPN 来源。建议本地下载 YAML 后使用“加载本地文件”导入。",
      applyHttp: "远程订阅返回错误",
      applyTimeout: "远程订阅请求超时，请检查网络后重试。",
      applyNetwork: "网络不可达、跨域受限或证书异常，无法拉取远程订阅。",
      scanQr: "扫码导入",
      scanTitle: "扫码获取订阅链接",
      scanClose: "关闭",
      scanStart: "启动摄像头",
      scanPermissionDenied: "摄像头权限被拒绝，请在浏览器允许权限后重试。",
      scanUnavailable: "当前浏览器不支持摄像头扫码，请改用“加载本地文件”。",
      scanNoCamera: "未检测到可用摄像头设备。",
      scanParseFailed: "二维码不含可识别订阅链接（需为 https://... 或 clash://install-config?url=...）。",
      scanSuccess: "扫码成功，已填入订阅链接",
      scanHint: "将二维码放入取景区域，识别成功后自动填入。",
      sourceTypeManual: "手动",
      sourceTypeQr: "扫码",
      sourceLabelPrefix: "来源",
    },
    en: {
      loadLocalFile: "Load Local File",
      localLoaded: "Local config loaded",
      localLoadFailed: "Failed to load local config",
      loading: "Loading...",
      providerName: "Provider",
      groupName: "Group",
      defaultGroup: "Default",
      saveSource: "Save Source",
      updateHint: "Same provider name overwrites existing entry",
      selectSource: "Saved subscriptions",
      fillInput: "Fill Input",
      applyNow: "Fetch & Apply",
      enhancedFetch: "Enhanced Fetch",
      deleteSource: "Delete",
      noSource: "No saved subscriptions",
      savedOk: "Saved subscription (updated if same provider)",
      deletedOk: "Deleted subscription",
      requiredName: "Provider name is required",
      requiredUrl: "Subscription URL is required",
      selectFirst: "Please select a source",
      blockedTip: "If remote fetch returns 403, download YAML locally and import with Load Local File.",
      remoteFetchWarning:
        "Default remote subscription fetch is handled by Mihomo core (avoids browser CORS). Enhanced Fetch pulls via same-origin proxy and uploads the config. If provider blocks proxy/VPN, core fetch may return 403.",
      applySuccess: "Remote subscription fetched and applied",
      applyFailed: "Failed to fetch remote subscription",
      apply403: "Subscription returned HTTP 403 and likely blocks proxy/VPN origin. Download YAML locally and import it.",
      applyHttp: "Remote subscription returned an HTTP error",
      applyTimeout: "Remote subscription request timed out.",
      applyNetwork: "Network/CORS/TLS error blocked remote subscription fetch.",
      scanQr: "Scan QR",
      scanTitle: "Scan subscription QR",
      scanClose: "Close",
      scanStart: "Start Camera",
      scanPermissionDenied: "Camera permission denied. Please allow camera access and retry.",
      scanUnavailable: "Camera QR scanning is not supported in this browser. Use local file import instead.",
      scanNoCamera: "No camera device available.",
      scanParseFailed: "QR content does not contain a valid subscription URL.",
      scanSuccess: "QR decoded and URL filled",
      scanHint: "Put the QR code inside the frame. It fills automatically after detection.",
      sourceTypeManual: "manual",
      sourceTypeQr: "qr",
      sourceLabelPrefix: "source",
    },
  };

  function getLang() {
    var htmlLang = (document.documentElement && document.documentElement.lang) || "";
    var localLang = "";
    try {
      localLang = localStorage.getItem("lang") || "";
    } catch (_e) {}
    return (htmlLang || localLang || navigator.language || "").toLowerCase();
  }

  function isZh() {
    return getLang().indexOf("zh") === 0;
  }

  function t(key) {
    return (isZh() ? I18N.zh : I18N.en)[key] || key;
  }

  function isConfigRoute() {
    var route = (location.hash || "") + " " + (location.pathname || "");
    return /config/i.test(route);
  }

  function isRemoteConfigForm(form) {
    var urlInput = form.querySelector("input[type='url']");
    var submitBtn = form.querySelector("button[type='submit']");
    if (!urlInput || !submitBtn) return false;

    var text = (submitBtn.textContent || "").toLowerCase();
    if (text.indexOf("remote") >= 0) return true;
    if (text.indexOf("拉取远程配置") >= 0) return true;
    if (text.indexOf("配置") >= 0 && text.indexOf("拉取") >= 0) return true;
    return false;
  }

  function findSecretFromStorage() {
    try {
      var list = JSON.parse(localStorage.getItem("endpointList") || "[]");
      var selectedId = localStorage.getItem("selectedEndpoint") || "";
      if (!Array.isArray(list) || !selectedId) return "";
      for (var i = 0; i < list.length; i += 1) {
        var item = list[i];
        if (item && item.id === selectedId && item.secret) return String(item.secret);
      }
    } catch (_e) {}
    return "";
  }

  function findSecret() {
    var fromStorage = findSecretFromStorage();
    if (fromStorage) return fromStorage;
    var fromConfig = window.__LZCAPP_MIHOMO__ && window.__LZCAPP_MIHOMO__.secret;
    return fromConfig ? String(fromConfig) : "";
  }

  function showNotice(root, msg, ok) {
    var old = document.getElementById(NOTICE_ID);
    if (old && old.parentNode) old.parentNode.removeChild(old);

    var node = document.createElement("div");
    node.id = NOTICE_ID;
    node.textContent = msg;
    node.style.marginTop = "8px";
    node.style.fontSize = "12px";
    node.style.opacity = "0.92";
    node.style.lineHeight = "1.45";
    node.style.whiteSpace = "pre-wrap";
    node.style.color = ok ? "var(--color-success, #16a34a)" : "var(--color-error, #ef4444)";

    var target = root && root.appendChild ? root : document.body || document.documentElement;
    if (!target) return;
    target.appendChild(node);
    setTimeout(function () {
      var curr = document.getElementById(NOTICE_ID);
      if (curr && curr.parentNode) curr.parentNode.removeChild(curr);
    }, 9000);
  }

  function triggerInput(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function normalizeName(name) {
    return String(name || "").trim().toLowerCase();
  }

  function nowTs() {
    return Date.now();
  }

  function readSources() {
    try {
      var data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      if (!Array.isArray(data)) return [];
      return data
        .filter(function (x) {
          return x && x.name && x.url;
        })
        .map(function (x) {
          return {
            id: String(x.id || ""),
            name: String(x.name || "").trim(),
            group: String(x.group || t("defaultGroup")).trim() || t("defaultGroup"),
            url: String(x.url || "").trim(),
            sourceType: x.sourceType === "qr" ? "qr" : "manual",
            updatedAt: Number(x.updatedAt || nowTs()),
            lastResult: x.lastResult === "failed" ? "failed" : x.lastResult === "ok" ? "ok" : "",
            lastErrorAt: Number(x.lastErrorAt || 0),
          };
        })
        .sort(function (a, b) {
          return b.updatedAt - a.updatedAt;
        });
    } catch (_e) {
      return [];
    }
  }

  function writeSources(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items || []));
  }

  function getById(items, id) {
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].id === id) return items[i];
    }
    return null;
  }

  function withFetchResult(items, id, result) {
    if (!id) return items;
    return items.map(function (x) {
      if (x.id !== id) return x;
      return {
        id: x.id,
        name: x.name,
        group: x.group,
        url: x.url,
        sourceType: x.sourceType,
        updatedAt: x.updatedAt,
        lastResult: result === "ok" ? "ok" : "failed",
        lastErrorAt: result === "ok" ? 0 : nowTs(),
      };
    });
  }

  function upsertSource(items, source) {
    var target = normalizeName(source.name);
    var next = items.slice();
    var found = -1;

    for (var i = 0; i < next.length; i += 1) {
      if (normalizeName(next[i].name) === target) {
        found = i;
        break;
      }
    }

    if (found >= 0) {
      var old = next[found];
      next[found] = {
        id: old.id || source.id,
        name: source.name,
        group: source.group,
        url: source.url,
        sourceType: source.sourceType || old.sourceType || "manual",
        updatedAt: nowTs(),
        lastResult: old.lastResult || "",
        lastErrorAt: old.lastErrorAt || 0,
      };
      return next;
    }

    next.unshift({
      id: source.id,
      name: source.name,
      group: source.group,
      url: source.url,
      sourceType: source.sourceType || "manual",
      updatedAt: nowTs(),
      lastResult: "",
      lastErrorAt: 0,
    });
    return next;
  }

  function groupItems(items) {
    var groups = {};
    for (var i = 0; i < items.length; i += 1) {
      var item = items[i];
      var group = item.group || t("defaultGroup");
      if (!groups[group]) groups[group] = [];
      groups[group].push(item);
    }
    return groups;
  }

  function maskUrl(url) {
    try {
      var u = new URL(url);
      return u.origin + u.pathname;
    } catch (_e) {
      return url.length > 60 ? url.slice(0, 57) + "..." : url;
    }
  }

  function sourceStateMark(source) {
    if (!source || !source.lastResult) return "";
    return source.lastResult === "ok" ? "[OK]" : "[ERR]";
  }

  function renderSourceOptions(selectEl, items) {
    selectEl.innerHTML = "";

    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = t("noSource");
    selectEl.appendChild(placeholder);

    if (!items.length) return;

    var grouped = groupItems(items);
    var names = Object.keys(grouped).sort();
    for (var i = 0; i < names.length; i += 1) {
      var g = names[i];
      var optGroup = document.createElement("optgroup");
      optGroup.label = g;
      var list = grouped[g];

      for (var j = 0; j < list.length; j += 1) {
        var s = list[j];
        var opt = document.createElement("option");
        var sourceLabel = s.sourceType === "qr" ? t("sourceTypeQr") : t("sourceTypeManual");
        opt.value = s.id;
        opt.textContent =
          sourceStateMark(s) + " " + s.name + " - " + maskUrl(s.url) + " (" + t("sourceLabelPrefix") + ":" + sourceLabel + ")";
        optGroup.appendChild(opt);
      }

      selectEl.appendChild(optGroup);
    }
  }

  async function uploadConfig(payloadText, secret) {
    var headers = { "Content-Type": "application/json" };
    if (secret) headers.Authorization = "Bearer " + secret;

    var resp = await fetch("/api/configs?force=true", {
      method: "PUT",
      headers: headers,
      body: JSON.stringify({ path: "", payload: payloadText }),
      credentials: "same-origin",
    });

    if (!resp.ok) {
      var body = "";
      try {
        body = await resp.text();
      } catch (_e) {}
      throw { kind: "apply", status: resp.status, body: body };
    }
  }

  function classifyRemoteError(err) {
    if (err && err.kind === "fetch-http") {
      if (err.status === 403) {
        var bodyText = (err.body || "").toLowerCase();
        var blocked =
          bodyText.indexOf("vpn") >= 0 ||
          bodyText.indexOf("代理") >= 0 ||
          bodyText.indexOf("禁止访问") >= 0 ||
          bodyText.indexOf("forbidden") >= 0;
        if (blocked) return t("apply403");
      }
      return t("applyHttp") + " (HTTP " + err.status + ")" + (err.body ? "\n" + String(err.body).slice(0, 180) : "");
    }

    if (err && err.kind === "timeout") return t("applyTimeout");
    if (err && err.kind === "network") return t("applyNetwork");
    if (err && err.kind === "apply") return t("applyHttp") + " (apply HTTP " + err.status + ")";

    return t("applyFailed") + ": " + (err && err.message ? err.message : String(err || "unknown"));
  }

  async function fetchRemoteTextViaProxy(url) {
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, APPLY_TIMEOUT_MS);

    try {
      var proxyUrl = "/fetch/?url=" + encodeURIComponent(String(url || ""));
      var resp = await fetch(proxyUrl, {
        method: "GET",
        redirect: "follow",
        cache: "no-store",
        signal: controller.signal,
      });

      var body = await resp.text();
      if (!resp.ok) {
        throw {
          kind: "fetch-http",
          status: resp.status,
          body: body,
        };
      }
      return body;
    } catch (err) {
      if (err && err.name === "AbortError") throw { kind: "timeout", message: "timeout" };
      if (err && err.kind) throw err;
      throw { kind: "network", message: err && err.message ? err.message : "network error" };
    } finally {
      clearTimeout(timer);
    }
  }

  function ensureLine(text, pattern, lineToInsert, anchorPattern) {
    if (pattern.test(text)) return { text: text, changed: false };
    var m = text.match(anchorPattern);
    if (!m || m.index == null) return { text: text + "\n" + lineToInsert + "\n", changed: true };
    var idx = m.index + m[0].length;
    return { text: text.slice(0, idx) + "\n" + lineToInsert + text.slice(idx), changed: true };
  }

  function patchFetchedMihomoConfig(payloadText, secret) {
    var text = String(payloadText || "");
    if (!text.trim()) return text;

    // Keep dashboard reachability stable.
    text = text.replace(/^[ \t]*external-controller:[^\n]*$/m, "external-controller: 172.18.0.1:9090");
    // Don't expose proxy port to LAN by accident.
    text = text.replace(/^[ \t]*allow-lan:[^\n]*$/m, "allow-lan: false");
    text = text.replace(/^[ \t]*bind-address:[^\n]*$/m, "bind-address: 127.0.0.1");

    if (secret) {
      if (/^[ \t]*secret:/m.test(text)) {
        text = text.replace(/^[ \t]*secret:[^\n]*$/m, "secret: '" + String(secret).replace(/'/g, "''") + "'");
      } else {
        // Insert after external-controller if missing.
        var out = ensureLine(
          text,
          /^[ \t]*secret:/m,
          "secret: '" + String(secret).replace(/'/g, "''") + "'",
          /^[ \t]*external-controller:[^\n]*$/m
        );
        text = out.text;
      }
    }

    // Ensure TUN block exists; keep it conservative and aligned with repo defaults.
    if (!/^[ \t]*tun:\s*$/m.test(text)) {
      var anchor = /^[ \t]*secret:[^\n]*$/m;
      var tunBlock =
        "\n" +
        "tun:\n" +
        "  enable: true\n" +
        "  stack: system\n" +
        "  auto-route: true\n" +
        "  auto-detect-interface: true\n" +
        "  strict-route: true\n" +
        "  route-exclude-address:\n" +
        "    - 6.6.6.6/32\n" +
        "    - 127.0.0.0/8\n" +
        "    - 10.0.0.0/8\n" +
        "    - 172.16.0.0/12\n" +
        "    - 192.168.0.0/16\n" +
        "    - 169.254.0.0/16\n" +
        "    - 100.64.0.0/10\n" +
        "    - 224.0.0.0/4\n" +
        "    - 255.255.255.255/32\n" +
        "    - ::1/128\n" +
        "    - 2000::6666/128\n" +
        "    - fc00::/7\n" +
        "    - fe80::/10\n" +
        "    - ff00::/8\n" +
        "    - fc03:1136:3800::/40\n";

      var m = text.match(anchor);
      if (m && m.index != null) {
        var idx2 = m.index + m[0].length;
        text = text.slice(0, idx2) + tunBlock + text.slice(idx2);
      } else {
        text = text + tunBlock;
      }
    } else {
      // Ensure required excludes remain present.
      var required = ["6.6.6.6/32", "2000::6666/128", "fc03:1136:3800::/40"];
      var lines = text.split("\n");
      var tunIdx = -1;
      for (var i = 0; i < lines.length; i += 1) {
        if (lines[i] === "tun:") {
          tunIdx = i;
          break;
        }
      }
      if (tunIdx >= 0) {
        var routeIdx = -1;
        for (var j = tunIdx + 1; j < lines.length; j += 1) {
          if (/^[^\s].+:\s*$/.test(lines[j])) break;
          if (lines[j] === "  route-exclude-address:") {
            routeIdx = j;
            break;
          }
        }
        if (routeIdx >= 0) {
          var existing = {};
          var k = routeIdx + 1;
          for (; k < lines.length; k += 1) {
            if (!/^    - /.test(lines[k])) break;
            existing[String(lines[k]).replace(/^    - /, "")] = true;
          }
          var inserts = [];
          for (var r = 0; r < required.length; r += 1) {
            if (!existing[required[r]]) inserts.push("    - " + required[r]);
          }
          if (inserts.length) {
            lines.splice(k, 0, ...inserts);
            text = lines.join("\n");
          }
        }
      }
    }

    // Fail-fast on IPv6 destinations for V4-only egress proxy sets (prevents UI "hangs").
    // This can be removed later once you have V6_EGRESS_OK nodes.
    var v6Rule = "- IP-CIDR6,::/0,REJECT,no-resolve";
    if (text.indexOf(v6Rule) < 0) {
      var lines2 = text.split("\n");
      var insertAt = -1;
      for (var ii = 0; ii < lines2.length; ii += 1) {
        if (lines2[ii] === "- GEOIP,CN,DIRECT") {
          insertAt = ii;
          break;
        }
      }
      if (insertAt < 0) {
        for (var jj = 0; jj < lines2.length; jj += 1) {
          if (lines2[jj] === "- MATCH,PROXY") {
            insertAt = jj;
            break;
          }
        }
      }
      if (insertAt >= 0) {
        lines2.splice(insertAt, 0, v6Rule);
        text = lines2.join("\n");
      }
    }

    if (!/\n$/.test(text)) text += "\n";
    return text;
  }

  async function fetchAndApplyRemoteConfig(url, secret) {
    var payload = await fetchRemoteTextViaProxy(url);
    var patched = patchFetchedMihomoConfig(payload, secret);
    await uploadConfig(patched, secret);
  }

  function createButtonBy(submitBtn, text) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = submitBtn.className;
    btn.textContent = text;
    return btn;
  }

  function ensureEnhanceStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      ".lzc-config-route .lzc-config-form-relaxed {",
      "  min-width: 0;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap {",
      "  margin-top: 10px;",
      "  max-width: 100%;",
      "  min-width: 0;",
      "  overflow: hidden;",
      "  box-sizing: border-box;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-subscription-manager {",
      "  padding: 10px;",
      "  border: 1px solid rgba(148, 163, 184, 0.25);",
      "  border-radius: 10px;",
      "  display: grid;",
      "  gap: 10px;",
      "  min-width: 0;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-subscription-row {",
      "  display: grid;",
      "  grid-template-columns: minmax(0, 1fr) auto;",
      "  gap: 10px;",
      "  align-items: start;",
      "  min-width: 0;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-subscription-fields {",
      "  display: grid;",
      "  grid-template-columns: minmax(220px, 2fr) minmax(120px, 1fr);",
      "  gap: 10px;",
      "  min-width: 0;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-subscription-fields.lzc-subscription-fields-source {",
      "  grid-template-columns: minmax(0, 1fr);",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-subscription-fields input,",
      ".lzc-config-route .lzc-subscription-wrap .lzc-subscription-fields select {",
      "  width: 100%;",
      "  min-width: 0;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-action-group {",
      "  display: flex;",
      "  flex-wrap: wrap;",
      "  justify-content: flex-end;",
      "  align-items: stretch;",
      "  gap: 8px;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-action-group > button {",
      "  min-width: 140px;",
      "  white-space: nowrap;",
      "}",
      ".lzc-config-route .lzc-subscription-wrap .lzc-subscription-tips {",
      "  font-size: 12px;",
      "  opacity: 0.75;",
      "  line-height: 1.45;",
      "}",
      "@media (max-width: 1279px) {",
      "  .lzc-config-route .lzc-subscription-wrap .lzc-subscription-row {",
      "    grid-template-columns: 1fr;",
      "  }",
      "  .lzc-config-route .lzc-subscription-wrap .lzc-action-group {",
      "    display: grid;",
      "    grid-template-columns: repeat(2, minmax(140px, 1fr));",
      "    justify-content: initial;",
      "  }",
      "  .lzc-config-route .lzc-subscription-wrap .lzc-action-group > button {",
      "    width: 100%;",
      "    min-width: 0;",
      "  }",
      "}",
      "@media (max-width: 1023px) {",
      "  .lzc-config-route .lzc-subscription-wrap .lzc-subscription-fields {",
      "    grid-template-columns: 1fr;",
      "  }",
      "}",
      "@media (max-width: 767px) {",
      "  .lzc-config-route .lzc-subscription-wrap .lzc-subscription-manager {",
      "    padding: 8px;",
      "    gap: 8px;",
      "  }",
      "  .lzc-config-route .lzc-subscription-wrap .lzc-action-group {",
      "    grid-template-columns: 1fr;",
      "  }",
      "}",
    ].join("\n");
    (document.head || document.documentElement).appendChild(style);
  }

  function isButtonLikeElement(el) {
    return !!(el && el.tagName && el.tagName.toLowerCase() === "button");
  }

  function isDenseButtonContainer(node) {
    if (!node || !node.children || node.children.length < 3) return false;
    if (node.closest && node.closest(".lzc-subscription-manager")) return false;
    if (node.querySelector("input,select,textarea")) return false;

    var buttonCount = 0;
    var nonButtonCount = 0;
    for (var i = 0; i < node.children.length; i += 1) {
      var child = node.children[i];
      if (isButtonLikeElement(child)) {
        buttonCount += 1;
        continue;
      }
      if (child.children && child.children.length === 1 && isButtonLikeElement(child.children[0])) {
        buttonCount += 1;
        continue;
      }
      nonButtonCount += 1;
    }
    return buttonCount >= 3 && nonButtonCount === 0;
  }

  function markDenseButtonRows(root) {
    if (!root || !root.querySelectorAll) return;

    var nodes = [];
    if (root.nodeType === 1) nodes.push(root);

    var found = root.querySelectorAll("div,section");
    for (var i = 0; i < found.length; i += 1) {
      nodes.push(found[i]);
    }

    for (var j = 0; j < nodes.length; j += 1) {
      var node = nodes[j];
      if (!node.classList || node.classList.contains("lzc-dense-button-row")) continue;
      if (!isDenseButtonContainer(node)) continue;
      node.classList.add("lzc-dense-button-row");
    }
  }

  function parseSubscriptionContent(raw) {
    var text = String(raw || "").trim();
    if (!text) return "";

    if (/^https?:\/\//i.test(text)) return text;

    if (/^clash:\/\//i.test(text)) {
      try {
        var u = new URL(text);
        var q = u.searchParams.get("url") || "";
        if (q) {
          try {
            return decodeURIComponent(q);
          } catch (_e) {
            return q;
          }
        }
      } catch (_e) {}
    }

    var m = text.match(/[?&]url=([^&]+)/i);
    if (m && m[1]) {
      try {
        var decoded = decodeURIComponent(m[1]);
        if (/^https?:\/\//i.test(decoded)) return decoded;
      } catch (_e) {}
    }

    return "";
  }

  function deriveProviderNameFromUrl(url) {
    try {
      var host = new URL(url).hostname;
      return host.replace(/^www\./i, "");
    } catch (_e) {
      return "";
    }
  }

  function ensureScanModal() {
    var old = document.getElementById(SCAN_MODAL_ID);
    if (old) return old;

    var modal = document.createElement("div");
    modal.id = SCAN_MODAL_ID;
    modal.style.position = "fixed";
    modal.style.inset = "0";
    modal.style.background = "rgba(0,0,0,0.6)";
    modal.style.display = "none";
    modal.style.zIndex = "9999";
    modal.style.alignItems = "center";
    modal.style.justifyContent = "center";

    var panel = document.createElement("div");
    panel.style.width = "min(92vw, 560px)";
    panel.style.background = "var(--color-base-200, #0f172a)";
    panel.style.border = "1px solid rgba(148, 163, 184, 0.25)";
    panel.style.borderRadius = "12px";
    panel.style.padding = "12px";
    panel.style.display = "grid";
    panel.style.gap = "8px";

    var head = document.createElement("div");
    head.style.display = "flex";
    head.style.alignItems = "center";
    head.style.justifyContent = "space-between";

    var title = document.createElement("div");
    title.textContent = t("scanTitle");
    title.style.fontWeight = "600";

    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.textContent = t("scanClose");

    closeBtn.style.border = "1px solid rgba(148, 163, 184, 0.25)";
    closeBtn.style.borderRadius = "8px";
    closeBtn.style.background = "transparent";
    closeBtn.style.color = "inherit";
    closeBtn.style.padding = "6px 10px";

    var hint = document.createElement("div");
    hint.textContent = t("scanHint");
    hint.style.fontSize = "12px";
    hint.style.opacity = "0.8";

    var videoWrap = document.createElement("div");
    videoWrap.style.width = "100%";
    videoWrap.style.aspectRatio = "4 / 3";
    videoWrap.style.background = "#111";
    videoWrap.style.borderRadius = "10px";
    videoWrap.style.overflow = "hidden";
    videoWrap.style.position = "relative";

    var video = document.createElement("video");
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;
    video.style.width = "100%";
    video.style.height = "100%";
    video.style.objectFit = "cover";

    var mark = document.createElement("div");
    mark.style.position = "absolute";
    mark.style.inset = "20%";
    mark.style.border = "2px solid rgba(34,197,94,0.9)";
    mark.style.borderRadius = "12px";
    mark.style.pointerEvents = "none";

    videoWrap.appendChild(video);
    videoWrap.appendChild(mark);

    head.appendChild(title);
    head.appendChild(closeBtn);

    panel.appendChild(head);
    panel.appendChild(hint);
    panel.appendChild(videoWrap);
    modal.appendChild(panel);
    document.body.appendChild(modal);

    modal.__video = video;
    modal.__closeBtn = closeBtn;
    modal.__hint = hint;
    return modal;
  }

  function openScanModal() {
    var modal = ensureScanModal();
    modal.style.display = "flex";
    return modal;
  }

  function closeScanModal(modal) {
    if (!modal) return;
    modal.style.display = "none";
  }

  async function scanWithCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw { kind: "scan-unavailable", message: t("scanUnavailable") };
    }

    var modal = openScanModal();
    var video = modal.__video;
    var closeBtn = modal.__closeBtn;

    var stream = null;
    var raf = 0;
    var done = false;
    var detector = null;
    var canvas = document.createElement("canvas");
    var ctx = canvas.getContext("2d", { willReadFrequently: true });

    function stop() {
      done = true;
      if (raf) cancelAnimationFrame(raf);
      if (stream) {
        stream.getTracks().forEach(function (tr) {
          tr.stop();
        });
      }
      closeScanModal(modal);
      closeBtn.onclick = null;
    }

    function loop(resolve, reject) {
      if (done) return;

      var w = video.videoWidth || 0;
      var h = video.videoHeight || 0;
      if (w > 0 && h > 0) {
        try {
          if (detector) {
            detector
              .detect(video)
              .then(function (codes) {
                if (!codes || !codes.length) return;
                var raw = String(codes[0].rawValue || "");
                if (raw) {
                  stop();
                  resolve(raw);
                }
              })
              .catch(function () {});
          } else if (window.jsQR && ctx) {
            canvas.width = w;
            canvas.height = h;
            ctx.drawImage(video, 0, 0, w, h);
            var imageData = ctx.getImageData(0, 0, w, h);
            var qr = window.jsQR(imageData.data, w, h, { inversionAttempts: "dontInvert" });
            if (qr && qr.data) {
              stop();
              resolve(String(qr.data));
              return;
            }
          }
        } catch (_e) {}
      }

      raf = requestAnimationFrame(function () {
        loop(resolve, reject);
      });
    }

    return new Promise(async function (resolve, reject) {
      try {
        if (window.BarcodeDetector) {
          try {
            detector = new window.BarcodeDetector({ formats: ["qr_code"] });
          } catch (_e) {
            detector = null;
          }
        }

        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });

        video.srcObject = stream;
        await video.play();

        closeBtn.onclick = function () {
          stop();
          reject({ kind: "scan-cancel", message: "cancel" });
        };

        if (!detector && !window.jsQR) {
          stop();
          reject({ kind: "scan-unavailable", message: t("scanUnavailable") });
          return;
        }

        loop(resolve, reject);
      } catch (err) {
        stop();
        var msg = String((err && err.message) || "");
        if (/denied|notallowed|permission/i.test(msg)) {
          reject({ kind: "scan-permission", message: t("scanPermissionDenied") });
          return;
        }
        if (/notfound|overconstrained|device/i.test(msg)) {
          reject({ kind: "scan-device", message: t("scanNoCamera") });
          return;
        }
        reject({ kind: "scan-failed", message: msg || t("scanUnavailable") });
      }
    });
  }

  function enhanceForm(form) {
    ensureEnhanceStyles();
    form.classList.add("lzc-config-form-relaxed");
    if (form.dataset.lzcDashboardEnhanced === "1") return;
    form.dataset.lzcDashboardEnhanced = "1";

    var urlInput = form.querySelector("input[type='url']");
    var submitBtn = form.querySelector("button[type='submit']");
    if (!urlInput || !submitBtn) return;

    var localFileInput = document.createElement("input");
    localFileInput.type = "file";
    localFileInput.accept = ".yaml,.yml,.json,.txt,.conf";
    localFileInput.style.display = "none";
    form.appendChild(localFileInput);

    var localBtn = createButtonBy(submitBtn, t("loadLocalFile"));
    localBtn.classList.add("lzc-local-import-btn");
    submitBtn.insertAdjacentElement("afterend", localBtn);

    // Keep subscription UI isolated from upstream form layout to avoid UI breakage.
    var wrap = form.nextElementSibling;
    if (!wrap || !wrap.classList || !wrap.classList.contains("lzc-subscription-wrap")) {
      wrap = document.createElement("div");
      wrap.className = "lzc-subscription-wrap";
      form.insertAdjacentElement("afterend", wrap);
    }

    var manager = document.createElement("div");
    manager.className = "lzc-subscription-manager";

    var row1 = document.createElement("div");
    row1.className = "lzc-subscription-row lzc-subscription-row-meta";

    var row1Fields = document.createElement("div");
    row1Fields.className = "lzc-subscription-fields lzc-subscription-fields-meta";

    var row1Actions = document.createElement("div");
    row1Actions.className = "lzc-action-group lzc-action-group-meta";

    var providerInput = document.createElement("input");
    providerInput.type = "text";
    providerInput.placeholder = t("providerName");
    providerInput.className = urlInput.className;

    var groupInput = document.createElement("input");
    groupInput.type = "text";
    groupInput.placeholder = t("groupName");
    groupInput.className = urlInput.className;

    var saveBtn = createButtonBy(submitBtn, t("saveSource"));
    var scanBtn = createButtonBy(submitBtn, t("scanQr"));

    row1Fields.appendChild(providerInput);
    row1Fields.appendChild(groupInput);
    row1Actions.appendChild(saveBtn);
    row1Actions.appendChild(scanBtn);
    row1.appendChild(row1Fields);
    row1.appendChild(row1Actions);

    var row2 = document.createElement("div");
    row2.className = "lzc-subscription-row lzc-subscription-row-source";

    var row2Fields = document.createElement("div");
    row2Fields.className = "lzc-subscription-fields lzc-subscription-fields-source";

    var row2Actions = document.createElement("div");
    row2Actions.className = "lzc-action-group lzc-action-group-source";

    var sourceSelect = document.createElement("select");
    sourceSelect.className = urlInput.className;
    sourceSelect.title = t("selectSource");

    var fillBtn = createButtonBy(submitBtn, t("fillInput"));
    var applyBtn = createButtonBy(submitBtn, t("applyNow"));
    var enhancedBtn = createButtonBy(submitBtn, t("enhancedFetch"));
    var deleteBtn = createButtonBy(submitBtn, t("deleteSource"));

    row2Fields.appendChild(sourceSelect);
    row2Actions.appendChild(fillBtn);
    row2Actions.appendChild(applyBtn);
    row2Actions.appendChild(enhancedBtn);
    row2Actions.appendChild(deleteBtn);
    row2.appendChild(row2Fields);
    row2.appendChild(row2Actions);

    var tips = document.createElement("div");
    tips.className = "lzc-subscription-tips";
    tips.textContent = t("updateHint") + " " + t("remoteFetchWarning") + " " + t("blockedTip");

    manager.appendChild(row1);
    manager.appendChild(row2);
    manager.appendChild(tips);
    wrap.appendChild(manager);

    function reloadOptions(selectedId) {
      var items = readSources();
      renderSourceOptions(sourceSelect, items);
      if (selectedId) sourceSelect.value = selectedId;
    }

    function getSelectedSource() {
      var id = sourceSelect.value || "";
      if (!id) return null;
      return getById(readSources(), id);
    }

    function resolveSourceForUrl(url) {
      var items = readSources();
      var clean = String(url || "").trim();
      for (var i = 0; i < items.length; i += 1) {
        if (items[i].url === clean) return items[i];
      }
      return null;
    }

    function saveCurrentSource(sourceType) {
      var name = String(providerInput.value || "").trim();
      var url = String(urlInput.value || "").trim();
      var group = String(groupInput.value || "").trim() || t("defaultGroup");

      if (!name) {
        showNotice(wrap, t("requiredName"), false);
        return null;
      }
      if (!url) {
        showNotice(wrap, t("requiredUrl"), false);
        return null;
      }

      var items = readSources();
      var sourceId = "s_" + nowTs() + "_" + Math.floor(Math.random() * 10000);
      var next = upsertSource(items, {
        id: sourceId,
        name: name,
        group: group,
        url: url,
        sourceType: sourceType || "manual",
      });

      next.sort(function (a, b) {
        return b.updatedAt - a.updatedAt;
      });
      writeSources(next);

      var normalized = normalizeName(name);
      var selected = null;
      for (var i = 0; i < next.length; i += 1) {
        if (normalizeName(next[i].name) === normalized) {
          selected = next[i];
          break;
        }
      }
      reloadOptions(selected ? selected.id : "");
      showNotice(wrap, t("savedOk"), true);
      return selected;
    }

    function setWorkingState(working, textBtn) {
      localBtn.disabled = working;
      saveBtn.disabled = working;
      applyBtn.disabled = working;
      enhancedBtn.disabled = working;
      submitBtn.disabled = working;
      scanBtn.disabled = working;
      if (textBtn) textBtn.textContent = working ? t("loading") : textBtn.__originText;
    }

    async function runEnhancedFetch(url, selectedSourceId) {
      var clean = String(url || "").trim();
      if (!clean) {
        showNotice(wrap, t("requiredUrl"), false);
        return false;
      }

      var secret = findSecret();
      showNotice(wrap, t("loading"), true);
      try {
        await fetchAndApplyRemoteConfig(clean, secret);
        if (selectedSourceId) {
          writeSources(withFetchResult(readSources(), selectedSourceId, "ok"));
          reloadOptions(selectedSourceId);
        }
        showNotice(wrap, t("applySuccess"), true);
        return true;
      } catch (err) {
        if (selectedSourceId) {
          writeSources(withFetchResult(readSources(), selectedSourceId, "failed"));
          reloadOptions(selectedSourceId);
        }
        showNotice(wrap, classifyRemoteError(err), false);
        return false;
      }
    }

    localBtn.addEventListener("click", function () {
      localFileInput.click();
    });

    localFileInput.addEventListener("change", async function (evt) {
      var file = evt.target && evt.target.files && evt.target.files[0];
      if (!file) return;

      localBtn.__originText = localBtn.__originText || localBtn.textContent;
      setWorkingState(true, localBtn);
      try {
        var text = await file.text();
        await uploadConfig(text, findSecret());
        showNotice(wrap, t("localLoaded"), true);
      } catch (err) {
        showNotice(wrap, t("localLoadFailed") + ": " + (err && err.message ? err.message : String(err)), false);
      } finally {
        setWorkingState(false, localBtn);
        localFileInput.value = "";
      }
    });

    saveBtn.addEventListener("click", function () {
      saveCurrentSource("manual");
    });

    sourceSelect.addEventListener("change", function () {
      var source = getSelectedSource();
      if (!source) return;
      providerInput.value = source.name;
      groupInput.value = source.group;
    });

    fillBtn.addEventListener("click", function () {
      var source = getSelectedSource();
      if (!source) {
        showNotice(wrap, t("selectFirst"), false);
        return;
      }
      urlInput.value = source.url;
      triggerInput(urlInput);
      providerInput.value = source.name;
      groupInput.value = source.group;
    });

    applyBtn.addEventListener("click", async function () {
      var source = getSelectedSource();
      if (!source) {
        showNotice(wrap, t("selectFirst"), false);
        return;
      }

      providerInput.value = source.name;
      groupInput.value = source.group;
      urlInput.value = source.url;
      triggerInput(urlInput);

      // Prefer our same-origin fetch+upload path so we can surface errors and
      // keep required safety patches (controller bind/secret/tun excludes).
      applyBtn.__originText = applyBtn.__originText || applyBtn.textContent;
      setWorkingState(true, applyBtn);
      try {
        await runEnhancedFetch(source.url, source.id);
      } finally {
        setWorkingState(false, applyBtn);
      }
    });

    enhancedBtn.addEventListener("click", async function () {
      var cleanUrl = String(urlInput.value || "").trim();
      var source = getSelectedSource() || resolveSourceForUrl(cleanUrl);
      var selectedId = source ? source.id : "";

      enhancedBtn.__originText = enhancedBtn.__originText || enhancedBtn.textContent;
      setWorkingState(true, enhancedBtn);
      try {
        await runEnhancedFetch(cleanUrl, selectedId);
      } finally {
        setWorkingState(false, enhancedBtn);
      }
    });

    deleteBtn.addEventListener("click", function () {
      var id = sourceSelect.value || "";
      if (!id) {
        showNotice(wrap, t("selectFirst"), false);
        return;
      }
      var items = readSources().filter(function (x) {
        return x.id !== id;
      });
      writeSources(items);
      reloadOptions("");
      showNotice(wrap, t("deletedOk"), true);
    });

    scanBtn.addEventListener("click", async function () {
      scanBtn.__originText = scanBtn.__originText || scanBtn.textContent;
      setWorkingState(true, scanBtn);
      try {
        var raw = await scanWithCamera();
        var parsed = parseSubscriptionContent(raw);
        if (!parsed) {
          showNotice(wrap, t("scanParseFailed"), false);
          return;
        }

        urlInput.value = parsed;
        triggerInput(urlInput);

        if (!providerInput.value) {
          providerInput.value = deriveProviderNameFromUrl(parsed);
        }

        showNotice(wrap, t("scanSuccess"), true);

        if (providerInput.value) {
          saveCurrentSource("qr");
        }
      } catch (err) {
        if (!err || err.kind === "scan-cancel") return;
        if (err.kind === "scan-permission") {
          showNotice(wrap, t("scanPermissionDenied"), false);
        } else if (err.kind === "scan-device") {
          showNotice(wrap, t("scanNoCamera"), false);
        } else if (err.kind === "scan-unavailable") {
          showNotice(wrap, t("scanUnavailable"), false);
        } else {
          showNotice(wrap, t("scanUnavailable") + " " + (err.message || ""), false);
        }
      } finally {
        setWorkingState(false, scanBtn);
      }
    });

    reloadOptions("");
  }

  function scanAndEnhance() {
    var onConfigRoute = isConfigRoute();
    document.documentElement.classList.toggle("lzc-config-route", onConfigRoute);
    if (!onConfigRoute) return;

    ensureEnhanceStyles();

    var forms = document.querySelectorAll("form");
    for (var i = 0; i < forms.length; i += 1) {
      var form = forms[i];
      if (!isRemoteConfigForm(form)) continue;
      enhanceForm(form);
    }
  }

  function hasMaskImage(maskValue) {
    var normalized = String(maskValue || "").trim().toLowerCase();
    return !!normalized && normalized !== "none";
  }

  function patchBrokenMaskSpinners(root) {
    var scope = root;
    if (!scope || (scope.nodeType !== 1 && scope.nodeType !== 9 && scope.nodeType !== 11)) {
      scope = document.body || document.documentElement;
    }
    if (!scope || !scope.querySelectorAll) return;

    var nodes = [];
    if (scope.nodeType === 1 && scope.tagName === "SPAN") {
      nodes.push(scope);
    }

    var found = scope.querySelectorAll("span[class*='mask-size'][class*='mask-position'][class*='mask-repeat']");
    for (var i = 0; i < found.length; i += 1) {
      nodes.push(found[i]);
    }

    for (var j = 0; j < nodes.length; j += 1) {
      var el = nodes[j];
      if (!el || el.getAttribute(MASK_PATCH_ATTR) === "1") continue;

      var className = typeof el.className === "string" ? el.className : "";
      if (
        className.indexOf("mask-size") < 0 ||
        className.indexOf("mask-position") < 0 ||
        className.indexOf("mask-repeat") < 0
      ) {
        continue;
      }

      var cs = window.getComputedStyle ? window.getComputedStyle(el) : null;
      if (!cs) continue;

      var maskImage = cs.maskImage;
      var webkitMaskImage = cs.webkitMaskImage;
      if (hasMaskImage(maskImage) || hasMaskImage(webkitMaskImage)) continue;

      el.style.maskImage = FALLBACK_SPINNER_MASK;
      el.style.webkitMaskImage = FALLBACK_SPINNER_MASK;
      el.setAttribute(MASK_PATCH_ATTR, "1");
    }
  }

  var observer = new MutationObserver(function (mutations) {
    for (var i = 0; i < mutations.length; i += 1) {
      var mutation = mutations[i];
      if (!mutation || mutation.type !== "childList") continue;

      for (var j = 0; j < mutation.addedNodes.length; j += 1) {
        var node = mutation.addedNodes[j];
        if (!node || (node.nodeType !== 1 && node.nodeType !== 11)) continue;
        patchBrokenMaskSpinners(node);
      }
    }

    scanAndEnhance();
  });

  function onRouteChange() {
    patchBrokenMaskSpinners(document.body || document.documentElement);
    scanAndEnhance();
  }

  function start() {
    onRouteChange();
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }

  window.addEventListener("hashchange", onRouteChange);
  window.addEventListener("popstate", onRouteChange);
})();
