import { Alert } from "@mui/material";
import { useEffect, useState } from "react";

import { vergeJson } from "./runtime";

type AlertStatus = {
  configured: boolean;
  ready: boolean;
  corruptionCount: number;
};
export function RuntimeAlertBanner() {
  const [status, setStatus] = useState<AlertStatus | null>(null);
  useEffect(() => {
    let active = true;
    const read = async () => {
      try {
        const data = await vergeJson<{ alerting?: AlertStatus }>(
          "/runtime-info",
        );
        if (active) setStatus(data.alerting ?? null);
      } catch {
        /* The runtime contract and connection UI report availability. */
      }
    };
    void read();
    const timer = window.setInterval(() => {
      void read();
    }, 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  if (!status || status.ready) return null;
  return (
    <Alert
      severity={
        status.configured || status.corruptionCount ? "warning" : "info"
      }
    >
      {status.corruptionCount
        ? "告警日志异常，请检查宿主机运行状态。"
        : status.configured
          ? "外部告警发送尚未确认，请检查通知通道。"
          : "外部告警未启用；运行记录保存在懒猫宿主机，服务可正常使用。"}
    </Alert>
  );
}
