/* Minimal Clash/Mihomo dashboard (no build step).
 *
 * Served as a LazyCat app static site, proxying API via /api -> 127.0.0.1:9090.
 */

const API_BASE = "/api";
const TEST_URL = "https://www.gstatic.com/generate_204";
const TEST_TIMEOUT_MS = 6000;

function qs(sel) {
  return document.querySelector(sel);
}

function setStatus(text) {
  const el = qs("#status");
  el.textContent = text;
}

function loadSecret() {
  try {
    return localStorage.getItem("mihomoSecret") || "";
  } catch {
    return "";
  }
}

function saveSecret(secret) {
  try {
    localStorage.setItem("mihomoSecret", secret);
  } catch {
    // ignore
  }
}

function authHeaders() {
  const secret = qs("#secret").value.trim();
  if (!secret) return {};
  return { Authorization: `Bearer ${secret}` };
}

async function apiFetch(path, init = {}) {
  const headers = {
    ...(init.headers || {}),
    ...authHeaders(),
  };
  const resp = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`${resp.status} ${resp.statusText}${body ? `: ${body}` : ""}`);
  }
  return resp;
}

function isGroupProxy(p) {
  return p && typeof p === "object" && Array.isArray(p.all) && typeof p.type === "string";
}

function groupSortKey(name) {
  if (name === "PROXY") return "00_" + name;
  if (name === "AUTO") return "01_" + name;
  if (name === "default") return "02_" + name;
  return "99_" + name.toLowerCase();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function loadGroups() {
  setStatus("Loading /proxies …");

  const data = await (await apiFetch("/proxies")).json();
  const proxies = data && data.proxies ? data.proxies : {};

  const groups = Object.entries(proxies)
    .filter(([name, p]) => isGroupProxy(p) && name !== "GLOBAL")
    .sort(([a], [b]) => groupSortKey(a).localeCompare(groupSortKey(b)));

  const root = qs("#groups");
  root.innerHTML = "";

  if (groups.length === 0) {
    setStatus("No proxy groups found via API.");
    return;
  }

  for (const [groupName, group] of groups) {
    const tpl = qs("#groupTpl");
    const node = tpl.content.cloneNode(true);

    const title = node.querySelector(".card__title");
    const meta = node.querySelector(".card__meta");
    const nowEl = node.querySelector(".js-now");
    const select = node.querySelector(".js-select");
    const delayEl = node.querySelector(".js-delay");
    const hintEl = node.querySelector(".js-hint");
    const testBtn = node.querySelector(".js-testNow");

    title.textContent = groupName;
    meta.textContent = `${group.type} • ${group.all.length} nodes`;
    nowEl.textContent = group.now || "-";

    // Populate options.
    for (const n of group.all) {
      const opt = document.createElement("option");
      opt.value = n;
      opt.textContent = n;
      if (group.now && n === group.now) opt.selected = true;
      select.appendChild(opt);
    }

    const applySelection = async (next) => {
      hintEl.textContent = "";
      delayEl.textContent = "-";
      setStatus(`Switching ${groupName} -> ${next} …`);
      await apiFetch(`/proxies/${encodeURIComponent(groupName)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: next }),
      });
      setStatus(`Switched ${groupName} -> ${next}`);
      await loadGroups();
    };

    select.addEventListener("change", async (e) => {
      const next = e.target.value;
      try {
        await applySelection(next);
      } catch (err) {
        hintEl.textContent = `Switch failed: ${err.message}`;
        setStatus("Ready");
      }
    });

    testBtn.addEventListener("click", async () => {
      const proxyName = (group.now || select.value || "").trim();
      if (!proxyName) return;
      hintEl.textContent = "";
      delayEl.textContent = "testing…";
      try {
        const q = new URLSearchParams({
          timeout: String(TEST_TIMEOUT_MS),
          url: TEST_URL,
        });
        const r = await (await apiFetch(`/proxies/${encodeURIComponent(proxyName)}/delay?${q.toString()}`)).json();
        const d = typeof r.delay === "number" ? `${r.delay} ms` : "-";
        delayEl.textContent = d;
      } catch (err) {
        delayEl.textContent = "-";
        hintEl.textContent = `Delay test failed: ${err.message}`;
      }
    });

    root.appendChild(node);
  }

  setStatus("Ready");
}

function setupControls() {
  const secret = qs("#secret");
  secret.value = loadSecret();

  qs("#saveSecret").addEventListener("click", () => {
    saveSecret(secret.value.trim());
    setStatus("Secret saved (local storage).");
  });

  qs("#refresh").addEventListener("click", async () => {
    try {
      await loadGroups();
    } catch (err) {
      setStatus(`Error: ${escapeHtml(err.message)}`);
    }
  });
}

async function main() {
  setupControls();

  try {
    await loadGroups();
  } catch (err) {
    setStatus(`Error: ${escapeHtml(err.message)}`);
  }
}

main();

