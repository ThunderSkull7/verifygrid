import React, { useState } from 'react';
import { useAuth } from '../context/useAuth';
import { api } from '../services/api';
import { ShieldCheck, LogIn, UserPlus } from 'lucide-react';

interface AuthModalProps {
  initialMode?: 'login' | 'register';
  onSuccess?: () => void;
}

export const AuthScreen: React.FC<AuthModalProps> = ({ initialMode = 'login', onSuccess }) => {
  const [isLogin, setIsLogin] = useState<boolean>(initialMode === 'login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
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

  return (
    <div className="auth-wrapper">
      <div className="auth-card">
        <div className="auth-header">
          <div style={{ display: 'inline-flex', marginBottom: 12 }} className="brand-icon">
            <ShieldCheck size={24} />
          </div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: 6 }}>
            {isLogin ? 'Sign in to VerifyGrid' : 'Create an Account'}
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            {isLogin
              ? 'Enter your credentials to access your verification projects'
              : 'Start reconciling datasets with audit-grade precision'}
          </p>
        </div>

        {error && (
          <div className="alert-box alert-error">
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {!isLogin && (
            <div className="form-group">
              <label className="form-label">Full Name (Optional)</label>
              <input
                type="text"
                className="form-input"
                placeholder="Jane Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input
              type="email"
              required
              className="form-input"
              placeholder="analyst@verifygrid.io"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              type="password"
              required
              minLength={isLogin ? 1 : 8}
              className="form-input"
              placeholder={isLogin ? '••••••••' : 'Min 8 characters'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', marginTop: 8 }}
            disabled={loading}
          >
            {loading ? (
              'Processing...'
            ) : isLogin ? (
              <>
                <LogIn size={16} /> Sign In
              </>
            ) : (
              <>
                <UserPlus size={16} /> Create Account
              </>
            )}
          </button>
        </form>

        <div style={{ marginTop: 24, textAlign: 'center', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          {isLogin ? (
            <>
              Don't have an account?{' '}
              <button
                type="button"
                style={{ color: 'var(--primary)', fontWeight: 600 }}
                onClick={() => {
                  setIsLogin(false);
                  setError(null);
                }}
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already registered?{' '}
              <button
                type="button"
                style={{ color: 'var(--primary)', fontWeight: 600 }}
                onClick={() => {
                  setIsLogin(true);
                  setError(null);
                }}
              >
                Sign in
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
