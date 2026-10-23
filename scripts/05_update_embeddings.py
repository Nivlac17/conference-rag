"""
Step 5: Import Embeddings to Database
=========================================
Reads scripts/output/sentences_with_embeddings.json and upserts
all records (text + embeddings) to Supabase.

After this step, SEMANTIC SEARCH will light up green on your site!

Usage:
    python scripts/05_update_embeddings.py

Input:
    scripts/output/sentences_with_embeddings.json  — from Step 4

Prerequisites:
    - config.public.json with Supabase URL and anon key
    - config.secret.json with Supabase service key
    - Database schema created (Step 1)
    - Embeddings generated (Step 4)
"""

import json
import os
import sys
import time

import requests

from supabase import create_client
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'sentences_with_embeddings.json')
SOURCE_FILE = os.path.join('scripts', 'output', 'sentences.json')
BATCH_SIZE = 100


def load_config():
    with open('config.public.json', 'r') as f:
        public_config = json.load(f)
    with open('config.secret.json', 'r') as f:
        secrets = json.load(f)
    return public_config, secrets


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/04_embed_data.py first.")
        sys.exit(1)

    # Load embedded records
    print("Loading embeddings data...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    # Verify embeddings are present
    with_embeddings = sum(1 for r in records if r.get('embedding'))
    without_embeddings = len(records) - with_embeddings

    print(f"   Loaded {len(records):,} records")
    print(f"   With embeddings:    {with_embeddings:,}")
    if without_embeddings:
        print(f"   Without embeddings: {without_embeddings:,} (will be imported without)")

    # Never replace database contents with a partial or empty local result.
    if not records or without_embeddings:
        print("❌ Refusing to update the database: every source record must have an embedding.")
        sys.exit(1)

    if not os.path.exists(SOURCE_FILE):
        print(f"❌ {SOURCE_FILE} is missing; cannot verify that the embedding file is complete.")
        sys.exit(1)
    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        source_records = json.load(f)
    if len(records) != len(source_records) or any(
        (embedded.get('talk_id'), embedded.get('sentence_num')) !=
        (source.get('talk_id'), source.get('sentence_num'))
        for embedded, source in zip(records, source_records)
    ):
        print("❌ Refusing to update the database: the embedding file is incomplete or out of order.")
        sys.exit(1)
    if any(not isinstance(record.get('embedding'), list) or len(record['embedding']) != 1536 for record in records):
        print("❌ Refusing to update the database: one or more embedding vectors are malformed.")
        sys.exit(1)

    sentence_keys = [(record.get('talk_id'), record.get('sentence_num')) for record in records]
    if any(not talk_id or sentence_num is None for talk_id, sentence_num in sentence_keys) or len(set(sentence_keys)) != len(sentence_keys):
        print("❌ Refusing to update the database: records must have unique talk/sentence keys.")
        sys.exit(1)

    # Use a single HTTP session to reuse the connection and avoid saturating
    # the free database with concurrent vector writes.
    public_config, secrets = load_config()
    supabase_url = public_config['SUPABASE_URL'].rstrip('/')
    service_key = secrets['SUPABASE_SERVICE_KEY']
    headers = {
        'apikey': service_key,
        'Authorization': f'Bearer {service_key}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal',
    }
    client = create_client(supabase_url, service_key)

    # Upsert on each talk/sentence natural key. This preserves existing rows
    # and updates their vectors without truncating the table.
    print("\n" + "=" * 60)
    print("Updating database rows with embeddings (upsert)")
    print("=" * 60)

    # Batch import (much faster than individual updates!)
    print(f"\n   Importing {len(records):,} records in batches of {BATCH_SIZE}...\n")

    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    session = requests.Session()
    success = 0
    for index, batch in enumerate(tqdm(batches, desc="Importing")):
        for attempt in range(5):
            try:
                response = session.post(
                    f'{supabase_url}/rest/v1/sentence_embeddings',
                    headers=headers,
                    params={'on_conflict': 'talk_id,sentence_num'},
                    json=batch,
                    timeout=180,
                )
                if response.status_code >= 500 or response.status_code in (408, 429):
                    raise requests.RequestException(f'Supabase returned HTTP {response.status_code}')
                response.raise_for_status()
                success += len(batch)
                break
            except requests.RequestException as e:
                if attempt == 4:
                    print(f"\n❌ Database update failed at batch {index} ({type(e).__name__}).")
                    print(f"   {success:,} records were confirmed before the failure; rerun safely to retry.")
                    sys.exit(1)
                time.sleep(min(3 * (attempt + 1), 15))

    print(f"\n✅ Import complete!")
    print(f"   Success: {success:,}")
    # Verify
    result = client.table('sentence_embeddings').select('id', count='exact').limit(1).execute()
    total = result.count or 0

    embedded_result = client.table('sentence_embeddings') \
        .select('id', count='exact') \
        .not_('embedding', 'is', 'null') \
        .limit(1).execute()
    with_emb = embedded_result.count or 0

    print(f"\n   Total rows:          {total:,}")
    print(f"   Rows with embeddings: {with_emb:,}")

    if with_emb < len(records):
        print("❌ The database does not yet contain embeddings for every input record.")
        sys.exit(1)

    print(f"\n🎉 Semantic Search is now ready!")
    print(f"   Refresh your site — the 🧠 Semantic Search panel should turn GREEN.")
    print(f"\nNext: Deploy edge functions to light up 🤖 RAG!")


if __name__ == '__main__':
    main()
