"""
Step 4: Generate Embeddings
===============================
Reads scripts/output/sentences.json and generates OpenAI embeddings
for each sentence. Saves the result to scripts/output/sentences_with_embeddings.json.

This is the most expensive step (~$0.60 in API costs). The output is
saved to disk so you won't lose your work if the next step fails.

Usage:
    python scripts/04_embed_data.py

Input:
    scripts/output/sentences.json  — from Step 3 (import)

Output:
    scripts/output/sentences_with_embeddings.json  — sentence records with embedding vectors

Prerequisites:
    - config.secret.json with OPENAI_API_KEY
    - scripts/output/sentences.json from the import step
"""

import json
import os
import sys
import time

from openai import OpenAI
from tqdm import tqdm


INPUT_FILE = os.path.join('scripts', 'output', 'sentences.json')
OUTPUT_FILE = os.path.join('scripts', 'output', 'sentences_with_embeddings.json')
BATCH_SIZE = 100
EMBEDDING_PRICE_PER_MILLION_TOKENS = 0.02
# Reserve at least $0.60 of the user's $1 total cap for one live RAG answer.
MAX_EMBEDDING_SPEND_USD = 0.40
USAGE_FILE = OUTPUT_FILE + '.usage.json'


def utf8_byte_upper_bound(texts):
    """A conservative token upper bound: each token encodes at least one byte."""
    return sum(len(text.encode('utf-8')) for text in texts)


def embedding_cost(tokens):
    return tokens / 1_000_000 * EMBEDDING_PRICE_PER_MILLION_TOKENS


def load_secrets():
    with open('config.secret.json', 'r') as f:
        return json.load(f)


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found. Run scripts/03_import_data.py first.")
        sys.exit(1)

    # Load sentences
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        records = json.load(f)

    print("=" * 60)
    print(f"Generating Embeddings for {len(records):,} Sentences")
    print("=" * 60)
    print(f"   Model: text-embedding-3-small (1,536 dimensions)")
    print(f"   Batch size: {BATCH_SIZE}\n")

    # Check if there's a partial result we can resume from
    already_embedded = 0
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        already_embedded = len(existing)
        if already_embedded >= len(records):
            print(f"✅ All {len(records):,} sentences already have embeddings in {OUTPUT_FILE}")
            print(f"   Delete {OUTPUT_FILE} to re-generate.")
            return
        print(f"   ⏩ Resuming from sentence {already_embedded:,} (found partial output)")
        records_to_embed = records[already_embedded:]
    else:
        existing = []
        records_to_embed = records

    # Use UTF-8 bytes as a conservative upper bound on token count before
    # making any billable calls. This leaves budget for the final RAG answer.
    remaining_texts = [r['text'] for r in records_to_embed]
    remaining_upper_bound = utf8_byte_upper_bound(remaining_texts)
    usage = {'prompt_tokens': 0}
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r', encoding='utf-8') as f:
            usage = json.load(f)
    elif already_embedded:
        # A legacy partial output has no usage ledger. Reserve its worst-case
        # byte bound so resuming cannot silently exceed the embedding budget.
        usage['prompt_tokens'] = utf8_byte_upper_bound(
            [r['text'] for r in existing]
        )

    maximum_total_tokens = usage['prompt_tokens'] + remaining_upper_bound
    maximum_total_cost = embedding_cost(maximum_total_tokens)
    if maximum_total_cost > MAX_EMBEDDING_SPEND_USD:
        print(
            f"❌ Safe preflight estimate is ${maximum_total_cost:.4f}, "
            f"above the ${MAX_EMBEDDING_SPEND_USD:.2f} embedding limit. "
            "No API calls were made."
        )
        sys.exit(1)
    print(
        f"   Conservative maximum embedding cost: ${maximum_total_cost:.4f} "
        f"(limit ${MAX_EMBEDDING_SPEND_USD:.2f})"
    )

    # Generate embeddings
    secrets = load_secrets()
    client = OpenAI(api_key=secrets['OPENAI_API_KEY'], max_retries=0)

    embedded_records = list(existing)  # Start from any partial results
    errors = 0

    for i in tqdm(range(0, len(records_to_embed), BATCH_SIZE), desc="Embedding"):
        batch = records_to_embed[i:i + BATCH_SIZE]
        batch_texts = [r['text'] for r in batch]
        batch_token_upper_bound = utf8_byte_upper_bound(batch_texts)

        # Persist the batch's worst-case cost before the request. If the process
        # stops after OpenAI accepts it but before its response is saved, a
        # resume still accounts for the possible charge.
        usage['prompt_tokens'] += batch_token_upper_bound
        with open(USAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(usage, f)

        try:
            response = client.embeddings.create(
                model='text-embedding-3-small',
                input=batch_texts
            )

            batch_tokens = response.usage.prompt_tokens
            if batch_tokens > batch_token_upper_bound:
                raise RuntimeError('API token usage exceeded the conservative preflight bound.')
            usage['prompt_tokens'] += batch_tokens - batch_token_upper_bound
            if embedding_cost(usage['prompt_tokens']) > MAX_EMBEDDING_SPEND_USD:
                raise RuntimeError('Embedding spend limit reached; stopping before another batch.')

            for record, item in zip(batch, response.data):
                record_with_embedding = dict(record)
                record_with_embedding['embedding'] = item.embedding
                embedded_records.append(record_with_embedding)

        except Exception as e:
            # Do not print SDK errors: authentication errors can echo a
            # partially masked API key. Stop instead of retrying later batches.
            print(f"\n   ❌ OpenAI request failed ({type(e).__name__}); stopping to avoid repeated calls.")
            with open(USAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(usage, f)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(embedded_records, f, ensure_ascii=False)
            sys.exit(1)

        # Checkpoint every batch so a crash does not repeat billable work.
        with open(USAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(usage, f)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(embedded_records, f, ensure_ascii=False)

        time.sleep(0.1)

    # Final save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(embedded_records, f, ensure_ascii=False)

    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"\n✅ Embedding complete!")
    print(f"   Embedded: {len(embedded_records):,} sentences")
    if errors:
        print(f"   Errors:   {errors:,}")

    cost = embedding_cost(usage['prompt_tokens'])
    print(f"   💰 Tracked embedding cost: ${cost:.4f} (actual API token usage)")

    print(f"\n💾 Saved to {OUTPUT_FILE} ({file_size_mb:.1f} MB)")
    print(f"   This file is your safety net — embeddings are preserved on disk.")
    print(f"\nNext: python scripts/05_update_embeddings.py")


if __name__ == '__main__':
    main()
