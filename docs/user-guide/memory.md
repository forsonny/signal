# Memory

**What you'll learn:**

- What memories are and how they are stored on disk
- The six memory types and when each is used
- How memory scoping works across Prime, micro-agents, and shared pools
- How to search and inspect memories with the CLI
- How scoring, decay, and semantic search rank results
- How the MemoryKeeper agent maintains memory health

---

## What memories are

A memory is an atomic unit of agent knowledge. Each memory is stored as a single markdown file with YAML frontmatter inside the `.signal/memory/` directory tree. Memories are indexed in a SQLite database (`index.db`) for fast retrieval, but the file on disk is always the source of truth.

A memory file looks like this:

```markdown
---
id: mem_a1b2c3d4
agent: prime
type: learning
tags:
  - python
  - error-handling
confidence: 0.7
version: 1
created: '2026-03-15T10:30:00+00:00'
updated: '2026-03-15T10:30:00+00:00'
accessed: '2026-03-20T14:00:00+00:00'
access_count: 3
changelog:
  - 'v1: Created (2026-03-15, confidence: 0.7)'
supersedes: []
superseded_by: null
consolidated_from: []
---

When handling file I/O errors in Python, always use
pathlib and catch OSError rather than bare IOError.
```

Every memory carries these metadata fields:

| Field              | Description                                           |
|--------------------|-------------------------------------------------------|
| `id`               | Unique identifier (`mem_` + 8 hex chars)              |
| `agent`            | Owning agent name (scoping key)                       |
| `type`             | One of the six memory types (see below)               |
| `tags`             | Searchable keyword tags                               |
| `confidence`       | Score from 0.0 to 1.0 indicating reliability          |
| `version`          | Monotonically increasing version counter              |
| `created`          | UTC timestamp of initial creation                     |
| `updated`          | UTC timestamp of last modification                    |
| `accessed`         | UTC timestamp of last read access                     |
| `access_count`     | Total number of times the memory was read             |
| `changelog`        | Version history entries                               |
| `supersedes`       | IDs of memories this one replaces                     |
| `superseded_by`    | ID of the memory that replaced this one (if any)      |
| `consolidated_from`| Source memory IDs if created by consolidation         |

Writes are crash-safe: the storage layer writes to a `.md.tmp` file and then atomically replaces the target using `os.replace`.

---

## Memory types

Signal defines six memory types. The type controls file-path routing and helps agents categorize what they know.

| Type       | Value      | Purpose                                                      |
|------------|------------|--------------------------------------------------------------|
| Identity   | `identity` | Who the agent is, its role and constraints                   |
| Learning   | `learning` | Knowledge acquired through interaction                       |
| Pattern    | `pattern`  | Recurring observations and behavioral patterns               |
| Outcome    | `outcome`  | Results of past actions (success, failure, tradeoffs)        |
| Context    | `context`  | Situational information about the current environment        |
| Shared     | `shared`   | Cross-agent knowledge visible to all agents in the instance  |

---

## Memory scoping

Memories are scoped by agent name and type. The file-path layout enforces this scoping:

```
.signal/memory/
  prime/                    # Prime agent memories
    identity/
      mem_aabbccdd.md
    learning/
      mem_11223344.md
  micro/                    # Micro-agent memories
    code-reviewer/
      learning/
        mem_55667788.md
      pattern/
        mem_99aabbcc.md
  shared/                   # Shared pool (no agent subdirectory)
    mem_ddeeff00.md
```

The routing rules are:

- **Shared memories** (`type=shared`) are stored in `shared/{id}.md`. The `agent` field is recorded in metadata but the file lives in a flat shared directory.
- **Prime memories** (`agent=prime`) are stored in `prime/{type}/{id}.md`.
- **Micro-agent memories** are stored in `micro/{agent}/{type}/{id}.md`.

When searching, agents see their own memories by default. Security policies can further restrict which agent scopes a given agent is allowed to read (see [Security](security.md)).

---

## Searching and inspecting memories

### Search by tags, agent, and type

```bash
signal memory search --tags python,error-handling --agent prime --limit 5
```

| Option        | Description                                       |
|---------------|---------------------------------------------------|
| `--tags`      | Comma-separated tags to filter by                 |
| `--agent`     | Filter to a specific agent name                   |
| `--type`      | Filter by memory type (e.g. `learning`, `shared`) |
| `--limit`     | Maximum number of results (default: 10)           |

The output is a table showing ID, agent, type, tags, confidence, and last-updated date.

### Inspect a single memory

```bash
signal memory inspect mem_a1b2c3d4
```

This prints the full memory record: all metadata fields, the complete changelog, and the content body. Inspecting a memory also updates its `accessed` timestamp and increments `access_count` in the index.

---

## Scoring

When a search returns multiple results, they are ranked by a composite score that combines four signals:

