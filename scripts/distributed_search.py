#!/usr/bin/env python3
"""
distributed_search.py -- Task 6: distributed search via (a) query
partitioning and (b) database partitioning, using DIAMOND blastx as the
underlying single-node search engine (BLAST+ blastx works identically but
is far slower per the Task 8 comparison, so it is not used for the
worker-count sweep in Task 7).

Two strategies, two different failure modes (this is what Task 6 asks to
be analysed, not just implemented):

QUERY PARTITIONING
  Split the query FASTA into N roughly-equal shards. Each worker runs a
  search of its shard against the *entire* database. Results are simply
  concatenated -- no merge/reduce step, because each worker already saw
  the full database and produced complete, final hits for its queries.
  Failure mode: does not help at all if the bottleneck is database size
  (every worker still has to load/scan the whole DB), and is only
  embarrassingly parallel if the DB fits in memory per worker. With N
  workers > available cores, workers compete for the same DB pages in
  memory/cache.

DATABASE PARTITIONING
  Split the database FASTA into N shards, each turned into its own DIAMOND
  index. The *entire* query set is searched against every shard, then a
  merge step keeps, for each query, only the best hit(s) across all
  shards (by bitscore, tie-broken by e-value). Failure mode: introduces a
  real reduce/merge step whose cost grows with (n_queries x N); a query
  present in shard A but with a slightly-worse-scoring paralogue in shard B
  needs the merge to pick correctly -- get the merge key wrong and you
  silently keep the wrong hit. Also duplicates the *query* set N times in
  flight instead of the database, which matters when queries, not the DB,
  are the memory pressure (e.g. many long Nanopore reads).

Both strategies are timed end-to-end (build/partition cost is charged to
whichever step causes it) so Task 7 can build a real, measured scaling
curve rather than a theoretical one.
"""
import argparse
import json
import multiprocessing as mp
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
DBDIR = PROC / "blastdb"
WORKDIR = ROOT / "data" / "processed" / "distributed_work"
WORKDIR.mkdir(parents=True, exist_ok=True)

DIAMOND_COLUMNS = "qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore"


def parse_fasta(path):
    records = []
    header, chunks = None, []
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith(">"):
                if header is not None:
                    records.append((header, "".join(chunks)))
                header = line[1:]
                chunks = []
            else:
                chunks.append(line.strip())
    if header is not None:
        records.append((header, "".join(chunks)))
    return records


def write_fasta(records, path):
    with open(path, "w") as out:
        for h, s in records:
            out.write(f">{h}\n{s}\n")


def split_evenly(records, n):
    n = max(1, n)
    k, m = divmod(len(records), n)
    shards, start = [], 0
    for i in range(n):
        size = k + (1 if i < m else 0)
        shards.append(records[start:start + size])
        start += size
    return [s for s in shards if s]


