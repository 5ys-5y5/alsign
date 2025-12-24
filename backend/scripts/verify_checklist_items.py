"""
Verify checklist items against actual database state.
Checks if SQL changes from apply_issue_docs_changes.sql have been applied.
"""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import settings


async def verify_database_state():
    """Verify checklist items against database."""
    
    print("=" * 80)
    print("📋 AlSign 체크리스트 DB 반영 상태 확인")
    print("=" * 80)
    print()
    
    try:
        # Connect to database
        print("🔌 DB 연결 중...")
        conn = await asyncpg.connect(
            dsn=settings.DATABASE_URL,
            statement_cache_size=0,
            server_settings={'application_name': 'verify_checklist'}
        )
        print("✅ DB 연결 성공")
        print()
        
        # Check 1: config_lv2_metric table exists
        print("-" * 80)
        print("1️⃣  테이블 존재 확인: config_lv2_metric")
        print("-" * 80)
        
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'config_lv2_metric'
            )
        """)
        
        if table_exists:
            print("✅ config_lv2_metric 테이블 존재")
            
            # Get total count
            total_count = await conn.fetchval(
                "SELECT COUNT(*) FROM config_lv2_metric"
            )
            print(f"   총 {total_count}개 메트릭 정의됨")
        else:
            print("❌ config_lv2_metric 테이블 없음")
            print("   ⚠️  setup_supabase.sql 실행 필요")
            await conn.close()
            return
        
        print()
        
        # Check 2: I-01 consensusSignal configuration
        print("-" * 80)
        print("2️⃣  I-01: consensusSignal 설정 확인")
        print("-" * 80)
        
        consensus_signal = await conn.fetchrow("""
            SELECT id, source, expression, aggregation_kind, 
                   aggregation_params, base_metric_id, domain
            FROM config_lv2_metric
            WHERE id = 'consensusSignal'
        """)
        
        if consensus_signal:
            print("✅ consensusSignal 메트릭 존재")
            print(f"   - source: {consensus_signal['source']}")
            print(f"   - expression: {consensus_signal['expression']}")
            print(f"   - aggregation_kind: {consensus_signal['aggregation_kind']}")
            print(f"   - base_metric_id: {consensus_signal['base_metric_id']}")
            print(f"   - domain: {consensus_signal['domain']}")
            
            # Verify expected changes from apply_issue_docs_changes.sql
            issues = []
            
            if consensus_signal['source'] == 'aggregation':
                print("   ✅ source = 'aggregation' (변경 적용됨)")
            else:
                print(f"   ❌ source = '{consensus_signal['source']}' (예상: 'aggregation')")
                issues.append("source not updated")
            
            if consensus_signal['expression'] is None:
                print("   ✅ expression = NULL (변경 적용됨)")
            else:
                print(f"   ❌ expression = '{consensus_signal['expression']}' (예상: NULL)")
                issues.append("expression not NULL")
            
            if consensus_signal['aggregation_kind'] == 'leadPairFromList':
                print("   ✅ aggregation_kind = 'leadPairFromList' (변경 적용됨)")
            else:
                print(f"   ⚠️  aggregation_kind = '{consensus_signal['aggregation_kind']}' (예상: 'leadPairFromList')")
                issues.append("aggregation_kind not set")
            
            if issues:
                print()
                print("   🔴 apply_issue_docs_changes.sql 미실행 또는 부분 실행됨")
            else:
                print()
                print("   ✅ I-01 SQL 변경사항 모두 적용됨")
        else:
            print("❌ consensusSignal 메트릭 없음")
        
        print()
        
        # Check 3: I-05 consensus metric
        print("-" * 80)
        print("3️⃣  I-05: consensus 메트릭 추가 확인")
        print("-" * 80)
        
        consensus = await conn.fetchrow("""
            SELECT id, source, api_list_id, domain, 
                   response_key
            FROM config_lv2_metric
            WHERE id = 'consensus'
        """)
        
        if consensus:
            print("✅ consensus 메트릭 존재")
            print(f"   - source: {consensus['source']}")
            print(f"   - api_list_id: {consensus['api_list_id']}")
            print(f"   - domain: {consensus['domain']}")
            
            if consensus['response_key']:
                # Handle both dict and string types
                if isinstance(consensus['response_key'], dict):
                    response_keys = list(consensus['response_key'].keys())
                    print(f"   - response_key 필드 수: {len(response_keys)}")
                    print(f"   - response_key 필드: {', '.join(response_keys[:5])}...")
                elif isinstance(consensus['response_key'], str):
                    import json
                    try:
                        response_key_dict = json.loads(consensus['response_key'])
                        response_keys = list(response_key_dict.keys())
                        print(f"   - response_key 필드 수: {len(response_keys)}")
                        print(f"   - response_key 필드: {', '.join(response_keys[:5])}...")
                    except:
                        print(f"   - response_key: (string 형태로 저장됨)")
            
            if consensus['source'] == 'api_field' and consensus['api_list_id'] == 'fmp-price-target':
                print()
                print("   ✅ I-05 SQL 변경사항 적용됨")
            else:
                print()
                print("   ⚠️  설정이 예상과 다름")
        else:
            print("❌ consensus 메트릭 없음")
            print("   🔴 apply_issue_docs_changes.sql 미실행")
        
        print()
        
        # Check 4: Other qualitative metrics
        print("-" * 80)
        print("4️⃣  qualatative-* 도메인 메트릭 현황")
        print("-" * 80)
        
        qual_metrics = await conn.fetch("""
            SELECT id, domain, source
            FROM config_lv2_metric
            WHERE domain LIKE 'qualatative-%'
            ORDER BY domain, id
        """)
        
        if qual_metrics:
            print(f"✅ {len(qual_metrics)}개 qualatative 메트릭 발견:")
            
            by_domain = {}
            for metric in qual_metrics:
                domain = metric['domain']
                if domain not in by_domain:
                    by_domain[domain] = []
                by_domain[domain].append(metric['id'])
            
            for domain in sorted(by_domain.keys()):
                metrics_in_domain = by_domain[domain]
                print(f"   - {domain}: {', '.join(metrics_in_domain)}")
        else:
            print("⚠️  qualatative 메트릭 없음")
        
        print()
        
        # Check 5: Config policies
        print("-" * 80)
        print("5️⃣  config_lv0_policy 테이블 확인")
        print("-" * 80)
        
        policy_table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'config_lv0_policy'
            )
        """)
        
        if policy_table_exists:
            policies = await conn.fetch("""
                SELECT function, policy
                FROM config_lv0_policy
                ORDER BY function
            """)
            
            print(f"✅ config_lv0_policy 테이블 존재 ({len(policies)}개 정책)")
            
            for policy in policies:
                print(f"   - {policy['function']}")
            
            # Check for priceEodOHLC_dateRange policy (I-10)
            has_ohlc_policy = any(p['function'] == 'priceEodOHLC_dateRange' for p in policies)
            if has_ohlc_policy:
                print()
                print("   ✅ priceEodOHLC_dateRange 정책 존재 (I-10 관련)")
            else:
                print()
                print("   ⚠️  priceEodOHLC_dateRange 정책 없음 (I-10: 미반영)")
        else:
            print("❌ config_lv0_policy 테이블 없음")
        
        print()
        
        # Summary
        print("=" * 80)
        print("📊 요약")
        print("=" * 80)
        
        if consensus_signal and consensus_signal['source'] == 'aggregation':
            print("✅ I-01: consensusSignal 설정 - SQL 변경 적용됨")
        else:
            print("🔴 I-01: consensusSignal 설정 - SQL 실행 필요")
        
        if consensus:
            print("✅ I-05: consensus 메트릭 - 추가됨")
        else:
            print("🔴 I-05: consensus 메트릭 - SQL 실행 필요")
        
        print()
        print("💡 다음 단계:")
        if not (consensus_signal and consensus_signal['source'] == 'aggregation') or not consensus:
            print("   1. Supabase Dashboard SQL Editor 접속")
            print("   2. backend/scripts/apply_issue_docs_changes.sql 실행")
            print("   3. 이 스크립트 재실행하여 확인")
        else:
            print("   1. Python 코드 변경사항 확인 (I-03, I-07, I-08, I-09)")
            print("   2. 미반영 항목 구현 (I-10, I-11)")
        
        print()
        
        # Close connection
        await conn.close()
        print("✅ DB 연결 종료")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(verify_database_state())

