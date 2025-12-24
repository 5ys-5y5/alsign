# 📝 가이드라인 검증 후 발견된 이슈 상세도

> 이 문서는 발견된 이슈들의 상세한 코드 수정 방법을 기록합니다.

---

## I-NEW-01: consensusSignal 하드코딩 → 동적 계산 전환 (미반영)

### 현재 문제가 있는 코드

**파일**: `backend/src/services/valuation_service.py`

**문제 코드** (라인 578-727):
```python
async def calculate_qualitative_metrics(
    pool,
    ticker: str,
    event_date,
    source: str,
    source_id: str
) -> Dict[str, Any]:
    """Calculate qualitative metrics (consensusSignal, targetMedian, consensusSummary)."""
    
    # ... 생략 ...
    
    # ❌ 문제: 하드코딩된 consensusSignal 생성 (라인 638-667)
    consensus_signal = {
        'direction': direction,
        'last': {
            'price_target': float(price_target) if price_target else None,
            'price_when_posted': float(price_when_posted) if price_when_posted else None
        }
    }
    
    # Add prev and delta if available
    if price_target_prev is not None and price_when_posted_prev is not None:
        consensus_signal['prev'] = {
            'price_target': float(price_target_prev),
            'price_when_posted': float(price_when_posted_prev)
        }
        
        # Calculate delta and deltaPct
        if price_target and price_target_prev:
            delta = float(price_target) - float(price_target_prev)
            delta_pct = (delta / float(price_target_prev)) * 100 if price_target_prev != 0 else None
            
            consensus_signal['delta'] = delta
            consensus_signal['deltaPct'] = delta_pct
        else:
            consensus_signal['delta'] = None
            consensus_signal['deltaPct'] = None
    else:
        consensus_signal['prev'] = None
        consensus_signal['delta'] = None
        consensus_signal['deltaPct'] = None
```

**왜 문제인가?**:
1. DB에 consensusSignal 메트릭이 `aggregation` 타입으로 정의되어 있음
2. `aggregation_kind = 'leadPairFromList'`로 설정되어 있음
3. `_lead_pair_from_list()` 메서드가 구현되어 있으나 사용하지 않음
4. 가이드라인 위반: "계산 로직 하드코딩 금지"

---

### 적용해야 할 코드

**파일**: `backend/src/services/valuation_service.py`

**수정 방법 1: MetricCalculationEngine 사용**

