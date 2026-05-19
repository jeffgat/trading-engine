import type { HTMLAttributes } from "react";

import { cn } from "@/shared/utils";

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  muted?: boolean;
}

const textWidths = ["w-11/12", "w-4/5", "w-2/3", "w-5/6", "w-3/5"];

export function Skeleton({ className, muted = false, ...props }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "skeleton-shimmer rounded-md border border-border/70 bg-bg-card/80",
        muted && "border-border/45 bg-bg-secondary/70",
        className,
      )}
      {...props}
    />
  );
}

export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton
          key={index}
          className={cn("h-3 rounded", textWidths[index % textWidths.length])}
          muted
        />
      ))}
    </div>
  );
}

export function MetricGridSkeleton({
  count = 5,
  className,
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5", className)}>
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="rounded-lg border border-border bg-bg-card p-4">
          <Skeleton className="h-3 w-20 rounded" muted />
          <Skeleton className="mt-3 h-7 w-24 rounded" />
          <Skeleton className="mt-3 h-2 w-16 rounded" muted />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({
  rows = 8,
  columns = 6,
  className,
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-lg border border-border bg-bg-card", className)}>
      <div
        className="grid gap-3 border-b border-border px-4 py-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(5rem, 1fr))` }}
      >
        {Array.from({ length: columns }).map((_, index) => (
          <Skeleton key={index} className="h-3 rounded" muted />
        ))}
      </div>
      <div className="divide-y divide-border/55">
        {Array.from({ length: rows }).map((_, rowIndex) => (
          <div
            key={rowIndex}
            className="grid gap-3 px-4 py-3"
            style={{ gridTemplateColumns: `repeat(${columns}, minmax(5rem, 1fr))` }}
          >
            {Array.from({ length: columns }).map((_, columnIndex) => (
              <Skeleton
                key={columnIndex}
                className={cn(
                  "h-3 rounded",
                  columnIndex === 0 ? "w-4/5" : columnIndex === columns - 1 ? "w-2/3" : "w-full",
                )}
                muted={rowIndex % 2 === 1}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
