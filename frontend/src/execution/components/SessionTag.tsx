import { SESSION_COLORS } from "@/execution/lib/constants";

interface SessionTagProps {
  session: string;
}

export function SessionTag({ session }: SessionTagProps) {
  const color = SESSION_COLORS[session] ?? "bg-text-muted/20 text-text-muted";
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${color}`}
    >
      {session}
    </span>
  );
}