```python
async def calculate_qualitative_metrics(
    pool,
    ticker: str,
    event_date,
    source: str,
    source_id: str
) -> Dict[str, Any]:
    """
    Calculate qualitative metrics using MetricCalculationEngine.
    
    Uses dynamic metric calculation from config_lv2_metric definitions.
    """
    try:
        # Only calculate for consensus events
        if source != 'consensus':
            return {
                'status': 'skipped',
                'value': None,
                'currentPrice': None,
                'message': 'Not a consensus event'
            }
        
        # ✅ 수정: MetricCalculationEngine으로 동적 계산
        from .metric_engine import MetricCalculationEngine
        from ..database.queries import metrics as metrics_queries, consensus as consensus_queries
        
        # 1. Load consensusSignal metric definition
        consensus_signal_metrics = await metrics_queries.select_metrics_by_domains(
            pool,
            ['consensusSignal']
        )
        
        if not consensus_signal_metrics:
            return {
                'status': 'failed',
                'value': None,
                'currentPrice': None,
                'message': 'consensusSignal metric not defined in config_lv2_metric'
            }
        
        # 2. Load evt_consensus data for this partition
        # Get all consensus events for (ticker, analyst_name, analyst_company)
        # to feed into leadPairFromList aggregation
        consensus_data = await metrics_queries.select_consensus_data(
            pool, ticker, event_date, source_id
        )
        
        if not consensus_data:
            return {
                'status': 'failed',
                'value': None,
                'currentPrice': None,
                'message': f'Consensus data not found for source_id={source_id}'
            }
        
        # Get analyst info for partition
        analyst_name = consensus_data.get('analyst_name')
        analyst_company = consensus_data.get('analyst_company')
        
        # Load all events for this partition (for leadPairFromList)
        partition_events = await consensus_queries.select_consensus_by_partition(
            pool,
            ticker,
            analyst_name,
            analyst_company,
            limit=10  # Get recent 10 events
        )
        
        # 3. Initialize MetricCalculationEngine
        engine = MetricCalculationEngine(
            metrics_by_domain={'consensusSignal': consensus_signal_metrics}
        )
        engine.build_dependency_graph()
        engine.topological_sort()
        
        # 4. Prepare "API data" (actually evt_consensus data)
        # leadPairFromList expects base_values as list of records
        api_data = {
            'evt_consensus': partition_events  # List of consensus events
        }
        
        # 5. Calculate consensusSignal using leadPairFromList
        calculated = engine.calculate_all(
            api_data=api_data,
            target_domains=['consensusSignal']
        )
        
        # 6. Extract consensusSignal result
        consensus_signal = None
        if 'consensusSignal' in calculated and 'consensusSignal' in calculated['consensusSignal']:
            consensus_signal = calculated['consensusSignal']['consensusSignal']
        
        # 7. Calculate targetMedian & consensusSummary (existing logic)
        target_median = 0
        consensus_summary = None
        
        try:
            consensus_summary_metrics = await metrics_queries.select_metrics_by_domains(
                pool,
                ['consensusSummary']
            )
            
            if consensus_summary_metrics:
                from .external_api import FMPAPIClient
                
                async with FMPAPIClient() as fmp_client:
                    api_data_fmp = {}
                    consensus_target_data = await fmp_client.call_api(
                        'fmp-price-target-consensus',
                        {'ticker': ticker}
                    )
                    if consensus_target_data:
                        api_data_fmp['fmp-price-target-consensus'] = (
                            consensus_target_data if isinstance(consensus_target_data, list)
                            else [consensus_target_data]
                        )
                    
                    engine_summary = MetricCalculationEngine(
                        metrics_by_domain={'consensusSummary': consensus_summary_metrics}
                    )
                    engine_summary.build_dependency_graph()
                    engine_summary.topological_sort()
                    
                    calculated_summary = engine_summary.calculate_all(
                        api_data=api_data_fmp,
                        target_domains=['consensusSummary']
                    )
                    
                    if 'consensusSummary' in calculated_summary and 'consensusSummary' in calculated_summary['consensusSummary']:
                        consensus_summary = calculated_summary['consensusSummary']['consensusSummary']
                        
                        if isinstance(consensus_summary, dict):
                            target_median = consensus_summary.get('targetMedian', 0)
        
        except Exception as e:
            logger.warning(f"[QualitativeMetrics] Failed to calculate consensusSummary/targetMedian: {e}")
        
        # 8. Build value_qualitative
        value_qualitative = {
            'targetMedian': target_median,
            'consensusSummary': consensus_summary,
            'consensusSignal': consensus_signal  # ✅ 동적 계산 결과 사용
        }
        
        return {
            'status': 'success',
            'value': value_qualitative,
            'currentPrice': None,
            'message': 'Qualitative metrics calculated successfully'
        }
        
    except Exception as e:
        logger.error(f"[QualitativeMetrics] Calculation failed: {e}", exc_info=True)
        return {
            'status': 'failed',
            'value': None,
            'currentPrice': None,
            'message': str(e)
        }
```

**필요한 추가 함수**:

**파일**: `backend/src/database/queries/consensus.py`

```python
async def select_consensus_by_partition(
    pool: asyncpg.Pool,
    ticker: str,
    analyst_name: Optional[str],
    analyst_company: Optional[str],
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Select consensus events for a specific partition.
    
    Used for leadPairFromList aggregation.
    
    Args:
        pool: Database connection pool
        ticker: Stock ticker
        analyst_name: Analyst name (nullable)
        analyst_company: Analyst company (nullable)
        limit: Maximum number of events to return
    
    Returns:
        List of consensus events ordered by event_date DESC
    """
    async with pool.acquire() as conn:
        query = """
            SELECT
                id,
                ticker,
                event_date,
                analyst_name,
                analyst_company,
                price_target,
                price_when_posted,
                price_target_prev,
                price_when_posted_prev,
                direction,
                response_key
            FROM evt_consensus
            WHERE ticker = $1
              AND (analyst_name = $2 OR ($2 IS NULL AND analyst_name IS NULL))
              AND (analyst_company = $3 OR ($3 IS NULL AND analyst_company IS NULL))
            ORDER BY event_date DESC
            LIMIT $4
        """
        
        rows = await conn.fetch(query, ticker, analyst_name, analyst_company, limit)
        
        results = []
        for row in rows:
            results.append({
                'id': str(row['id']),
                'ticker': row['ticker'],
                'event_date': row['event_date'].isoformat() if row['event_date'] else None,
                'analyst_name': row['analyst_name'],
                'analyst_company': row['analyst_company'],
                'price_target': float(row['price_target']) if row['price_target'] else None,
                'price_when_posted': float(row['price_when_posted']) if row['price_when_posted'] else None,
                'price_target_prev': float(row['price_target_prev']) if row['price_target_prev'] else None,
                'price_when_posted_prev': float(row['price_when_posted_prev']) if row['price_when_posted_prev'] else None,
                'direction': row['direction'],
                'response_key': row['response_key']
            })
        
        return results
```

