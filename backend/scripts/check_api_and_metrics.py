#!/usr/bin/env python3
"""Check config_lv1_api_list and config_lv2_metric states"""

import asyncio
import asyncpg
import json

DATABASE_URL = "postgresql://postgres.fgypclaqxonwxlmqdphx:qycKXqvs%40%21Q_Pt3@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

async def main():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    try:
        print('='*80)
        print('config_lv1_api_list - Relevant APIs')
        print('='*80)

        api_ids = ['fmp-historical-price-eod-full', 'fmp-price-target-consensus', 'fmp-price-target']
        for api_id in api_ids:
            row = await conn.fetchrow(
                'SELECT id, api, schema FROM config_lv1_api_list WHERE id = $1',
                api_id
            )

            if row:
                print(f'\n[{api_id}]')
                print(f'  api: {row["api"]}')
                if row['schema']:
                    schema_obj = row['schema']
                    schema_str = json.dumps(schema_obj, indent=2)
                    if len(schema_str) > 1000:
                        print(f'  schema (first 1000 chars):\n{schema_str[:1000]}...')
                    else:
                        print(f'  schema:\n{schema_str}')
            else:
                print(f'\n[{api_id}] - NOT FOUND')

        print('\n' + '='*80)
        print('config_lv2_metric - Consensus related metrics')
        print('='*80)

        metric_ids = [
            'consensusSignal', 'consensusSummary', 'targetMedian',
            'consensusSummaryTargetLow', 'consensusSummaryTargetHigh',
            'consensusSummaryTargetMedian', 'consensusSummaryTargetConsensus'
        ]

        for metric_id in metric_ids:
            row = await conn.fetchrow(
                '''SELECT id, source, api_list_id, response_key, expression, domain
                   FROM config_lv2_metric WHERE id = $1''',
                metric_id
            )

            if row:
                print(f'\n[{metric_id}]')
                print(f'  source: {row["source"]}')
                print(f'  api_list_id: {row["api_list_id"]}')
                print(f'  response_key: {row["response_key"]}')
                print(f'  expression: {row["expression"]}')
                print(f'  domain: {row["domain"]}')
            else:
                print(f'\n[{metric_id}] - NOT FOUND')

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
