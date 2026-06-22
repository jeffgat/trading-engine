import { AuthControls } from '@/auth/AuthControls';
import { AuthenticatedApiBridge } from '@/auth/AuthenticatedApiBridge';
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
    return (
        <AuthenticatedApiBridge>
            <AppShell authState={authState} />
        </AuthenticatedApiBridge>
    );
}

function AppShell({ authState }: { authState: OwnerAuthState }) {
    const location = useLocation();
    const isDeployedPublic = import.meta.env.PROD && !authState.isOwner;
    const isExecution = location.pathname.startsWith('/execution');
    const isPerformance = location.pathname.startsWith('/performance');

    return (
        <div className="app-shell min-h-screen">
            {/* Top-level section nav */}
            <nav className="gc-top-nav">
                <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-2 sm:px-6 lg:px-8">
                    <div className="flex min-w-0 flex-wrap items-center gap-3 sm:gap-6">
                        <span className="gc-brand">
                            <img src="/gat-cap-logo-champagne.png" alt="Gat Capital logo" className="gc-brand-logo" />
                            <span>
                                gat<span>.</span>capital
                            </span>
                        </span>
                        <div className="gc-section-switch">
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
            {isDeployedPublic ? <PublicDeployRoutes /> : <FullAppRoutes authState={authState} />}
        </div>
    );
}

function TopNavLink({ to, active, children }: { to: string; active: boolean; children: ReactNode }) {
    return (
        <Link
            to={to}
            className={`gc-nav-link ${active ? 'is-active' : ''}`}>
            {children}
        </Link>
    );
}

function FullAppRoutes({ authState }: { authState: OwnerAuthState }) {
    const executionReadOnly = CLERK_ENABLED && !authState.isOwner;

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
                        <ExecutionApp readOnly={executionReadOnly} />
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