---

## I-NEW-02: consensusSignal 스키마 보완 (부분반영)

### 추가해야 할 필드

**파일**: `backend/src/services/valuation_service.py`

**현재 스키마**:
```python
consensus_signal = {
    'direction': direction,
    'last': { ... },
    'prev': { ... },
    'delta': { ... },
    'deltaPct': { ... }
}
```

**완성된 스키마 (가이드라인 준수)**:
```python
consensus_signal = {
    # ✅ 추가: 소스 정보
    'source': 'evt_consensus',
    'source_id': source_id,  # UUID string
    'event_date': event_date.isoformat() if event_date else None,
    
    # ✅ 기존 필드
    'direction': direction,
    'last': {
        'price_target': float(price_target) if price_target else None,
        'price_when_posted': float(price_when_posted) if price_when_posted else None
    },
    'prev': {
        'price_target': float(price_target_prev) if price_target_prev else None,
        'price_when_posted': float(price_when_posted_prev) if price_when_posted_prev else None
    } if price_target_prev is not None else None,
    'delta': {
        'price_target': delta,
        'price_when_posted': delta_when_posted
    } if price_target_prev is not None else None,
    'deltaPct': {
        'price_target': delta_pct
    } if price_target_prev is not None and price_target_prev != 0 else None,
    
    # ✅ 추가: 메타 정보
    'meta': {
        'analyst_name': consensus_data.get('analyst_name'),
        'analyst_company': consensus_data.get('analyst_company'),
        # ✅ 추가: 뉴스 정보 (response_key.last에서 추출)
        'news_url': consensus_data.get('response_key', {}).get('last', {}).get('newsURL'),
        'news_title': consensus_data.get('response_key', {}).get('last', {}).get('newsTitle'),
        'news_publisher': consensus_data.get('response_key', {}).get('last', {}).get('newsPublisher'),
        'source_api': 'fmp-price-target'
    }
}
```

---

## 구현 우선순위

### 🔴 필수 (즉시)
1. **I-NEW-01 수정**
   - `calculate_qualitative_metrics()` 함수 전체 리팩토링
   - MetricCalculationEngine 사용
   - `select_consensus_by_partition()` 함수 추가
   - 하드코딩 로직 제거

### 🟡 권장 (단기)
2. **I-NEW-02 보완**
   - source, source_id, event_date 필드 추가
   - meta.news_* 필드 추가

---

## 테스트 방법

### 1. consensusSignal 동적 계산 테스트

```python
# backend/scripts/test_consensus_signal_dynamic.py
import asyncio
from src.database.connection import db_pool
from src.services.valuation_service import calculate_qualitative_metrics

async def test_consensus_signal():
    pool = await db_pool.get_pool()
    
    # Test parameters
    ticker = 'AAPL'
    event_date = '2024-03-15'
    source = 'consensus'
    source_id = '<UUID from evt_consensus>'
    
    result = await calculate_qualitative_metrics(
        pool, ticker, event_date, source, source_id
    )
    
    print("Result:", result)
    
    # Verify
    assert result['status'] == 'success'
    assert 'consensusSignal' in result['value']
    
    consensus_signal = result['value']['consensusSignal']
    
    # Check required fields
    assert 'source' in consensus_signal
    assert 'source_id' in consensus_signal
    assert 'event_date' in consensus_signal
    assert 'direction' in consensus_signal
    assert 'last' in consensus_signal
    assert 'meta' in consensus_signal
    
    print("✅ All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_consensus_signal())
```

---

*마지막 업데이트: 2025-12-24*

