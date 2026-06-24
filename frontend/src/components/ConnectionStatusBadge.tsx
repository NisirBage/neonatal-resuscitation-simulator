export type ConnectionBadgeStatus = "connected" | "reconnecting" | "disconnected";

interface ConnectionStatusBadgeProps {
  websocketStatus: string;
}

function mapConnectionStatus(rawStatus: string): ConnectionBadgeStatus {
  if (rawStatus === "connected") {
    return "connected";
  }

  if (rawStatus === "connecting") {
    return "reconnecting";
  }

  return "disconnected";
}

const STATUS_STYLES: Record<
  ConnectionBadgeStatus,
  { label: string; className: string; dotClassName: string }
> = {
  connected: {
    label: "Connected",
    className: "border-emerald-200 bg-emerald-50 text-emerald-800",
    dotClassName: "bg-emerald-500"
  },
  reconnecting: {
    label: "Reconnecting",
    className: "border-amber-200 bg-amber-50 text-amber-800",
    dotClassName: "bg-amber-500 animate-pulse"
  },
  disconnected: {
    label: "Disconnected",
    className: "border-rose-200 bg-rose-50 text-rose-800",
    dotClassName: "bg-rose-500"
  }
};

export function ConnectionStatusBadge({ websocketStatus }: ConnectionStatusBadgeProps) {
  const status = mapConnectionStatus(websocketStatus);
  const styles = STATUS_STYLES[status];

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium ${styles.className}`}
    >
      <span className={`h-2 w-2 rounded-full ${styles.dotClassName}`} />
      {styles.label}
    </span>
  );
}