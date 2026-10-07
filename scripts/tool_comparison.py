#!/usr/bin/env python3
"""
tool_comparison.py -- Task 8: compare classic BLAST+ against DIAMOND and
MMseqs2, quantifying what sensitivity is traded for their speed. All three
tools run the SAME translated-nucleotide-query-vs-protein-database search
(blastx-equivalent) against the SAME query subset and the SAME database,
so runtime and hit counts are directly comparable.

Query subset: classic BLAST+ blastx is dramatically slower than the
accelerated tools (that speed gap is the whole point of Task 8), so a
fixed, identical subset of the real short-read workload is used for all
three tools rather than the full 815-read set -- this keeps the benchmark
finishing in reasonable time while still being a fair, apples-to-apples
comparison (same input, same database, same output format family).

Sensitivity proxy: since there is no curated gold-standard truth set for
these real, unannotated sequences, sensitivity is approximated the way
method papers commonly do when no ground truth exists: using BLAST+'s own
result as the reference ("what a slow, thorough search finds") and
measuring, for each accelerated tool, (a) how many of BLAST+'s query hits
it also finds a hit for (recall proxy) and (b) how its top-hit bitscore
compares to BLAST+'s top-hit bitscore for the same query, when both find
one. This is explicitly a proxy relative to BLAST+, not an absolute
sensitivity truth -- and that limitation is stated again in the report.
"""
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
DBDIR = PROC / "blastdb"
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"
WORKDIR = PROC / "tool_comparison_work"
WORKDIR.mkdir(parents=True, exist_ok=True)

N_QUERY_SUBSET = 60  # fixed, identical subset for all three tools
DB_NAME = "db_medium"


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


def write_subset():
    all_records = parse_fasta(PROC / "query_short_reads.fasta")
    subset = all_records[:N_QUERY_SUBSET]
    path = WORKDIR / "query_subset.fasta"
    with open(path, "w") as out:
        for h, s in subset:
            out.write(f">{h}\n{s}\n")
    return path, len(subset)


def run_blast_plus(query_fasta, out_tsv):
    t0 = time.perf_counter()
    subprocess.run(
        ["blastx", "-query", str(query_fasta),
         "-db", str(DBDIR / DB_NAME),
         "-out", str(out_tsv),
         "-outfmt", "6 qseqid sseqid pident length evalue bitscore",
         "-max_target_seqs", "5",
         "-num_threads", "2"],
        check=True, capture_output=True, text=True,
    )
    return time.perf_counter() - t0


def run_diamond(query_fasta, out_tsv, sensitive=False):
    cmd = ["diamond", "blastx", "--query", str(query_fasta),
           "--db", str(DBDIR / f"{DB_NAME}_diamond"),
           "--out", str(out_tsv),
           "--outfmt", "6", "qseqid", "sseqid", "pident", "length", "evalue", "bitscore",
           "--max-target-seqs", "5", "--threads", "2", "--quiet"]
    if sensitive:
        cmd.append("--ultra-sensitive")
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return time.perf_counter() - t0


def run_mmseqs(query_fasta, out_tsv, sensitive=False, tag="default"):
    tmp = WORKDIR / f"mmseqs_tmp_{tag}"
    tmp.mkdir(exist_ok=True)
    cmd = ["mmseqs", "easy-search", str(query_fasta),
           str(DBDIR / f"{DB_NAME}.faa"),
           str(out_tsv), str(tmp),
           "--search-type", "2",
           "--format-output", "query,target,pident,alnlen,evalue,bits",
           "--threads", "2", "-v", "1"]
    cmd += ["-s", "7.5"] if sensitive else ["-s", "4.0"]
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return time.perf_counter() - t0


def load_hits(tsv_path):
    """qid -> list of (bitscore, evalue, sseqid), best first."""
    hits = {}
    if not tsv_path.exists():
        return hits
    with open(tsv_path) as fh:
        for line in fh:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 6:
                continue
            qid, sseqid = cols[0], cols[1]
            evalue, bitscore = float(cols[4]), float(cols[5])
            hits.setdefault(qid, []).append((bitscore, evalue, sseqid))
    for qid in hits:
        hits[qid].sort(key=lambda t: (-t[0], t[1]))
    return hits


def sensitivity_proxy(reference_hits, other_hits):
    ref_queries_with_hit = set(reference_hits.keys())
    other_queries_with_hit = set(other_hits.keys())
    if not ref_queries_with_hit:
        return {"recall_proxy": None, "mean_bitscore_ratio": None}

    recall = len(ref_queries_with_hit & other_queries_with_hit) / len(ref_queries_with_hit)

    ratios = []
    for qid in ref_queries_with_hit & other_queries_with_hit:
        ref_top = reference_hits[qid][0][0]
        other_top = other_hits[qid][0][0]
        if ref_top > 0:
            ratios.append(other_top / ref_top)
    mean_ratio = sum(ratios) / len(ratios) if ratios else None

    return {
        "recall_proxy": round(recall, 3),
        "mean_bitscore_ratio_vs_blastplus": round(mean_ratio, 3) if mean_ratio else None,
        "n_queries_compared": len(ratios),
    }


