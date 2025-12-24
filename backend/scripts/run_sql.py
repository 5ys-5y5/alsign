"""SQL 스크립트 실행 유틸리티"""
import asyncio
import asyncpg
import os
from pathlib import Path

async def run_sql_file(sql_file_path: str):
    """SQL 파일을 실행합니다."""
    # DATABASE_URL 환경 변수 확인
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL 환경 변수가 설정되지 않았습니다.")
        return
    
    # SQL 파일 읽기
    sql_path = Path(sql_file_path)
    if not sql_path.exists():
        print(f"ERROR: SQL 파일을 찾을 수 없습니다: {sql_file_path}")
        return
    
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    print(f"SQL 파일 로드 완료: {sql_file_path}")
    print(f"SQL 길이: {len(sql_content)} 문자")
    
    # DB 연결 및 실행
    try:
        conn = await asyncpg.connect(database_url)
        print("DB 연결 성공")
        
        # SQL 실행 (트랜잭션으로 감싸기)
        async with conn.transaction():
            # 세미콜론으로 분리하여 각 쿼리 실행
            queries = [q.strip() for q in sql_content.split(';') if q.strip() and not q.strip().startswith('--')]
            
            for i, query in enumerate(queries, 1):
                if query:
                    print(f"\n실행 중 ({i}/{len(queries)}): {query[:100]}...")
                    try:
                        result = await conn.execute(query)
                        print(f"✓ 완료: {result}")
                    except Exception as e:
                        print(f"✗ 실패: {e}")
                        raise
        
        print("\n모든 쿼리 실행 완료")
        
        await conn.close()
        print("DB 연결 종료")
        
    except Exception as e:
        print(f"ERROR: SQL 실행 실패: {e}")
        raise

if __name__ == '__main__':
    sql_file = 'backend/scripts/apply_issue_docs_changes.sql'
    asyncio.run(run_sql_file(sql_file))

