(function () {
  var current = window.__LZCAPP_MIHOMO__ || {};
  function readJsonSync(url) {
    var request = new XMLHttpRequest();
    request.open("GET", url, false);
    request.withCredentials = true;
    request.send(null);
    if (request.status >= 200 && request.status < 300) {
      return JSON.parse(request.responseText || "{}");
    }
    return null;
  }

  var config = {
    secret: "",
    vergeApiSecret: "",
    mihomoBaseUrl: current.mihomoBaseUrl || "/api",
    vergeApiBaseUrl: current.vergeApiBaseUrl || "/verge-api",
    appVersion: current.appVersion || "2.4.7-webport.0",
    runtimeInfo: null,
    runtimeWarning: null
  };

  try {
    var remote = readJsonSync(config.vergeApiBaseUrl + "/public-config");
    if (remote) {
      config.secret = remote.secret || "";
      config.vergeApiSecret = "";
      config.mihomoBaseUrl = remote.mihomoBaseUrl || config.mihomoBaseUrl;
      config.vergeApiBaseUrl = remote.vergeApiBaseUrl || config.vergeApiBaseUrl;
      config.appVersion = remote.appVersion || config.appVersion;
    }
  } catch (_error) {}

  try {
    var runtimeInfo = readJsonSync(config.vergeApiBaseUrl + "/runtime-info");
    if (runtimeInfo) {
      config.runtimeInfo = runtimeInfo;
    }
  } catch (_error) {}

  window.__LZCAPP_MIHOMO__ = config;
})();
