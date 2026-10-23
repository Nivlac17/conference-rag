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
PARTIAL_FILE = OUTPUT_FILE + '.partial.jsonl'
BATCH_SIZE = 500
EMBEDDING_PRICE_PER_MILLION_TOKENS = 0.02
# Reserve at least $0.60 of the user's $1 total cap for one live RAG answer.
MAX_EMBEDDING_SPEND_USD = 0.40
USAGE_FILE = OUTPUT_FILE + '.usage.json'


def utf8_byte_upper_bound(texts):
    """A conservative token upper bound: each token encodes at least one byte."""
    return sum(len(text.encode('utf-8')) for text in texts)


def embedding_cost(tokens):
    return tokens / 1_000_000 * EMBEDDING_PRICE_PER_MILLION_TOKENS


def atomic_write_json(path, value):
    temporary_path = path + '.tmp'
    with open(temporary_path, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary_path, path)


def load_existing_embeddings(records):
    """Load complete JSONL checkpoints and discard only an interrupted last line."""
    existing = []
    if os.path.exists(PARTIAL_FILE):
        valid_bytes = 0
        with open(PARTIAL_FILE, 'rb') as f:
            while True:
                line = f.readline()
                if not line:
                    break
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    break
                if not record.get('embedding'):
                    break
                existing.append(record)
                valid_bytes += len(line)
        if os.path.getsize(PARTIAL_FILE) != valid_bytes:
            with open(PARTIAL_FILE, 'r+b') as f:
                f.truncate(valid_bytes)
    elif os.path.exists(OUTPUT_FILE):
        # Migrate an earlier JSON-array checkpoint to append-only JSONL.
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        temporary_path = PARTIAL_FILE + '.tmp'
        with open(temporary_path, 'w', encoding='utf-8') as f:
            for record in existing:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, PARTIAL_FILE)

    if len(existing) > len(records):
        raise ValueError('Saved embeddings contain more rows than the source data.')
    for index, record in enumerate(existing):
        if record.get('id') != records[index].get('id'):
            raise ValueError('Saved embeddings do not match the source record order.')
    return existing


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

    try:
        existing = load_existing_embeddings(records)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"❌ Could not safely resume saved embeddings ({type(e).__name__}).")
        sys.exit(1)
    already_embedded = len(existing)
    if already_embedded >= len(records):
        atomic_write_json(OUTPUT_FILE, existing)
        if os.path.exists(PARTIAL_FILE):
            os.remove(PARTIAL_FILE)
        print(f"✅ All {len(records):,} sentences already have embeddings in {OUTPUT_FILE}")
        return
    if already_embedded:
        print(f"   ⏩ Resuming from sentence {already_embedded:,} (saved JSONL checkpoint)")
    records_to_embed = records[already_embedded:]

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

    embedded_records = list(existing)  # Used to produce the final JSON array once.

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
            if len(response.data) != len(batch):
                raise RuntimeError('The embedding response did not contain one vector per input.')
            if any(len(item.embedding) != 1536 for item in response.data):
                raise RuntimeError('The embedding response contained an unexpected vector size.')
            usage['prompt_tokens'] += batch_tokens - batch_token_upper_bound
            if embedding_cost(usage['prompt_tokens']) > MAX_EMBEDDING_SPEND_USD:
                raise RuntimeError('Embedding spend limit reached; stopping before another batch.')

            new_records = []
            for record, item in zip(batch, response.data):
                record_with_embedding = dict(record)
                record_with_embedding['embedding'] = item.embedding
                new_records.append(record_with_embedding)

            # Save the actual response usage before appending vectors. If the
            # process stops while writing, the next run still accounts for the
            # request and recovers only complete JSONL lines.
            atomic_write_json(USAGE_FILE, usage)
            with open(PARTIAL_FILE, 'a', encoding='utf-8') as f:
                for record in new_records:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            embedded_records.extend(new_records)

        except Exception as e:
            # Do not print SDK errors: authentication errors can echo a
            # partially masked API key. Stop instead of retrying later batches.
            print(f"\n   ❌ OpenAI request failed ({type(e).__name__}); stopping to avoid repeated calls.")
            sys.exit(1)

        time.sleep(0.1)

    # Write the importer-compatible JSON array once, atomically.
    atomic_write_json(OUTPUT_FILE, embedded_records)
    if os.path.exists(PARTIAL_FILE):
        os.remove(PARTIAL_FILE)

    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"\n✅ Embedding complete!")
    print(f"   Embedded: {len(embedded_records):,} sentences")
    cost = embedding_cost(usage['prompt_tokens'])
    print(f"   💰 Tracked embedding spend ceiling: ${cost:.4f}")

    print(f"\n💾 Saved to {OUTPUT_FILE} ({file_size_mb:.1f} MB)")
    print(f"   This file is your safety net — embeddings are preserved on disk.")
    print(f"\nNext: python scripts/05_update_embeddings.py")


if __name__ == '__main__':
    main()
