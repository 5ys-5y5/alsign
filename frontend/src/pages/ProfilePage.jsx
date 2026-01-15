/**
 * ProfilePage Component
 *
 * Manage password and subscription details.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { supabase } from '../services/supabaseClient';
import { useAuth } from '../contexts/AuthContext';

export default function ProfilePage() {
  const { user, loading, isAuthenticated, refreshProfile } = useAuth();
  const [profile, setProfile] = useState(null);
  const [paymentHistory, setPaymentHistory] = useState([]);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState(null);

  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [passwordStatus, setPasswordStatus] = useState(null);
  const [profileManageOpen, setProfileManageOpen] = useState(false);

  const [subscriptionStatus, setSubscriptionStatus] = useState(null);
  const [billingOpen, setBillingOpen] = useState(false);
  const [billingForm, setBillingForm] = useState({
    planName: '',
    priceMonthly: '',
    nextBillingDate: '',
    cardBrand: '',
    cardLast4: '',
    billingName: '',
    billingAddress: '',
  });

  const currentPayment = useMemo(() => {
    return paymentHistory.find((entry) => entry.status === 'active') || paymentHistory[0] || null;
  }, [paymentHistory]);

  const formatKoreanDate = (value) => {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  useEffect(() => {
    let mounted = true;

    const loadProfile = async () => {
      if (!user?.id) {
        if (mounted) {
          setProfile(null);
          setPaymentHistory([]);
          setProfileLoading(false);
        }
        return;
      }

      setProfileLoading(true);
      setProfileError(null);
      const { data, error } = await supabase
        .from('user_profiles')
        .select('is_paying,subscription_expires_at')
        .eq('user_id', user.id)
        .maybeSingle();

      const { data: paymentData } = await supabase
        .from('user_payments')
        .select('id,status,start_at,end_at,canceled_at')
        .eq('user_id', user.id)
        .order('start_at', { ascending: false })
        .limit(20);

      if (!mounted) return;
      if (error) {
        setProfileError(error.message || 'Failed to load profile.');
        setProfile(null);
        setPaymentHistory([]);
      } else {
        setProfile(data || null);
        setPaymentHistory(paymentData || []);
      }
      setProfileLoading(false);
    };

    loadProfile();

    return () => {
      mounted = false;
    };
  }, [user?.id]);

  const handlePasswordUpdate = async (event) => {
    event.preventDefault();
    setPasswordStatus(null);

    if (!password || password.length < 6) {
      setPasswordStatus({ type: 'error', message: '비밀번호는 6자 이상이어야 합니다.' });
      return;
    }
    if (password !== passwordConfirm) {
      setPasswordStatus({ type: 'error', message: '비밀번호가 일치하지 않습니다.' });
      return;
    }

    const { error } = await supabase.auth.updateUser({ password });
    if (error) {
      setPasswordStatus({ type: 'error', message: error.message || '비밀번호 변경에 실패했습니다.' });
      return;
    }

    setPassword('');
    setPasswordConfirm('');
    setPasswordStatus({ type: 'success', message: '비밀번호가 변경되었습니다.' });
  };

  const handleStartSubscription = async () => {
    setSubscriptionStatus(null);
    const startAt = new Date();
    const expiresAt = new Date(startAt);
    expiresAt.setMonth(expiresAt.getMonth() + 1);
    const expiresAtIso = expiresAt.toISOString();
    const { data, error } = await supabase
      .from('user_profiles')
      .update({
        is_paying: true,
        subscription_expires_at: expiresAtIso,
      })
      .eq('user_id', user.id)
      .select('is_paying,subscription_expires_at')
      .single();

    if (error) {
      setSubscriptionStatus({ type: 'error', message: error.message || '구독 시작에 실패했습니다.' });
      return;
    }

    const { error: insertError } = await supabase
      .from('user_payments')
      .insert({
        user_id: user.id,
        status: 'active',
        start_at: startAt.toISOString(),
        end_at: expiresAtIso,
      });

    if (insertError) {
      setSubscriptionStatus({ type: 'error', message: insertError.message || '결제 기록 저장에 실패했습니다.' });
      return;
    }

    setProfile(data);
    setPaymentHistory((prev) => ([
      {
        status: 'active',
        start_at: startAt.toISOString(),
        end_at: expiresAtIso,
        canceled_at: null,
      },
      ...prev,
    ]));
    setBillingOpen(false);
    setBillingForm({
      planName: '',
      priceMonthly: '',
      nextBillingDate: '',
      cardBrand: '',
      cardLast4: '',
      billingName: '',
      billingAddress: '',
    });
    await refreshProfile();
    setSubscriptionStatus({ type: 'success', message: '구독이 시작되었습니다.' });
  };

  const handleBillingFieldChange = (field) => (event) => {
    setBillingForm((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const handleBillingToggle = () => {
    setBillingOpen((prev) => !prev);
    setSubscriptionStatus(null);
  };

  const handleBillingCancel = async () => {
    setSubscriptionStatus(null);
    const nowIso = new Date().toISOString();
    const { data, error } = await supabase
      .from('user_profiles')
      .update({
        is_paying: false,
        subscription_expires_at: null,
      })
      .eq('user_id', user.id)
      .select('is_paying,subscription_expires_at')
      .single();

    if (error) {
      setSubscriptionStatus({ type: 'error', message: error.message || '구독 해지에 실패했습니다.' });
      return;
    }

    const { error: updateError } = await supabase
      .from('user_payments')
      .update({
        status: 'canceled',
        canceled_at: nowIso,
        end_at: nowIso,
      })
      .eq('user_id', user.id)
      .eq('status', 'active');

    if (updateError) {
      setSubscriptionStatus({ type: 'error', message: updateError.message || '결제 기록 업데이트에 실패했습니다.' });
      return;
    }

    setProfile(data);
    setPaymentHistory((prev) => prev.map((entry) => (
      entry.status === 'active'
        ? { ...entry, status: 'canceled', canceled_at: nowIso, end_at: nowIso }
        : entry
    )));
    await refreshProfile();
    setSubscriptionStatus({ type: 'success', message: '구독이 해지되었습니다.' });
  };

  const handleBillingStart = async () => {
    await handleStartSubscription();
  };

  const handleBillingReset = () => {
    setBillingForm({
      planName: '',
      priceMonthly: '',
      nextBillingDate: '',
      cardBrand: '',
      cardLast4: '',
      billingName: '',
      billingAddress: '',
    });
  };

  if (loading || profileLoading) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div style={{ padding: 'var(--space-4)' }}>
        <div className="alert alert-warning">로그인이 필요합니다.</div>
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
      <section
        style={{
          backgroundColor: 'white',
          border: '1px solid var(--border)',
          borderRadius: 'var(--rounded-lg)',
          padding: 'var(--space-4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
          <h2 style={{ marginTop: 0, marginBottom: 0 }}>프로필</h2>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="btn btn-sm btn-outline"
              onClick={() => setProfileManageOpen((prev) => !prev)}
              style={{ width: '96px' }}
            >
              관리
            </button>
          </div>
        </div>
        <div style={{ marginTop: 'var(--space-2)', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
          {user?.email || 'Unknown email'}
        </div>
        {profileError && (
          <div className="alert alert-error" style={{ marginTop: 'var(--space-3)' }}>
            {profileError}
          </div>
        )}
        {profileManageOpen && (
          <>
            <div style={{ borderTop: '1px solid var(--border)', margin: 'var(--space-3) 0' }} />
            <div style={{ display: 'grid', gap: 'var(--space-2)', maxWidth: '420px' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)' }}>비밀번호 변경</div>
              <form onSubmit={handlePasswordUpdate} style={{ display: 'grid', gap: 'var(--space-2)' }}>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="새 비밀번호"
                  minLength={6}
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
                <input
                  type="password"
                  value={passwordConfirm}
                  onChange={(event) => setPasswordConfirm(event.target.value)}
                  placeholder="새 비밀번호 확인"
                  minLength={6}
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
                <button type="submit" className="btn btn-sm btn-primary" style={{ width: '140px' }}>
                  변경하기
                </button>
              </form>
              {passwordStatus && (
                <div className={`alert ${passwordStatus.type === 'error' ? 'alert-error' : 'alert-success'}`} style={{ marginTop: 'var(--space-3)' }}>
                  {passwordStatus.message}
                </div>
              )}
            </div>
          </>
        )}
      </section>

      <section
        style={{
          backgroundColor: 'white',
          border: '1px solid var(--border)',
          borderRadius: 'var(--rounded-lg)',
          padding: 'var(--space-4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
          <h2 style={{ marginTop: 0, marginBottom: 0 }}>구독 관리</h2>
          <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
            {profile?.is_paying ? (
              <>
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={handleBillingToggle}
                  style={{ width: '96px' }}
                >
                  결제 관리
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={handleBillingCancel}
                  style={{ width: '96px' }}
                >
                  구독 해지
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={handleBillingToggle}
                style={{ width: '96px' }}
              >
                구독 시작
              </button>
            )}
          </div>
        </div>

        {profile?.subscription_expires_at && (
          <div style={{ marginTop: 'var(--space-2)', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            {formatKoreanDate(profile.subscription_expires_at)} 플랜이 자동 갱신됩니다.
          </div>
        )}

        {billingOpen && (
          <div style={{ marginTop: 'var(--space-3)', display: 'grid', gap: 'var(--space-3)' }}>
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)', marginBottom: 'var(--space-2)' }}>
                결제 정보
              </div>
              <div style={{ display: 'grid', gap: 'var(--space-2)', maxWidth: '520px' }}>
                <input
                  type="text"
                  value={billingForm.planName}
                  onChange={handleBillingFieldChange('planName')}
                  placeholder="구독 플랜명"
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
                <input
                  type="text"
                  value={billingForm.priceMonthly}
                  onChange={handleBillingFieldChange('priceMonthly')}
                  placeholder="월 결제 금액"
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
                <input
                  type="text"
                  value={billingForm.nextBillingDate}
                  onChange={handleBillingFieldChange('nextBillingDate')}
                  placeholder="다음 청구일"
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)', marginBottom: 'var(--space-2)' }}>
                결제 방식
              </div>
              <div style={{ display: 'grid', gap: 'var(--space-2)', maxWidth: '520px' }}>
                <input
                  type="text"
                  value={billingForm.cardBrand}
                  onChange={handleBillingFieldChange('cardBrand')}
                  placeholder="카드 브랜드"
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
                <input
                  type="text"
                  value={billingForm.cardLast4}
                  onChange={handleBillingFieldChange('cardLast4')}
                  placeholder="카드 끝 4자리"
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)', marginBottom: 'var(--space-2)' }}>
                청구 정보
              </div>
              <div style={{ display: 'grid', gap: 'var(--space-2)', maxWidth: '520px' }}>
                <input
                  type="text"
                  value={billingForm.billingName}
                  onChange={handleBillingFieldChange('billingName')}
                  placeholder="이름"
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
                <input
                  type="text"
                  value={billingForm.billingAddress}
                  onChange={handleBillingFieldChange('billingAddress')}
                  placeholder="청구 주소"
                  style={{
                    width: '100%',
                    backgroundColor: '#f8fafc',
                    border: '1px solid var(--border)',
                    borderRadius: '12px',
                    padding: '10px 14px',
                    color: 'var(--text)',
                    fontSize: 'var(--text-sm)',
                  }}
                />
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--font-medium)', marginBottom: 'var(--space-2)' }}>
                청구서 내역
              </div>
              {paymentHistory.length === 0 ? (
                <div style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
                  결제 내역이 없습니다.
                </div>
              ) : (
                <div style={{ display: 'grid', gap: '8px' }}>
                  {paymentHistory.map((entry) => (
                    <div
                      key={entry.id || `${entry.status}-${entry.start_at}`}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '160px 1fr 120px',
                        gap: 'var(--space-2)',
                        alignItems: 'center',
                        padding: '10px 12px',
                        border: '1px solid var(--border)',
                        borderRadius: '12px',
                        backgroundColor: '#ffffff',
                      }}
                    >
                      <div style={{ fontSize: 'var(--text-sm)' }}>
                        {formatKoreanDate(entry.start_at) || '-'}
                      </div>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                        {entry.end_at ? `${formatKoreanDate(entry.start_at)} ~ ${formatKoreanDate(entry.end_at)}` : '기간 정보 없음'}
                      </div>
                      <div style={{ fontSize: 'var(--text-sm)', textAlign: 'right' }}>
                        {entry.status === 'active' ? '결제됨' : entry.status === 'canceled' ? '취소됨' : entry.status}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              {!profile?.is_paying ? (
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  onClick={handleBillingStart}
                >
                  구독 시작
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-sm btn-outline"
                  onClick={handleBillingCancel}
                >
                  구독 해지
                </button>
              )}
              <button
                type="button"
                className="btn btn-sm btn-outline"
                onClick={handleBillingReset}
              >
                입력 초기화
              </button>
            </div>
          </div>
        )}

        {currentPayment && (
          <div style={{ marginTop: 'var(--space-3)', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
            다음 청구일: {formatKoreanDate(currentPayment.end_at) || '-'}
          </div>
        )}

        {subscriptionStatus && (
          <div className={`alert ${subscriptionStatus.type === 'error' ? 'alert-error' : 'alert-success'}`} style={{ marginTop: 'var(--space-3)' }}>
            {subscriptionStatus.message}
          </div>
        )}
      </section>
    </div>
  );
}
