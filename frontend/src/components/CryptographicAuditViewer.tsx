import React, { useCallback, useEffect, useState } from 'react';
import type { AuditEventResponse, AuditVerificationResponse } from '../types';
import { api } from '../services/api';
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Link as LinkIcon,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';

interface CryptographicAuditViewerProps {
  projectId: string;
  runId: string;
}

export const CryptographicAuditViewer: React.FC<CryptographicAuditViewerProps> = ({
  projectId,
  runId,
}) => {
  const [events, setEvents] = useState<AuditEventResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [verification, setVerification] = useState<AuditVerificationResponse | null>(null);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const [expandedPayloads, setExpandedPayloads] = useState<Set<string>>(new Set());

  const loadAuditTrail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAuditTrail(projectId, runId, 0, 100);
      setEvents(res.items);
    } catch (err: any) {
      setError(err.message || 'Failed to load audit trail.');
    } finally {
      setLoading(false);
    }
  }, [projectId, runId]);

  const handleVerifyChain = async () => {
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await api.verifyAuditChain(projectId, runId);
      setVerification(res);
    } catch (err: any) {
      setVerifyError(err.message || 'Chain verification failed.');
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadAuditTrail();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadAuditTrail]);

  const togglePayload = (eventId: string) => {
    setExpandedPayloads((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) next.delete(eventId);
      else next.add(eventId);
      return next;
    });
  };

  const getEventBadgeClass = (eventType: string) => {
    if (eventType.includes('APPROVED')) return 'badge-success';
    if (eventType.includes('REJECTED')) return 'badge-danger';
    if (eventType.includes('PROPOSED') || eventType.includes('COUNTERSIGNED')) return 'badge-accent';
    if (eventType.includes('EXECUTED')) return 'badge-neutral';
    return 'badge';
  };

  return (
    <div className="card" style={{ padding: '20px', border: '1px solid var(--border-color)', marginTop: 20 }}>
      {/* Header & Verification Controls */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div>
          <h4 style={{ margin: 0, fontSize: '1.05rem', display: 'flex', alignItems: 'center', gap: 8 }}>
            <LinkIcon size={18} className="text-accent" /> Cryptographic Audit Trail &amp; Hash Chain
          </h4>
          <p className="text-dim" style={{ margin: '4px 0 0', fontSize: '0.8rem' }}>
            Append-only tamper-evident event log chained via SHA-256 cryptographic hashes from genesis seed.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void loadAuditTrail()}
            disabled={loading}
            title="Refresh events"
          >
            <RefreshCw size={13} className={loading ? 'spinner' : ''} /> Refresh
          </button>

          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => void handleVerifyChain()}
            disabled={verifying}
          >
            {verifying ? (
              <span className="spinner" />
            ) : (
              <ShieldCheck size={14} />
            )}
            Verify Audit Chain
          </button>
        </div>
      </div>

      {/* Verification Live Status Banner */}
      {verifyError && (
        <div className="alert alert-error" style={{ marginBottom: 14 }}>
          <AlertCircle size={16} />
          <span>{verifyError}</span>
        </div>
      )}

      {verification && (
        <div
          className={`alert ${verification.is_valid ? 'alert-success' : 'alert-error'}`}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            marginBottom: 16,
            padding: '12px 16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {verification.is_valid ? (
              <ShieldCheck size={20} className="text-success" />
            ) : (
              <ShieldAlert size={20} className="text-danger" />
            )}
            <strong style={{ fontSize: '0.92rem' }}>
              {verification.is_valid
                ? 'Tamper-Evident Verification: Chain 100% Valid & Unbroken'
                : 'SECURITY ALERT: Audit Chain Tampering Detected!'}
            </strong>
            <span
              className={`badge ${verification.is_valid ? 'badge-success' : 'badge-danger'}`}
              style={{ fontSize: '0.72rem', marginLeft: 'auto' }}
            >
              {verification.status}
            </span>
          </div>

          <div style={{ fontSize: '0.8rem', color: 'var(--text-main)', opacity: 0.9 }}>
            {verification.message}
          </div>

          {verification.head_hash && (
            <div style={{ fontSize: '0.74rem', fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>
              <strong>Head Hash:</strong> {verification.head_hash}
            </div>
          )}

          {verification.broken_link && (
            <div
              style={{
                marginTop: 6,
                padding: '8px 10px',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                borderRadius: 'var(--radius-xs)',
                fontSize: '0.78rem',
              }}
            >
              <div><strong>Broken Sequence #:</strong> {verification.broken_link.sequence_number} ({verification.broken_link.event_id})</div>
              <div><strong>Diagnostic Reason:</strong> {verification.broken_link.reason}</div>
              <div><strong>Expected Hash:</strong> <code>{verification.broken_link.expected_hash}</code></div>
              <div><strong>Actual Found:</strong> <code>{verification.broken_link.actual_hash}</code></div>
            </div>
          )}
        </div>
      )}

      {/* Events List */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)' }}>
          <span className="spinner" /> Loading cryptographic event chain...
        </div>
      ) : error ? (
        <div className="alert alert-error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      ) : events.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)', fontSize: '0.85rem' }}>
          No audit events recorded for this run yet. Run execution and review actions will appear here.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {events.map((evt) => {
            const isExpanded = expandedPayloads.has(evt.event_id);
            const isGenesis = evt.sequence_number === 1;

            return (
              <div
                key={evt.id}
                style={{
                  backgroundColor: 'var(--bg-card)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '12px 14px',
                  position: 'relative',
                }}
              >
                {/* Event Top Bar */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        backgroundColor: 'var(--bg-card-hover)',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-xs)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                      }}
                    >
                      #{evt.sequence_number}
                    </span>
                    <span className={`badge ${getEventBadgeClass(evt.event_type)}`} style={{ fontSize: '0.74rem' }}>
                      {evt.event_type}
                    </span>
                    <span style={{ fontSize: '0.74rem', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>
                      {evt.event_id}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.76rem', color: 'var(--text-dim)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <UserCheck size={13} />
                      <span>{evt.user_email || 'System'} ({evt.user_role})</span>
                    </div>
                    <span>{new Date(evt.timestamp_utc).toLocaleString()}</span>
                  </div>
                </div>

                {/* Hash Linkage Details */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 8,
                    fontSize: '0.72rem',
                    fontFamily: 'var(--font-mono)',
                    backgroundColor: 'var(--bg-subtle)',
                    padding: '8px 10px',
                    borderRadius: 'var(--radius-xs)',
                    marginBottom: 8,
                  }}
                >
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Prev Hash: </span>
                    <span title={evt.previous_event_hash}>
                      {isGenesis ? '0x0000... (GENESIS SEED)' : `${evt.previous_event_hash.slice(0, 16)}...`}
                    </span>
                  </div>
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Event Hash: </span>
                    <span className="text-accent" title={evt.current_event_hash}>
                      {evt.current_event_hash.slice(0, 16)}...{evt.current_event_hash.slice(-8)}
                    </span>
                  </div>
                </div>

                {/* Collapsible Canonical Payload */}
                <div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ padding: '2px 6px', fontSize: '0.74rem' }}
                    onClick={() => togglePayload(evt.event_id)}
                  >
                    {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    {isExpanded ? 'Hide Event Payload' : 'Inspect Canonical Payload'}
                  </button>

                  {isExpanded && (
                    <pre
                      style={{
                        margin: '8px 0 0',
                        padding: '10px 12px',
                        backgroundColor: 'var(--bg-secondary)',
                        borderRadius: 'var(--radius-xs)',
                        fontSize: '0.74rem',
                        fontFamily: 'var(--font-mono)',
                        maxHeight: 180,
                        overflowY: 'auto',
                      }}
                    >
                      {JSON.stringify(evt.event_payload, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
