import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('VerifyGrid Caught UI Error in ErrorBoundary:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          role="alert"
          aria-live="assertive"
          className="card"
          style={{
            margin: '32px auto',
            maxWidth: 640,
            padding: 32,
            textAlign: 'center',
            border: '1px solid var(--border-color)',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              backgroundColor: 'var(--danger-soft, rgba(239, 68, 68, 0.12))',
              color: 'var(--danger-text, #ef4444)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px auto',
            }}
          >
            <AlertTriangle size={28} />
          </div>
          <h2 style={{ margin: '0 0 8px 0', fontSize: '1.25rem', color: 'var(--text-main)' }}>
            Something went wrong
          </h2>
          <p style={{ margin: '0 0 20px 0', fontSize: '0.88rem', color: 'var(--text-muted)' }}>
            An unexpected error occurred while rendering this view. Your session data remains safe.
          </p>
          {this.state.error?.message && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: 'var(--radius-sm, 6px)',
                backgroundColor: 'var(--bg-subtle)',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.78rem',
                color: 'var(--danger-text, #ef4444)',
                textAlign: 'left',
                overflowX: 'auto',
                marginBottom: 20,
              }}
            >
              {this.state.error.message}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={this.handleReset}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <RotateCcw size={15} /> Try Again
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => window.location.reload()}
            >
              Reload Application
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
