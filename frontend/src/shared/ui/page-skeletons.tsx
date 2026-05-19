import { MetricGridSkeleton, Skeleton, SkeletonText, TableSkeleton } from "@/shared/ui/skeleton";
import { cn } from "@/shared/utils";

export type BacktestingSkeletonTab =
  | "backtests"
  | "saved"
  | "configs"
  | "optimizations"
  | "coverage"
  | "risk-engine"
  | "regime"
  | "news";

export type ExecutionSkeletonTab = "status" | "trades" | "performance" | "logs" | "config";

function TabRailSkeleton({ count, wide = false }: { count: number; wide?: boolean }) {
  return (
    <div className="border-b border-border bg-bg-secondary/60 px-4 py-2 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl gap-1 overflow-hidden rounded-lg border border-border bg-bg-primary/70 p-1">
        {Array.from({ length: count }).map((_, index) => (
          <Skeleton
            key={index}
            className={cn("h-9 shrink-0 rounded-md", wide ? "w-32" : "w-24", index === 0 && "bg-profit/20")}
            muted={index !== 0}
          />
        ))}
      </div>
    </div>
  );
}

function HeaderSkeleton({ subtitle = true }: { subtitle?: boolean }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <Skeleton className="h-6 w-48 rounded" />
        {subtitle && <Skeleton className="mt-2 h-3 w-72 max-w-[70vw] rounded" muted />}
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-8 w-24 rounded-md" muted />
        <Skeleton className="h-8 w-28 rounded-md" muted />
      </div>
    </div>
  );
}

function AnalyticsResultsSkeleton() {
  return (
    <div className="mt-4 space-y-4">
      <MetricGridSkeleton count={5} />
      <MetricGridSkeleton count={5} />
      <Skeleton className="h-[430px] rounded-lg" />
      <TableSkeleton rows={5} columns={7} />
    </div>
  );
}

function HistoryWithResultsSkeleton({ optimized = false }: { optimized?: boolean }) {
  return (
    <>
      <TableSkeleton rows={6} columns={optimized ? 8 : 10} />
      {optimized ? (
        <div className="mt-4 space-y-4">
          <MetricGridSkeleton count={4} className="lg:grid-cols-4" />
          <Skeleton className="h-[300px] rounded-lg" />
          <TableSkeleton rows={5} columns={6} />
        </div>
      ) : (
        <AnalyticsResultsSkeleton />
      )}
    </>
  );
}

function ConfigsSkeleton() {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
      <div className="rounded-lg border border-border bg-bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <Skeleton className="h-4 w-28 rounded" />
          <Skeleton className="h-3 w-14 rounded" muted />
        </div>
        <div className="divide-y divide-border/60">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <Skeleton className="h-4 w-36 rounded" />
                <Skeleton className="h-3 w-16 rounded" muted />
              </div>
              <div className="mt-2 flex gap-2">
                <Skeleton className="h-5 w-10 rounded" muted />
                <Skeleton className="h-5 w-20 rounded" muted />
                <Skeleton className="h-5 w-12 rounded" muted />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-4">
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <SkeletonText lines={4} />
        </div>
        <Skeleton className="h-28 rounded-lg" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    </div>
  );
}

function CoverageSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="rounded-lg border border-border bg-bg-card p-4">
          <div className="flex items-center justify-between">
            <Skeleton className="h-5 w-14 rounded" />
            <Skeleton className="h-4 w-20 rounded" muted />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((__, metricIndex) => (
              <Skeleton key={metricIndex} className="h-10 rounded" muted />
            ))}
          </div>
          <SkeletonText lines={4} className="mt-4" />
        </div>
      ))}
    </div>
  );
}

function RiskEngineSkeleton() {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="flex items-center justify-between gap-4">
          <Skeleton className="h-4 w-48 rounded" />
          <Skeleton className="h-8 w-32 rounded-md" muted />
        </div>
      </div>
      <MetricGridSkeleton count={4} className="lg:grid-cols-4" />
      <div className="grid gap-4 xl:grid-cols-2">
        <Skeleton className="h-72 rounded-lg" />
        <Skeleton className="h-72 rounded-lg" />
      </div>
    </div>
  );
}

function RegimeSkeleton() {
  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      <div className="rounded-lg border border-border bg-bg-card p-3">
        <div className="mb-3 flex items-center justify-between">
          <Skeleton className="h-4 w-20 rounded" />
          <Skeleton className="h-3 w-16 rounded" muted />
        </div>
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-20 rounded-md" muted />
          ))}
        </div>
      </div>
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <MetricGridSkeleton count={3} className="sm:grid-cols-3 lg:grid-cols-3" />
        <Skeleton className="mt-5 h-72 rounded-lg" />
      </div>
    </div>
  );
}

