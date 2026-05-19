import { AuthControls } from '@/auth/AuthControls';
import { CLERK_ENABLED, PUBLIC_AUTH_STATE, type OwnerAuthState } from '@/auth/clerkConfig';
import { useOwnerAuthState } from '@/auth/useOwnerAuthState';
import { RoutePageSkeleton } from '@/shared/ui/page-skeletons';
import { lazy, Suspense, type ReactNode } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

const BacktestApp = lazy(() =>
    import('@/backtesting/BacktestApp').then((module) => ({ default: module.BacktestApp })),
);
const ExecutionApp = lazy(() =>
    import('@/execution/ExecutionApp').then((module) => ({ default: module.ExecutionApp })),
);

function App() {
    if (CLERK_ENABLED) {
        return <ClerkAwareApp />;
    }

    return <AppShell authState={PUBLIC_AUTH_STATE} />;
}

function ClerkAwareApp() {
    const authState = useOwnerAuthState();
    return <AppShell authState={authState} />;
}

function AppShell({ authState }: { authState: OwnerAuthState }) {
    const location = useLocation();
    const isDeployedPublic = import.meta.env.PROD && !authState.isOwner;
    const isExecution = location.pathname.startsWith('/execution');
    const isPerformance = location.pathname.startsWith('/performance');

    return (
        <div className="app-shell min-h-screen">
            {/* Top-level section nav */}
            <nav className="border-b border-border bg-bg-secondary/70 backdrop-blur-sm">
                <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-2 sm:px-6 lg:px-8">
                    <div className="flex min-w-0 flex-wrap items-center gap-3 sm:gap-6">
                        <span className="font-brand inline-flex items-center gap-2 rounded-md border border-profit/30 bg-bg-primary/80 px-3 py-2 text-lg font-semibold tracking-normal text-profit shadow-[0_0_18px_rgba(114,242,95,0.12)]">
                            <img src="/gat-cap-logo.png" alt="Gat Capital logo" className="h-5 w-5 object-contain" />
                            <span>
                                gat<span className="text-info">.</span>capital
                            </span>
                        </span>
                        <div className="flex gap-1 rounded-lg border border-border bg-bg-primary/70 p-1">
                            {isDeployedPublic ? (
                                <>
                                    <TopNavLink to="/" active={!isPerformance}>
                                        Status
                                    </TopNavLink>
                                    <TopNavLink to="/performance" active={isPerformance}>
                                        Performance
                                    </TopNavLink>
                                </>
                            ) : (
                                <>
                                    <TopNavLink to="/" active={!isExecution}>
                                        Backtesting
                                    </TopNavLink>
                                    <TopNavLink to="/execution" active={isExecution}>
                                        Execution
                                    </TopNavLink>
                                </>
                            )}
                        </div>
                    </div>
                    <AuthControls enabled={CLERK_ENABLED} showFallback={import.meta.env.PROD} state={authState} />
                </div>
            </nav>

            {/* Section content */}
            {isDeployedPublic ? <PublicDeployRoutes /> : <FullAppRoutes />}
        </div>
    );
}

function TopNavLink({ to, active, children }: { to: string; active: boolean; children: ReactNode }) {
    return (
        <Link
            to={to}
            className={`rounded-md px-4 py-2 font-mono text-sm font-semibold lowercase transition-colors ${
                active
                    ? 'bg-profit text-bg-primary shadow-[0_0_18px_rgba(114,242,95,0.18)]'
                    : 'text-text-secondary hover:bg-bg-card-hover hover:text-foreground'
            }`}>
            {children}
        </Link>
    );
}

function FullAppRoutes() {
    return (
        <Routes>
            <Route
                path="/"
                element={
                    <Suspense fallback={<RoutePageSkeleton section="backtesting" />}>
                        <BacktestApp />
                    </Suspense>
                }
            />
            <Route
                path="/execution/*"
                element={
                    <Suspense fallback={<RoutePageSkeleton section="execution" />}>
                        <ExecutionApp />
                    </Suspense>
                }
            />
            <Route path="/performance" element={<Navigate to="/execution" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

function PublicDeployRoutes() {
    return (
        <Routes>
            <Route
                path="/"
                element={
                    <Suspense fallback={<RoutePageSkeleton section="execution" />}>
                        <ExecutionApp forcedTab="status" hideTabNav readOnly />
                    </Suspense>
                }
            />
            <Route
                path="/performance"
                element={
                    <Suspense fallback={<RoutePageSkeleton section="execution" />}>
                        <ExecutionApp forcedTab="performance" hideTabNav readOnly />
                    </Suspense>
                }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

export default App;
