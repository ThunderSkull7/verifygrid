import React, { useState } from 'react';
import { useAuth } from '../context/useAuth';
import { api } from '../services/api';
import {
  ShieldCheck,
  LogIn,
  UserPlus,
  AlertCircle,
  Eye,
  EyeOff,
  FileSpreadsheet,
  GitCompareArrows,
  FileCheck2,
} from 'lucide-react';
import { AppearanceControl } from './AppearanceControl';

interface AuthModalProps {
  initialMode?: 'login' | 'register';
  onSuccess?: () => void;
}

export const AuthScreen: React.FC<AuthModalProps> = ({ initialMode = 'login', onSuccess }) => {
  const [isLogin, setIsLogin] = useState<boolean>(initialMode === 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isLogin) {
        const res = await api.login({ email, password });
        login(res.access_token, res.user);
      } else {
        const res = await api.register({
          email,
          password,
          full_name: fullName.trim() || undefined,
        });
        login(res.access_token, res.user);
      }
      if (onSuccess) onSuccess();
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (toLogin: boolean) => {
    setIsLogin(toLogin);
    setError(null);
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-theme-toggle">
        <AppearanceControl variant="compact" />
      </div>

      <div className="auth-shell">
        <aside className="auth-hero">
          <div className="brand-icon">
            <ShieldCheck size={22} />
          </div>
          <h1>Audit-grade dataset reconciliation</h1>
          <p className="auth-hero-tagline">
            Compare source and target datasets, isolate discrepancies, and export defensible audit
            reports — all in one workspace.
          </p>
          <ul className="auth-features">
            <li>
              <span className="auth-feature-icon">
                <FileSpreadsheet size={14} />
              </span>
              Upload CSV or XLSX datasets with automatic schema inference
            </li>
            <li>
              <span className="auth-feature-icon">
                <GitCompareArrows size={14} />
              </span>
              Match records on composite keys with tolerance-aware rules
            </li>
            <li>
              <span className="auth-feature-icon">
                <FileCheck2 size={14} />
              </span>
              Persist audit runs and export CSV, Excel, and JSON reports
            </li>
          </ul>
          <span className="auth-hero-foot">VerifyGrid — verification you can defend.</span>
        </aside>

        <div className="auth-panel">
          <h2>{isLogin ? 'Welcome back' : 'Create your account'}</h2>
          <p className="auth-sub">
            {isLogin
              ? 'Sign in to access your verification projects and audit history.'
              : 'Start reconciling datasets with audit-grade precision.'}
          </p>

          {error && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate={false}>
            {!isLogin && (
              <div className="form-group">
                <label className="form-label" htmlFor="auth-fullname">
                  Full name <span className="text-dim">(optional)</span>
                </label>
                <input
                  id="auth-fullname"
                  type="text"
                  className="form-input"
                  placeholder="Jane Doe"
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
            )}

            <div className="form-group">
              <label className="form-label" htmlFor="auth-email">
                Email address
              </label>
              <input
                id="auth-email"
                type="email"
                required
                className="form-input"
                placeholder="analyst@company.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="auth-password">
                Password
              </label>
              <div className="input-with-action">
                <input
                  id="auth-password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={isLogin ? 1 : 8}
                  className="form-input"
                  placeholder={isLogin ? '••••••••' : 'Minimum 8 characters'}
                  autoComplete={isLogin ? 'current-password' : 'new-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="input-action-btn"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {!isLogin && (
                <span className="form-hint">Use at least 8 characters for your password.</span>
              )}
            </div>

            <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={loading}>
              {loading ? (
                <>
                  <span className="spinner on-primary" aria-hidden="true" />
                  {isLogin ? 'Signing in…' : 'Creating account…'}
                </>
              ) : isLogin ? (
                <>
                  <LogIn size={16} /> Sign in
                </>
              ) : (
                <>
                  <UserPlus size={16} /> Create account
                </>
              )}
            </button>
          </form>

          <div className="auth-switch">
            {isLogin ? (
              <>
                Don't have an account?{' '}
                <button type="button" onClick={() => switchMode(false)}>
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already registered?{' '}
                <button type="button" onClick={() => switchMode(true)}>
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