function NewsSkeleton() {
  return (
    <div className="space-y-6">
      <TableSkeleton rows={4} columns={9} />
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-7">
          {Array.from({ length: 7 }).map((_, index) => (
            <div key={index}>
              <Skeleton className="h-3 w-20 rounded" muted />
              <Skeleton className="mt-2 h-8 rounded" />
            </div>
          ))}
        </div>
      </div>
      <MetricGridSkeleton count={5} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton className="h-72 rounded-lg" />
        <Skeleton className="h-72 rounded-lg" />
      </div>
    </div>
  );
}

export function BacktestingTabSkeleton({ tab }: { tab: BacktestingSkeletonTab }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <HeaderSkeleton subtitle={tab !== "backtests"} />
      {tab === "backtests" && <HistoryWithResultsSkeleton />}
      {tab === "saved" && <HistoryWithResultsSkeleton />}
      {tab === "optimizations" && <HistoryWithResultsSkeleton optimized />}
      {tab === "configs" && <ConfigsSkeleton />}
      {tab === "coverage" && <CoverageSkeleton />}
      {tab === "risk-engine" && <RiskEngineSkeleton />}
      {tab === "regime" && <RegimeSkeleton />}
      {tab === "news" && <NewsSkeleton />}
    </div>
  );
}

function ExecutionHeaderSkeleton() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-bg-secondary/70 backdrop-blur-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-2 sm:px-6">
        <div className="flex gap-1 overflow-hidden rounded-lg border border-border bg-bg-primary/70 p-1">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className={cn("h-9 rounded-md", index === 0 ? "w-24 bg-profit/20" : "w-28")} muted={index !== 0} />
          ))}
        </div>
        <Skeleton className="h-7 w-28 rounded-md" muted />
      </div>
    </header>
  );
}

export function ExecutionTabSkeleton({ tab }: { tab: ExecutionSkeletonTab }) {
  if (tab === "status") {
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Skeleton className="h-4 w-40 rounded" muted />
          <div className="flex gap-2">
            <Skeleton className="h-8 w-20 rounded-md" muted />
            <Skeleton className="h-8 w-44 rounded-md" muted />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="rounded-lg border border-border bg-bg-card p-4">
              <div className="flex items-center justify-between">
                <Skeleton className="h-5 w-28 rounded" />
                <Skeleton className="h-6 w-16 rounded" muted />
              </div>
              <SkeletonText lines={4} className="mt-4" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (tab === "config") {
    return (
      <div className="space-y-5">
        <div className="flex gap-2">
          <Skeleton className="h-10 w-28 rounded-md" />
          <Skeleton className="h-10 w-36 rounded-md" muted />
          <Skeleton className="h-10 w-24 rounded-md" muted />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="rounded-lg border border-border bg-bg-card p-4">
              <Skeleton className="h-4 w-40 rounded" />
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {Array.from({ length: 6 }).map((__, fieldIndex) => (
                  <Skeleton key={fieldIndex} className="h-9 rounded-md" muted />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (tab === "performance") {
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-border bg-bg-card p-3">
          <div className="flex flex-wrap gap-3">
            {Array.from({ length: 7 }).map((_, index) => (
              <Skeleton key={index} className="h-8 w-32 rounded-md" muted />
            ))}
          </div>
        </div>
        <MetricGridSkeleton count={5} />
        <Skeleton className="h-[360px] rounded-lg" />
        <TableSkeleton rows={6} columns={8} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          <Skeleton className="h-8 w-24 rounded-md" />
          <Skeleton className="h-8 w-32 rounded-md" muted />
          {tab === "logs" && <Skeleton className="h-8 w-48 rounded-md" muted />}
        </div>
        <Skeleton className="h-4 w-24 rounded" muted />
      </div>
      <TableSkeleton rows={10} columns={tab === "logs" ? 5 : 6} className="min-h-[420px]" />
    </div>
  );
}

export function RoutePageSkeleton({ section }: { section: "backtesting" | "execution" }) {
  if (section === "execution") {
    return (
      <>
        <ExecutionHeaderSkeleton />
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <ExecutionTabSkeleton tab="status" />
        </main>
      </>
    );
  }

  return (
    <>
      <TabRailSkeleton count={8} wide />
      <BacktestingTabSkeleton tab="backtests" />
    </>
  );
}
