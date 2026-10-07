#!/usr/bin/env bash
# run_smoke_test.sh -- the reproducibility bundle's small, fast
# verification test (handbook: "small test dataset included for
# verification", "one documented command reproduces the headline result").
#
# Uses the tiny, committed test/data/ files (30 real protein sequences,
# 10 real short-read-derived queries -- small enough to be committed to
# git directly, unlike the full data/ pipeline outputs) to check that the
# whole toolchain (makeblastdb, diamond makedb, mmseqs createdb, and all
# three search tools) is installed and produces non-empty output, in well
# under a minute, without needing any of the larger fetched/built data.
#
# Usage:  bash test/run_smoke_test.sh
# Exit code 0 = pass.
set -euo pipefail
cd "$(dirname "$0")"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "[1/4] makeblastdb on tiny test database ..."
makeblastdb -in data/tiny_db.faa -dbtype prot -out "$TMP/tinydb" >/dev/null

echo "[2/4] diamond makedb on tiny test database ..."
diamond makedb --in data/tiny_db.faa --db "$TMP/tinydb_diamond" --quiet

echo "[3/4] mmseqs createdb on tiny test database ..."
mmseqs createdb data/tiny_db.faa "$TMP/tinydb_mmseqs" -v 1 >/dev/null

echo "[4/4] running all three search tools against the tiny test queries ..."
blastx -query data/tiny_queries.fasta -db "$TMP/tinydb" \
    -outfmt 6 -out "$TMP/blast.tsv"
diamond blastx --query data/tiny_queries.fasta --db "$TMP/tinydb_diamond" \
    --out "$TMP/diamond.tsv" --outfmt 6 --quiet
mmseqs easy-search data/tiny_queries.fasta data/tiny_db.faa \
    "$TMP/mmseqs.tsv" "$TMP/mmseqs_tmp" --search-type 2 -v 1 >/dev/null

for f in blast.tsv diamond.tsv mmseqs.tsv; do
    n=$(wc -l < "$TMP/$f")
    echo "  $f: $n result lines"
done

echo ""
echo "PASS -- toolchain is installed correctly and produces results."
echo "This only exercises the tiny committed test/ dataset. To reproduce"
echo "the full headline result (the measured scaling curve), see README.md."
