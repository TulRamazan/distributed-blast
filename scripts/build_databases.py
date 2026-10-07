#!/usr/bin/env python3
"""
build_databases.py -- Task 2 (Database work) and half of Task 3 (database-growth
model). Builds three real BLAST protein databases of increasing size from the
raw data fetched by fetch_data.sh, and records storage footprint and
preprocessing (indexing) time for each -- the exact quantities Task 2 of the
project card asks for ("document the storage, preprocessing time and index
size for each").

Database growth ladder (all built from genuinely real sequences, concatenated
without modification):
  db_small  :    300 sequences  (nr_300.faa)
  db_medium : 10,300 sequences  (nr_300.faa + nr_10k.faa)
  db_large  : 30,300 sequences  (nr_300.faa + nr_10k.faa + uniprot_trembl_20k.fasta)

This ladder lets Task 3 (how has database growth changed the computational
problem?) be answered with a real measured curve instead of an assumption.
"""
import subprocess
import time
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DBDIR = ROOT / "data" / "processed" / "blastdb"
DBDIR.mkdir(parents=True, exist_ok=True)

LADDER = {
    "db_small":  [RAW / "nr_300.faa"],
    "db_medium": [RAW / "nr_300.faa", RAW / "nr_10k.faa"],
    "db_large":  [RAW / "nr_300.faa", RAW / "nr_10k.faa", RAW / "uniprot_trembl_20k.fasta"],
}


def count_seqs(fasta_path):
    n = 0
    with open(fasta_path) as fh:
        for line in fh:
            if line.startswith(">"):
                n += 1
    return n


def dir_size_bytes(path):
    total = 0
    for p in Path(path).parent.glob(Path(path).name + "*"):
        total += p.stat().st_size
    return total


def build_one(name, fasta_sources):
    combined_fasta = DBDIR / f"{name}.faa"
    with open(combined_fasta, "wb") as out:
        for src in fasta_sources:
            out.write(src.read_bytes())

    n_seqs = count_seqs(combined_fasta)
    raw_size = combined_fasta.stat().st_size

    db_prefix = DBDIR / name
    t0 = time.perf_counter()
    subprocess.run(
        ["makeblastdb", "-in", str(combined_fasta), "-dbtype", "prot",
         "-out", str(db_prefix), "-title", name],
        check=True, capture_output=True, text=True,
    )
    makeblastdb_time = time.perf_counter() - t0

    # DIAMOND needs its own binary index; build it too and time it, since
    # Task 8 will need a diamond index for every database size anyway.
    dmnd_prefix = DBDIR / f"{name}_diamond"
    t0 = time.perf_counter()
    subprocess.run(
        ["diamond", "makedb", "--in", str(combined_fasta), "--db", str(dmnd_prefix)],
        check=True, capture_output=True, text=True,
    )
    diamond_index_time = time.perf_counter() - t0

    # MMseqs2 also needs its own DB format.
    mmseqs_prefix = DBDIR / f"{name}_mmseqs"
    t0 = time.perf_counter()
    subprocess.run(
        ["mmseqs", "createdb", str(combined_fasta), str(mmseqs_prefix)],
        check=True, capture_output=True, text=True,
    )
    mmseqs_index_time = time.perf_counter() - t0

    blast_index_size = dir_size_bytes(db_prefix)
    diamond_index_size = dmnd_prefix.with_suffix(".dmnd").stat().st_size
    mmseqs_index_size = dir_size_bytes(mmseqs_prefix)

    return {
        "name": name,
        "n_sequences": n_seqs,
        "raw_fasta_bytes": raw_size,
        "blast_makeblastdb_seconds": round(makeblastdb_time, 4),
        "blast_index_bytes": blast_index_size,
        "diamond_makedb_seconds": round(diamond_index_time, 4),
        "diamond_index_bytes": diamond_index_size,
        "mmseqs_createdb_seconds": round(mmseqs_index_time, 4),
        "mmseqs_index_bytes": mmseqs_index_size,
    }


def main():
    results = []
    for name, sources in LADDER.items():
        print(f"Building {name} from {[s.name for s in sources]} ...")
        row = build_one(name, sources)
        print(f"  -> {row['n_sequences']} sequences, "
              f"makeblastdb {row['blast_makeblastdb_seconds']}s, "
              f"diamond makedb {row['diamond_makedb_seconds']}s, "
              f"mmseqs createdb {row['mmseqs_createdb_seconds']}s")
        results.append(row)

    out_path = ROOT / "results" / "tables" / "database_build.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
