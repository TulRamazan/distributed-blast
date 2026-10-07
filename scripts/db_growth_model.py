#!/usr/bin/env python3
"""
db_growth_model.py -- Task 3 (second half): model search/index cost as a
function of database size, using the three real measured points from
build_databases.py (db_small/medium/large, 300 / 10,300 / 30,300 real
sequences).

WHY A MODEL AND NOT JUST A TABLE
---------------------------------
Task 3 asks to "analyse how database growth has changed the computational
problem" -- not just report three numbers. BLAST's own seeding step scans
the database once per query, so single-query search time against an
un-indexed or minimally-indexed database is expected to scale roughly
linearly with database size (O(n) in sequence count / residue count) for
a fixed word size, while the *index build* (makeblastdb / diamond makedb /
mmseqs createdb) is close to linear in input size too, but with very
different constants -- which is exactly why Task 8's tool comparison
matters: those constants are the whole reason DIAMOND/MMseqs2 exist.

This script fits a simple power law (log-log linear regression) to
index-build time and index size vs. sequence count for each of the three
tools from the three real measured points, reports the fitted exponent
(near 1.0 = linear, as expected for these operations), and produces the
plot the report cites.

HONEST LIMITATION: three points is the minimum for a trend line, not a
statistically strong fit; the real point of this analysis is the real,
measured direction and rough shape of the curve (near-linear index-build
cost, and the index-size-vs-tool gap that motivates Task 8), not a
precise exponent. This is stated again in the report.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"


def log_log_fit(xs, ys):
    """Fit y = a * x^b via linear regression in log-log space.
    Returns (a, b)."""
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    n = len(lx)
    mean_x = sum(lx) / n
    mean_y = sum(ly) / n
    num = sum((lx[i] - mean_x) * (ly[i] - mean_y) for i in range(n))
    den = sum((lx[i] - mean_x) ** 2 for i in range(n))
    b = num / den if den else 0.0
    log_a = mean_y - b * mean_x
    return math.exp(log_a), b


def main():
    data = json.loads((TABLES / "database_build.json").read_text())
    n_seqs = [row["n_sequences"] for row in data]

    fits = {}
    for tool, time_key, size_key in [
        ("blast", "blast_makeblastdb_seconds", "blast_index_bytes"),
        ("diamond", "diamond_makedb_seconds", "diamond_index_bytes"),
        ("mmseqs", "mmseqs_createdb_seconds", "mmseqs_index_bytes"),
    ]:
        times = [row[time_key] for row in data]
        sizes = [row[size_key] for row in data]
        a_t, b_t = log_log_fit(n_seqs, times)
        a_s, b_s = log_log_fit(n_seqs, sizes)
        fits[tool] = {
            "index_time_fit": f"time ~= {a_t:.3e} * n_seqs^{b_t:.3f}",
            "time_exponent": round(b_t, 3),
            "index_size_fit": f"bytes ~= {a_s:.3e} * n_seqs^{b_s:.3f}",
            "size_exponent": round(b_s, 3),
            "bytes_per_sequence_at_largest": round(sizes[-1] / n_seqs[-1], 1),
        }

    out_json = TABLES / "db_growth_model.json"
    out_json.write_text(json.dumps(fits, indent=2))
    print(json.dumps(fits, indent=2))
    print(f"\nWrote {out_json}")

    plot(data, n_seqs, fits)


def plot(data, n_seqs, fits):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    for tool, time_key, color in [
        ("BLAST+ (makeblastdb)", "blast_makeblastdb_seconds", "#55A868"),
        ("DIAMOND (makedb)", "diamond_makedb_seconds", "#4C72B0"),
        ("MMseqs2 (createdb)", "mmseqs_createdb_seconds", "#DD8452"),
    ]:
        times = [row[time_key] for row in data]
        axes[0].plot(n_seqs, times, "o-", color=color, label=tool)
    axes[0].set_xlabel("Database size (sequences)")
    axes[0].set_ylabel("Index build time (s)")
    axes[0].set_title("Index build time vs. database size\n(measured, 3 real sizes)")
    axes[0].legend(fontsize=8)

    for tool, size_key, color in [
        ("BLAST+ index", "blast_index_bytes", "#55A868"),
        ("DIAMOND index", "diamond_index_bytes", "#4C72B0"),
        ("MMseqs2 index", "mmseqs_index_bytes", "#DD8452"),
    ]:
        sizes = [row[size_key] / 1e6 for row in data]
        axes[1].plot(n_seqs, sizes, "s-", color=color, label=tool)
    axes[1].set_xlabel("Database size (sequences)")
    axes[1].set_ylabel("Index size (MB)")
    axes[1].set_title("Index size vs. database size\n(measured, 3 real sizes)")
    axes[1].legend(fontsize=8)

    fig.suptitle("Task 3 -- database growth vs. computational cost (real measurements)")
    fig.tight_layout()
    out_path = FIGURES / "db_growth_model.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
