/**
 * WebSocket client utility for Attendance & Workstation presence stream
 */

export const resolveWsUrl = (path: string = "/ws/attendance"): string => {
  if (typeof window === "undefined") return `ws://127.0.0.1:8000${path}`;

  const host = window.location.hostname || "127.0.0.1";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  
  if (process.env.NEXT_PUBLIC_WS_URL) {
    const configured = process.env.NEXT_PUBLIC_WS_URL.replace("://localhost:", "://127.0.0.1:");
    if (path === "/ws/attendance") return configured;
    return configured.replace("/ws/attendance", path);
  }

  return `${protocol}//${host}:8000${path}`;
};

export class AttendanceWebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private onMessage: (msg: any) => void;
  private onStatusChange: (status: "connected" | "disconnected") => void;
  private reconnectAttempts = 0;
  private isExplicitlyClosed = false;
  private reconnectTimer: any = null;

  constructor(
    url: string,
    onMessage: (msg: any) => void,
    onStatusChange: (status: "connected" | "disconnected") => void
  ) {
    this.url = url;
    this.onMessage = onMessage;
    this.onStatusChange = onStatusChange;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    this.isExplicitlyClosed = false;

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.reconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.onStatusChange("connected");
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.onMessage(data);
      } catch (e) {
        console.error("[WS] Failed to parse message", e);
      }
    };

    this.ws.onclose = () => {
      this.onStatusChange("disconnected");
      if (!this.isExplicitlyClosed) {
        this.reconnect();
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private reconnect() {
    if (this.isExplicitlyClosed) return;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectAttempts++;
    const delay = Math.min(15000, 3000 * Math.pow(1.5, Math.min(this.reconnectAttempts, 4)));

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  disconnect() {
    this.isExplicitlyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
