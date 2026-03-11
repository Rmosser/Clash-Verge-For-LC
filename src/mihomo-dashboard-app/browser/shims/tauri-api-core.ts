import {
  basename,
  dispatchAppEvent,
  getUnsupportedWebFeatureMessage,
  getRegisteredFile,
  getLzcConfig,
  isLzcWebRuntime,
  readRegisteredBuffer,
  resolveAppFileUrl,
  saveBlob,
  textToBase64,
  vergeInvoke
} from "../runtime";

const maybeSerializeRegisteredPath = async (
  value: unknown
): Promise<unknown> => {
  if (typeof value === "string") {
    const file = getRegisteredFile(value);
    if (file) {
      return {
        __registeredFile: true,
        name: file.name,
        content_b64: textToBase64(await file.text())
      };
    }
    return value;
  }
  if (Array.isArray(value)) {
    return Promise.all(value.map((item) => maybeSerializeRegisteredPath(item)));
  }
  if (value && typeof value === "object") {
    const entries = await Promise.all(
      Object.entries(value as Record<string, unknown>).map(async ([key, item]) => [
        key,
        await maybeSerializeRegisteredPath(item)
      ])
    );
    return Object.fromEntries(entries);
  }
  return value;
};

export const invoke = async <T>(
  cmd: string,
  args?: Record<string, unknown>
): Promise<T> => {
  if (cmd === "notify_ui_ready" || cmd === "update_ui_stage" || cmd === "open_devtools") {
    return undefined as T;
  }
  if (cmd === "open_web_url") {
    const url = typeof args?.url === "string" ? args.url : "";
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
    return undefined as T;
  }
  if (cmd === "exit_app" || cmd === "restart_app" || cmd === "exit_lightweight_mode") {
    window.location.reload();
    return undefined as T;
  }
  if (isLzcWebRuntime()) {
    if (cmd === "entry_lightweight_mode") {
      throw new Error(getUnsupportedWebFeatureMessage("lightweight-mode"));
    }
    if (
      cmd === "install_service" ||
      cmd === "uninstall_service" ||
      cmd === "reinstall_service" ||
      cmd === "repair_service"
    ) {
      throw new Error(getUnsupportedWebFeatureMessage("system-service"));
    }
    if (cmd === "invoke_uwp_tool") {
      throw new Error(getUnsupportedWebFeatureMessage("uwp-tool"));
    }
  }

  const payload = (await maybeSerializeRegisteredPath(args ?? {})) as Record<
    string,
    unknown
  >;
  const result = await vergeInvoke<any>(cmd, payload);

  if (cmd === "export_local_backup" && result?.filename && result?.content_b64) {
    const buffer = Uint8Array.from(atob(result.content_b64), (char) =>
      char.charCodeAt(0)
    );
    saveBlob(
      new Blob([buffer], { type: result.content_type ?? "application/gzip" }),
      result.download_name ?? basename(result.filename)
    );
    return undefined as T;
  }

  if (cmd === "view_profile" && result?.filename && result?.content) {
    saveBlob(
      new Blob([result.content], {
        type: result.content_type ?? "text/plain; charset=utf-8"
      }),
      basename(result.filename)
    );
    return undefined as T;
  }

  if (cmd === "copy_clash_env" && typeof result === "string") {
    await navigator.clipboard.writeText(result);
    return undefined as T;
  }

  if (
    (cmd === "open_app_dir" || cmd === "open_core_dir" || cmd === "open_logs_dir") &&
    result?.path &&
    typeof result.path === "string"
  ) {
    await navigator.clipboard.writeText(result.path);
    return undefined as T;
  }

  if (cmd === "export_diagnostic_info" && result?.filename && result?.content_b64) {
    const buffer = Uint8Array.from(atob(result.content_b64), (char) =>
      char.charCodeAt(0)
    );
    saveBlob(
      new Blob([buffer], {
        type: result.content_type ?? "application/json"
      }),
      result.download_name ?? basename(result.filename)
    );
    return undefined as T;
  }

  if (cmd === "copy_icon_file" && result?.path && typeof result.path === "string") {
    return result.path as T;
  }

  if (cmd === "patch_profiles_config" && args?.profiles && typeof args.profiles === "object") {
    const profiles = args.profiles as { current?: string };
    if (profiles.current) {
      dispatchAppEvent("profile-changed", profiles.current);
    }
    dispatchAppEvent("verge://refresh-clash-config", null);
    dispatchAppEvent("verge://refresh-proxy-config", null);
  }

  if (cmd === "patch_clash_config") {
    if (result?.secret && typeof result.secret === "string") {
      const mutableWindow = window as unknown as {
        __LZCAPP_MIHOMO__?: ReturnType<typeof getLzcConfig>;
      };
      mutableWindow.__LZCAPP_MIHOMO__ = {
        ...getLzcConfig(),
        secret: result.secret
      };
    }
    dispatchAppEvent("verge://refresh-clash-config", null);
    dispatchAppEvent("verge://refresh-proxy-config", null);
  }

  if (cmd === "patch_verge_config" || cmd === "apply_dns_config" || cmd === "restart_core") {
    dispatchAppEvent("verge://refresh-clash-config", null);
    dispatchAppEvent("verge://refresh-proxy-config", null);
  }

  return result as T;
};

export const convertFileSrc = (path: string) => resolveAppFileUrl(path);
