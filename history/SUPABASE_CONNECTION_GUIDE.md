# 🔌 Supabase DATABASE_URL 찾기 가이드

## 방법 1: Database Settings 페이지 (권장)

1. Supabase Dashboard → **Settings** → **Database** 클릭
2. **페이지를 맨 위로 스크롤**
3. "Connection string" 또는 "Connection info" 섹션 찾기
4. 다음 탭 중 하나 선택:
   - **Transaction** (권장) 또는
   - **Session**
5. URI 형식의 문자열 복사

**예시:**
```
postgresql://postgres.abcdefghijk:[YOUR-PASSWORD]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres
```

## 방법 2: Project Settings → API

1. Supabase Dashboard → **Project Settings** (톱니바퀴 아이콘)
2. **API** 클릭
3. "Database" 섹션에서 다음 정보 확인:
   - Host
   - Database name
   - Port
   - User
4. Password는 **Database Settings**에서 확인하거나 리셋

수동으로 연결 문자열 구성:
```
postgresql://[user]:[password]@[host]:[port]/[database]
```

## 방법 3: 환경 변수 파일 생성 (간편)

직접 입력하는 대신 `.env` 파일을 생성하면 더 편리합니다:

### 1. `.env` 파일 생성

`c:\dev\alsign\backend\.env` 파일을 생성하고 다음 내용 입력:

```env
# Database Configuration
DATABASE_URL=postgresql://postgres.abcdefghijk:[YOUR-PASSWORD]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres
DB_POOL_MIN_SIZE=10
DB_POOL_MAX_SIZE=20

# FMP API Configuration
FMP_API_KEY=your_fmp_api_key_here
FMP_BASE_URL=https://financialmodelingprep.com/api/v3
FMP_RATE_LIMIT=250

# Application Configuration
LOG_LEVEL=INFO
ENVIRONMENT=development

# CORS Settings
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# Batch Configuration
DB_UPSERT_BATCH_SIZE=1000
API_BATCH_SIZE_INITIAL=50
```

### 2. 환경 변수 방식으로 검증 스크립트 실행

```bash
cd c:\dev\alsign\backend
python scripts\verify_checklist_items.py
```

이제 DATABASE_URL을 매번 입력할 필요가 없습니다!

## 현재 보이는 Supabase UI 기준

스크린샷에서 보이는 섹션들:
- ✅ Database password
- ✅ Connection pooling configuration (SHARED/DEDICATED)
- ✅ SSL Configuration

→ **"Connection pooling configuration" 위쪽**으로 스크롤하면 Connection string이 보일 것입니다.

## 주의사항

### ⚠️ Pooler 모드 선택
- **Transaction mode** (권장): 포트 `6543`
- Session mode: 포트 `5432`

→ `6543` 포트를 사용하는 것이 Supabase의 Connection Pooler를 사용하는 것입니다.

### ⚠️ 비밀번호 확인
- Connection string에 `[YOUR-PASSWORD]`로 표시되어 있다면
- "Database password" 섹션에서 비밀번호 확인 또는 리셋 필요
- 리셋 시 **반드시 복사해두세요** (다시 볼 수 없습니다)

## 빠른 테스트

DATABASE_URL을 찾았다면 바로 테스트:

```bash
cd c:\dev\alsign\backend
python scripts\verify_checklist_direct.py "YOUR_DATABASE_URL"
```

---

*업데이트: 2025-12-24*