| Signal      | Weight | Description                                                |
|-------------|--------|------------------------------------------------------------|
| Relevance   | 50%    | Tag overlap ratio (matched tags / query tags)              |
| Frequency   | 25%    | Access frequency: `min(log(access_count + 1) / 10, 1.0)`  |
| Confidence  | 25%    | The memory's confidence value (0.0--1.0)                   |

The base score is then multiplied by a time-decay factor:

```
base_score = relevance * 0.5 + frequency * 0.25 + confidence * 0.25
decay_factor = 1 / (1 + days_since_last_access / decay_half_life_days)
effective_score = base_score * decay_factor
```

With the default `decay_half_life_days: 30`, a memory not accessed for 30 days retains half its base score. At 60 days, it retains one-third. This keeps actively-used memories at the top while stale knowledge naturally drifts down the rankings.

---

## Semantic search

When an `embedding_model` is configured in the profile's `memory` section, Signal embeds memory content at write time and stores the vector in the SQLite index.

Semantic search uses two-phase retrieval:

1. **Candidate selection:** The query text is embedded and compared against all stored vectors using cosine similarity. The top `3 * limit` candidates are selected.
2. **Scoring and ranking:** Candidates are scored using the same formula described above. When tags are provided, relevance is computed from tag overlap; otherwise, embedding similarity substitutes as the relevance signal.

To enable semantic search, set the embedding model in your profile:

```yaml
memory:
  decay_half_life_days: 30
  embedding_model: openai/text-embedding-3-small
```

If embedding fails for a specific memory (e.g., API error), the memory is still stored on disk and indexed -- it just lacks a vector and will not appear in semantic search results until re-embedded.

To backfill embeddings for existing memories that were created before an embedding model was configured, the engine provides a `rebuild_embeddings()` method that processes memories in batches.

---

## Memory lifecycle

### Decay

Memories naturally lose ranking weight over time through the decay factor. This is not deletion -- the memory file stays on disk and still appears in search results, but its effective score decreases as `days_since_last_access` grows. Accessing a memory (via search with `touch=True` or via `signal memory inspect`) resets its `accessed` timestamp and restores its decay factor to 1.0.

### Archival

Archived memories are excluded from default search results but remain on disk. Archival is reversible. A memory's changelog records the reason for archival:

```
v2: Archived (2026-04-01, reason: stale: 95 days without access, effective confidence 0.08)
```

### Consolidation

When multiple memories cover overlapping knowledge, they can be consolidated into a single memory. The new memory records its `consolidated_from` sources, and each source memory is marked with `superseded_by` pointing to the consolidated replacement, then archived.

### The MemoryKeeper agent

The MemoryKeeper is a purpose-built maintenance agent (not a regular micro-agent). When configured in a profile, it runs on a heartbeat schedule and performs two passes:

1. **Group classification:** Finds groups of related memories (by tag overlap within the same agent and type), sends each group to the LLM for classification as `consolidate`, `archive`, or `skip`, and executes the recommended action.
2. **Staleness detection:** Finds memories where `days_since_access > staleness_threshold_days` and `effective_confidence < min_confidence`, then archives them.

---

## Configuration

Memory behavior is controlled by two profile sections:

### memory

```yaml
memory:
  decay_half_life_days: 30
  embedding_model: openai/text-embedding-3-small
```

| Field                  | Type        | Default | Description                                          |
|------------------------|-------------|---------|------------------------------------------------------|
| `decay_half_life_days` | int         | `30`    | Days after which memory relevance is halved (min: 1) |
| `embedding_model`      | string/null | `null`  | LiteLLM model ID for embeddings, or null to disable  |

### memory_keeper

```yaml
memory_keeper:
  schedule: "0 3 * * 0"
  staleness_threshold_days: 90
  min_confidence: 0.1
  max_candidates_per_run: 20
```

| Field                      | Type   | Default       | Description                                                |
|----------------------------|--------|---------------|------------------------------------------------------------|
| `schedule`                 | string | `"0 3 * * 0"` | Cron expression for maintenance runs (default: Sunday 3am) |
| `staleness_threshold_days` | int    | `90`           | Days without access before a memory is considered stale    |
| `min_confidence`           | float  | `0.1`          | Effective confidence below which stale memories are archived |
| `max_candidates_per_run`   | int    | `20`           | Max memory groups to process per maintenance run           |

Set `memory_keeper` to `null` or omit the section entirely to disable automatic maintenance. Memory creation, search, and decay still function without the keeper.

### Index recovery

If the SQLite index becomes corrupted or is deleted, the engine can rebuild it by scanning all `.md` files on disk:

```python
count = await engine.rebuild_index()
```

This is idempotent and safe to run at any time.

---

## Next steps

- [Profiles](profiles.md) -- full profile YAML schema including memory and memory_keeper sections
- [Security](security.md) -- how `allow_memory_read` policies restrict memory access per agent
- [Heartbeat](heartbeat.md) -- scheduling the MemoryKeeper via cron triggers
- [Core Concepts](concepts.md) -- how memory fits into the agent architecture
