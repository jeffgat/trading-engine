import { BacktestApp } from '@/backtesting/BacktestApp';
import { ExecutionApp } from '@/execution/ExecutionApp';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

function App() {
    const location = useLocation();
    const isExecution = location.pathname.startsWith('/execution');

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
                            <Link
                                to="/"
                                className={`rounded-md px-4 py-2 font-mono text-sm font-semibold lowercase transition-colors ${
                                    !isExecution
                                        ? 'bg-profit text-bg-primary shadow-[0_0_18px_rgba(114,242,95,0.18)]'
                                        : 'text-text-secondary hover:bg-bg-card-hover hover:text-foreground'
                                }`}>
                                Backtesting
                            </Link>
                            <Link
                                to="/execution"
                                className={`rounded-md px-4 py-2 font-mono text-sm font-semibold lowercase transition-colors ${
                                    isExecution
                                        ? 'bg-profit text-bg-primary shadow-[0_0_18px_rgba(114,242,95,0.18)]'
                                        : 'text-text-secondary hover:bg-bg-card-hover hover:text-foreground'
                                }`}>
                                Execution
                            </Link>
                        </div>
                    </div>
                </div>
            </nav>

            {/* Section content */}
            <Routes>
                <Route path="/" element={<BacktestApp />} />
                <Route path="/execution/*" element={<ExecutionApp />} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </div>
    );
}

export default App;