def run_diamond_blastx(query_fasta, db_prefix, out_tsv, threads=1):
    cmd = [
        "diamond", "blastx",
        "--query", str(query_fasta),
        "--db", str(db_prefix),
        "--out", str(out_tsv),
        "--outfmt", "6", *DIAMOND_COLUMNS.split(),
        "--threads", str(threads),
        "--quiet",
        "--max-target-seqs", "5",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Query partitioning
# ---------------------------------------------------------------------------
def _query_shard_worker(args):
    shard_idx, query_records, db_prefix, tag = args
    shard_fasta = WORKDIR / f"{tag}_qshard_{shard_idx}.fasta"
    shard_out = WORKDIR / f"{tag}_qshard_{shard_idx}.tsv"
    write_fasta(query_records, shard_fasta)
    t0 = time.perf_counter()
    run_diamond_blastx(shard_fasta, db_prefix, shard_out, threads=1)
    elapsed = time.perf_counter() - t0
    n_hits = sum(1 for _ in open(shard_out)) if shard_out.exists() else 0
    return shard_idx, elapsed, n_hits, shard_out


def query_partitioning_search(query_fasta, db_prefix, n_workers, tag):
    records = parse_fasta(query_fasta)
    shards = split_evenly(records, n_workers)
    tasks = [(i, shard, db_prefix, tag) for i, shard in enumerate(shards)]

    t_wall0 = time.perf_counter()
    with mp.Pool(processes=len(shards)) as pool:
        per_worker = pool.map(_query_shard_worker, tasks)
    wall_time = time.perf_counter() - t_wall0

    merged_path = WORKDIR / f"{tag}_query_partition_merged.tsv"
    total_hits = 0
    with open(merged_path, "w") as out:
        for _, _, n_hits, shard_out in sorted(per_worker):
            out.write(shard_out.read_text())
            total_hits += n_hits

    return {
        "strategy": "query_partitioning",
        "n_workers": len(shards),
        "n_queries": len(records),
        "wall_seconds": round(wall_time, 4),
        "per_worker_seconds": [round(e, 4) for _, e, _, _ in sorted(per_worker)],
        "merge_seconds": 0.0,  # concatenation only -- no real merge needed
        "total_hits": total_hits,
    }


# ---------------------------------------------------------------------------
# Database partitioning
# ---------------------------------------------------------------------------
def _db_shard_worker(args):
    shard_idx, db_records, query_fasta, tag = args
    shard_fasta = WORKDIR / f"{tag}_dbshard_{shard_idx}.faa"
    shard_dmnd = WORKDIR / f"{tag}_dbshard_{shard_idx}"
    shard_out = WORKDIR / f"{tag}_dbshard_{shard_idx}.tsv"
    write_fasta(db_records, shard_fasta)

    t0 = time.perf_counter()
    subprocess.run(
        ["diamond", "makedb", "--in", str(shard_fasta), "--db", str(shard_dmnd)],
        check=True, capture_output=True, text=True,
    )
    index_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    run_diamond_blastx(query_fasta, shard_dmnd, shard_out, threads=1)
    search_time = time.perf_counter() - t0

    return shard_idx, index_time, search_time, shard_out


def merge_best_hit_per_query(shard_outputs, merged_path):
    """Reduce step: for each query, keep the single best hit (highest
    bitscore, tied-broken by lowest e-value) across all database shards.
    This is the merge/reduce cost Task 7 needs measured separately from
    the per-shard search time."""
    best = {}
    for shard_out in shard_outputs:
        if not shard_out.exists():
            continue
        with open(shard_out) as fh:
            for line in fh:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 12:
                    continue
                qid = cols[0]
                evalue = float(cols[10])
                bitscore = float(cols[11])
                key = (-bitscore, evalue)
                if qid not in best or key < best[qid][0]:
                    best[qid] = (key, line)

    with open(merged_path, "w") as out:
        for qid, (_, line) in best.items():
            out.write(line)
    return len(best)


def db_partitioning_search(query_fasta, db_fasta_source, n_workers, tag):
    db_records = parse_fasta(db_fasta_source)
    shards = split_evenly(db_records, n_workers)
    tasks = [(i, shard, query_fasta, tag) for i, shard in enumerate(shards)]

    t_wall0 = time.perf_counter()
    with mp.Pool(processes=len(shards)) as pool:
        per_worker = pool.map(_db_shard_worker, tasks)
    search_wall_time = time.perf_counter() - t_wall0

    t0 = time.perf_counter()
    merged_path = WORKDIR / f"{tag}_db_partition_merged.tsv"
    n_merged = merge_best_hit_per_query(
        [shard_out for _, _, _, shard_out in per_worker], merged_path
    )
    merge_time = time.perf_counter() - t0

    return {
        "strategy": "database_partitioning",
        "n_workers": len(shards),
        "n_queries": len(parse_fasta(query_fasta)),
        "wall_seconds": round(search_wall_time + merge_time, 4),
        "index_seconds": [round(t, 4) for _, t, _, _ in sorted(per_worker)],
        "per_worker_search_seconds": [round(t, 4) for _, _, t, _ in sorted(per_worker)],
        "merge_seconds": round(merge_time, 4),
        "queries_with_a_hit": n_merged,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=str(PROC / "query_short_reads.fasta"))
    ap.add_argument("--db-prefix", default=str(DBDIR / "db_medium_diamond"))
    ap.add_argument("--db-fasta", default=str(DBDIR / "db_medium.faa"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--tag", default="demo")
    args = ap.parse_args()

    qres = query_partitioning_search(args.query, args.db_prefix, args.workers, args.tag)
    dres = db_partitioning_search(args.query, args.db_fasta, args.workers, args.tag)

    print(json.dumps({"query_partitioning": qres, "database_partitioning": dres}, indent=2))


if __name__ == "__main__":
    main()
