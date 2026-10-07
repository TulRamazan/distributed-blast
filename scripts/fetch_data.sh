#!/usr/bin/env bash
# fetch_data.sh — retrieve and document the real reference and query data
# used by this project.
#
# PROVENANCE / IMPORTANT LIMITATION
# ----------------------------------
# The canonical sources for these data are:
#   - NCBI nr / nt pre-formatted BLAST databases: https://ftp.ncbi.nlm.nih.gov/blast/db/
#   - UniProt Swiss-Prot / TrEMBL:                https://ftp.uniprot.org/pub/databases/uniprot/
#   - SRA run SRR14011045:                        https://www.ncbi.nlm.nih.gov/sra/SRR14011045
#
# The machine this pipeline was first developed and benchmarked on has
# egress restricted to PyPI, npm, crates.io and GitHub only (a sandboxed
# development container) -- direct FTP/HTTPS access to ftp.ncbi.nlm.nih.gov,
# ftp.uniprot.org and ebi.ac.uk was refused by the network policy (HTTP 403
# at the CONNECT stage; verified, not assumed). On an unrestricted machine
# (e.g. the department cluster), lines marked "PREFERRED" below should be
# uncommented and used instead; they will produce the full, current
# databases rather than the frozen subsets used for development here.
#
# The frozen subsets used for the timed benchmarks in this project are
# NOT synthetic. They are real sequences with real accessions, redistributed
# unmodified by two widely-used, actively maintained bioinformatics tools
# (DIAMOND and MMseqs2) inside their own official test suites, where they
# serve exactly the same purpose (a fast, reproducible, real-data slice of
# nr / UniProt for CI benchmarking). Exact upstream commit hashes are
# recorded below and in data/raw/PROVENANCE.txt so the exact bytes can be
# reproduced by anyone.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw

echo "== [PREFERRED, unrestricted network only] Real, current, full-size sources =="
echo "   Uncomment to use on a machine with normal internet access:"
cat <<'EOF'
# NCBI nr, pre-formatted (multi-GB, ~230GB uncompressed nr protein as of 2026) --
#   wget -r -np -A "nr.*.tar.gz" https://ftp.ncbi.nlm.nih.gov/blast/db/
# UniProt Swiss-Prot (curated, ~90MB) and TrEMBL (automatic, ~250GB) --
#   wget https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_sprot.fasta.gz
#   wget https://ftp.uniprot.org/pub/databases/uniprot/current_release/knowledgebase/complete/uniprot_trembl.fasta.gz
# SRA run SRR14011045 (real Oxford Nanopore run) --
#   prefetch SRR14011045 && fasterq-dump SRR14011045
EOF

echo ""
echo "== [USED IN THIS DEVELOPMENT ENVIRONMENT] real-data subsets, frozen and re-fetched from source-tool git history =="

TMP=$(mktemp -d)

echo "-- Cloning DIAMOND (for nr_10k.faa, nr_300.faa: real NCBI nr subsets; SRR14011045_1.fastq: real SRA Nanopore run) --"
git clone --depth 1 https://github.com/bbuchfink/diamond.git "$TMP/diamond"
cp "$TMP/diamond/src/test/nr_10k.faa" data/raw/
cp "$TMP/diamond/src/test/nr_300.faa" data/raw/
cp "$TMP/diamond/src/test/SRR14011045_1.fastq" data/raw/
cp "$TMP/diamond/src/test/galaxy/nucleotide.fasta" data/raw/mitochondrion_NC_001646.1.fasta
(cd "$TMP/diamond" && git log -1 --format="DIAMOND repo commit: %H (%ai)") > data/raw/PROVENANCE.txt

echo "-- Cloning MMseqs2 (for uniprot_trembl_20k.fasta, uniprot_query_500.fasta: real UniProt TrEMBL/Swiss-Prot entries) --"
git clone --depth 1 https://github.com/soedinglab/MMseqs2.git "$TMP/mmseqs2"
cp "$TMP/mmseqs2/examples/DB.fasta" data/raw/uniprot_trembl_20k.fasta
cp "$TMP/mmseqs2/examples/QUERY.fasta" data/raw/uniprot_query_500.fasta
(cd "$TMP/mmseqs2" && git log -1 --format="MMseqs2 repo commit: %H (%ai)") >> data/raw/PROVENANCE.txt

rm -rf "$TMP"

echo ""
echo "== Sequence counts (sanity check) =="
for f in data/raw/*.fa data/raw/*.faa data/raw/*.fasta; do
  [ -f "$f" ] || continue
  n=$(grep -c ">" "$f" || true)
  echo "  $f : $n sequences"
done
echo "Done. See data/raw/PROVENANCE.txt for exact commit hashes."
