/**
 * AuthModal Component
 *
 * ChatGPT-style login/signup modal for Supabase authentication.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { supabase } from '../services/supabaseClient';
import { useAuth } from '../contexts/AuthContext';

export default function AuthModal({ isOpen, onClose, nextHash }) {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    if (!loading && isAuthenticated) {
      if (nextHash) {
        window.location.hash = nextHash;
      } else {
        window.location.hash = '#/trades';
      }
      onClose();
    }
  }, [isOpen, loading, isAuthenticated, nextHash, onClose]);

  useEffect(() => {
    if (!isOpen) {
      setStatus(null);
      setSubmitting(false);
    }
  }, [isOpen]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setStatus(null);

    try {
      if (mode === 'login') {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        setStatus({ type: 'success', message: '로그인 완료. 이동 중...' });
      } else {
        const { error } = await supabase.auth.signUp({ email, password });
        if (error) throw error;
        setStatus({ type: 'success', message: '가입 완료. 이메일 확인이 필요할 수 있습니다.' });
      }
    } catch (error) {
      setStatus({ type: 'error', message: error.message || '인증에 실패했습니다.' });
    } finally {
      setSubmitting(false);
    }
  };

  const modalTitle = mode === 'login' ? '로그인 또는 회원 가입' : '회원 가입';
  const modalSubtitle = mode === 'login'
    ? '로그인하고 최근 30일 성과 확인하기'
    : '가입 후 이메일 인증을 완료하세요.';

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(15, 23, 42, 0.25)',
      backdropFilter: 'blur(6px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 'var(--space-4)',
      zIndex: 1200,
    }}>
      <div style={{
        width: '100%',
        maxWidth: '420px',
        backgroundColor: '#ffffff',
        borderRadius: '20px',
        border: '1px solid var(--border)',
        boxShadow: '0 30px 80px rgba(15, 23, 42, 0.15)',
        padding: '24px',
        color: 'var(--text)',
        position: 'relative',
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '20px',
            right: '20px',
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            background: '#f8fafc',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            fontSize: '18px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          aria-label="Close"
        >
          X
        </button>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '30px', marginBottom: '30px' }}>
          <h2 style={{ margin: 0, fontSize: 'var(--text-lg)' }}>{modalTitle}</h2>
          <p style={{ margin: 0, color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            {modalSubtitle}
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            placeholder="이메일 주소"
            style={{
              width: '100%',
              backgroundColor: '#f8fafc',
              border: '1px solid var(--border)',
              borderRadius: '999px',
              padding: '12px 16px',
              color: 'var(--text)',
              fontSize: 'var(--text-sm)',
            }}
          />

          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            placeholder="비밀번호"
            minLength={6}
            style={{
              width: '100%',
              backgroundColor: '#f8fafc',
              border: '1px solid var(--border)',
              borderRadius: '999px',
              padding: '12px 16px',
              color: 'var(--text)',
              fontSize: 'var(--text-sm)',
              marginTop: '12px',
            }}
          />

          <button
            type="submit"
            disabled={submitting}
            style={{
              width: '100%',
              marginTop: '18px',
              borderRadius: '999px',
              border: 'none',
              padding: '12px 16px',
              backgroundColor: '#111827',
              color: '#f9fafb',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--font-semibold)',
              cursor: submitting ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? '처리 중...' : mode === 'login' ? '로그인' : '가입 완료'}
          </button>
        </form>

        {status && (
          <div
            className={`alert ${status.type === 'error' ? 'alert-error' : 'alert-success'}`}
            style={{ marginTop: 'var(--space-3)' }}
          >
            {status.message}
          </div>
        )}

        <div style={{ marginTop: 'var(--space-3)', textAlign: 'center' }}>
          {mode === 'login' ? (
            <button
              type="button"
              onClick={() => setMode('signup')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--accent-primary)',
                fontSize: 'var(--text-sm)',
                cursor: 'pointer',
              }}
            >
              계정 만들기
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setMode('login')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--accent-primary)',
                fontSize: 'var(--text-sm)',
                cursor: 'pointer',
              }}
            >
              이미 계정이 있습니다
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
