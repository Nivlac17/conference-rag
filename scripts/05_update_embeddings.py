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

from supabase import create_client
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'sentences_with_embeddings.json')
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

    ids = [record.get('id') for record in records]
    if any(not record_id for record_id in ids) or len(set(ids)) != len(ids):
        print("❌ Refusing to update the database: records must have unique IDs.")
        sys.exit(1)

    # Connect to Supabase
    public_config, secrets = load_config()
    client = create_client(public_config['SUPABASE_URL'], secrets['SUPABASE_SERVICE_KEY'])

    # Upsert on each record ID. This preserves existing rows and updates their
    # vectors without truncating the table.
    print("\n" + "=" * 60)
    print("Updating database rows with embeddings (upsert)")
    print("=" * 60)

    # Batch import (much faster than individual updates!)
    print(f"\n   Importing {len(records):,} records in batches of {BATCH_SIZE}...\n")

    success = 0
    for i in tqdm(range(0, len(records), BATCH_SIZE), desc="Importing"):
        batch = records[i:i + BATCH_SIZE]
        try:
            client.table('sentence_embeddings').upsert(batch, on_conflict='id').execute()
            success += len(batch)
        except Exception as e:
            print(f"\n❌ Database update failed at batch {i // BATCH_SIZE} ({type(e).__name__}); stopping.")
            print(f"   {success:,} records were updated before the failure; rerun to resume safely.")
            sys.exit(1)
        time.sleep(0.1)

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