def plot_comparison(rows, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = [r["tool"] for r in rows]
    times = [r["seconds"] for r in rows]
    palette = ["#55A868", "#4C72B0", "#4C72B0", "#DD8452", "#DD8452"]

    fig, ax1 = plt.subplots(figsize=(8.5, 5.2))
    bars = ax1.bar(names, times, color=palette[:len(names)])
    ax1.set_ylabel("Wall time (s), log scale")
    ax1.set_yscale("log")
    ax1.set_title(f"Task 8 -- runtime, {N_QUERY_SUBSET} identical queries vs {DB_NAME}")
    ax1.set_xticklabels(names, rotation=20, ha="right", fontsize=9)
    ax1.margins(y=0.25)
    for b, r in zip(bars, rows):
        recall = r.get("recall_proxy")
        label = f"{r['seconds']:.2f}s"
        if recall is not None:
            label += f"\nrecall={recall}"
        ax1.text(b.get_x() + b.get_width() / 2, b.get_height(), label,
                  ha="center", va="bottom", fontsize=7.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


N_REPEATS = 3  # median of 3 runs -- damps OS page-cache noise between tools


def timed_median(fn, *args, **kwargs):
    times = []
    for _ in range(N_REPEATS):
        times.append(fn(*args, **kwargs))
    times.sort()
    return times[len(times) // 2], times


def main():
    query_fasta, n = write_subset()
    print(f"Fixed comparison subset: {n} queries -> {query_fasta}")
    print(f"(each tool/mode run {N_REPEATS}x; reported time is the median, "
          f"to damp OS page-cache noise between tools)")

    blast_out = WORKDIR / "blastplus.tsv"
    diamond_out = WORKDIR / "diamond.tsv"
    diamond_sens_out = WORKDIR / "diamond_sensitive.tsv"
    mmseqs_out = WORKDIR / "mmseqs.tsv"
    mmseqs_sens_out = WORKDIR / "mmseqs_sensitive.tsv"

    print("Running BLAST+ blastx ...")
    t_blast, r_blast = timed_median(run_blast_plus, query_fasta, blast_out)
    print(f"  median {t_blast:.3f}s (runs: {[round(x,3) for x in r_blast]})")

    print("Running DIAMOND blastx (default sensitivity) ...")
    t_diamond, r_d = timed_median(run_diamond, query_fasta, diamond_out, sensitive=False)
    print(f"  median {t_diamond:.3f}s (runs: {[round(x,3) for x in r_d]})")

    print("Running DIAMOND blastx (--ultra-sensitive) ...")
    t_diamond_sens, r_ds = timed_median(run_diamond, query_fasta, diamond_sens_out, sensitive=True)
    print(f"  median {t_diamond_sens:.3f}s (runs: {[round(x,3) for x in r_ds]})")

    print("Running MMseqs2 easy-search (translated, -s 4.0 default) ...")
    t_mmseqs, r_m = timed_median(run_mmseqs, query_fasta, mmseqs_out, sensitive=False, tag="default")
    print(f"  median {t_mmseqs:.3f}s (runs: {[round(x,3) for x in r_m]})")

    print("Running MMseqs2 easy-search (translated, -s 7.5 sensitive) ...")
    t_mmseqs_sens, r_ms = timed_median(run_mmseqs, query_fasta, mmseqs_sens_out, sensitive=True, tag="sensitive")
    print(f"  median {t_mmseqs_sens:.3f}s (runs: {[round(x,3) for x in r_ms]})")

    blast_hits = load_hits(blast_out)
    diamond_hits = load_hits(diamond_out)
    diamond_sens_hits = load_hits(diamond_sens_out)
    mmseqs_hits = load_hits(mmseqs_out)
    mmseqs_sens_hits = load_hits(mmseqs_sens_out)

    rows = [
        {"tool": "BLAST+ (blastx)", "seconds": round(t_blast, 4),
         "n_queries_with_hit": len(blast_hits),
         "recall_proxy": 1.0, "mean_bitscore_ratio_vs_blastplus": 1.0,
         "note": "reference tool for the sensitivity proxy"},
        {"tool": "DIAMOND default", "seconds": round(t_diamond, 4),
         "n_queries_with_hit": len(diamond_hits),
         **sensitivity_proxy(blast_hits, diamond_hits)},
        {"tool": "DIAMOND --ultra-sensitive", "seconds": round(t_diamond_sens, 4),
         "n_queries_with_hit": len(diamond_sens_hits),
         **sensitivity_proxy(blast_hits, diamond_sens_hits)},
        {"tool": "MMseqs2 -s 4.0 (default)", "seconds": round(t_mmseqs, 4),
         "n_queries_with_hit": len(mmseqs_hits),
         **sensitivity_proxy(blast_hits, mmseqs_hits)},
        {"tool": "MMseqs2 -s 7.5 (sensitive)", "seconds": round(t_mmseqs_sens, 4),
         "n_queries_with_hit": len(mmseqs_sens_hits),
         **sensitivity_proxy(blast_hits, mmseqs_sens_hits)},
    ]

    for r in rows:
        speedup = round(t_blast / r["seconds"], 2) if r["seconds"] > 0 else None
        r["speedup_vs_blastplus"] = speedup

    out_json = TABLES / "tool_comparison.json"
    out_json.write_text(json.dumps(rows, indent=2))
    print(f"\nWrote {out_json}")
    print(json.dumps(rows, indent=2))

    plot_comparison(rows, FIGURES / "tool_comparison.png")
    print(f"Wrote {FIGURES / 'tool_comparison.png'}")


if __name__ == "__main__":
    main()
