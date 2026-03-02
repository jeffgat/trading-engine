import { BacktestApp } from '@/backtesting/BacktestApp';
import { ExecutionApp } from '@/execution/ExecutionApp';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';

function App() {
    const location = useLocation();
    const isExecution = location.pathname.startsWith('/execution');

    return (
        <div className="min-h-screen bg-bg-primary">
            {/* Top-level section nav */}
            <nav className="border-b border-border bg-bg-secondary">
                <div className="mx-auto flex max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center gap-6">
                        <span className="text-lg font-semibold tracking-tight text-text-primary bg-black py-2 px-4">
                            Gat<span className="text-accent">.</span> Capital
                        </span>
                        <div className="flex gap-1">
                            <Link
                                to="/"
                                className={`px-4 py-3 text-sm font-medium capitalize transition-colors border-b-2 ${
                                    !isExecution
                                        ? 'border-accent text-text-primary'
                                        : 'border-transparent text-text-muted hover:text-text-secondary'
                                }`}>
                                Backtesting
                            </Link>
                            <Link
                                to="/execution"
                                className={`px-4 py-3 text-sm font-medium capitalize transition-colors border-b-2 ${
                                    isExecution
                                        ? 'border-accent text-text-primary'
                                        : 'border-transparent text-text-muted hover:text-text-secondary'
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
