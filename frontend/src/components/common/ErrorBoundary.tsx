import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertOctagon, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught component error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: '3rem 2rem',
            background: 'var(--bg-card)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '12px',
            margin: '2rem',
            textAlign: 'center',
          }}
        >
          <AlertOctagon size={48} color="#ef4444" style={{ marginBottom: '1rem' }} />
          <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem', color: 'var(--text-main)' }}>
            Something went wrong displaying this section
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1.5rem', fontFamily: 'var(--font-mono)' }}>
            {this.state.error?.message || 'An unhandled render exception occurred.'}
          </p>
          <button
            className="btn"
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <RefreshCw size={16} /> Reload Component
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
