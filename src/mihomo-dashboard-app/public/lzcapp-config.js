(function () {
  var current = window.__LZCAPP_MIHOMO__ || {};
  var config = {
    secret: current.secret || "",
    vergeApiSecret: current.vergeApiSecret || "",
    mihomoBaseUrl: current.mihomoBaseUrl || "/api",
    vergeApiBaseUrl: current.vergeApiBaseUrl || "/verge-api",
    appVersion: current.appVersion || "2.4.7-webport.0"
  };

  try {
    if (config.vergeApiSecret) {
      var request = new XMLHttpRequest();
      request.open(
        "GET",
        config.vergeApiBaseUrl +
          "/public-config?token=" +
          encodeURIComponent(config.vergeApiSecret),
        false
      );
      request.send(null);
      if (request.status >= 200 && request.status < 300) {
        var remote = JSON.parse(request.responseText || "{}");
        config.secret = remote.secret || config.secret;
        config.vergeApiSecret = remote.vergeApiSecret || config.vergeApiSecret;
        config.mihomoBaseUrl = remote.mihomoBaseUrl || config.mihomoBaseUrl;
        config.vergeApiBaseUrl = remote.vergeApiBaseUrl || config.vergeApiBaseUrl;
        config.appVersion = remote.appVersion || config.appVersion;
      }
    }
  } catch (_error) {}

  window.__LZCAPP_MIHOMO__ = config;
})();
