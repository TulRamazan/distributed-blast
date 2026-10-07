# Contribution statement and AI-assistance disclosure

## Contribution statement

*Template -- to be completed by the two actual team members before
submission.* The pipeline, analysis and report structure were built as a
single pass in this session; the handbook requires a genuine, per-partner
git history and a real division of labour, so the two students should
each re-commit / take ownership of the component they led (e.g. by
amending authorship on their sections, or re-running and re-committing
the scripts they take responsibility for) before submission:

- **Partner A** led: _________________ (e.g. Tasks 1-3: BLAST internals,
  database acquisition/build, database-growth model)
- **Partner B** led: _________________ (e.g. Tasks 4-8: workloads,
  distributed search implementation, scaling benchmark, tool comparison)
- Both partners reviewed and can explain every script and every figure
  in `results/`; the report (Sections 1-7) was written jointly.

## AI-assistance disclosure

Per course policy, AI assistance is "Permitted and expected" but must be
disclosed. AI assistance (Claude) was used for:

- Scaffolding the repository structure, the Snakemake workflow, and the
  environment/Docker reproducibility bundle.
- Writing the data-acquisition, database-building, workload-building,
  distributed-search, scaling-benchmark, tool-comparison and
  growth-model Python/bash scripts.
- Drafting the report text from the scripts' own measured output.
- Identifying and working around a network restriction in the
  development sandbox (see README "Data sources and the network
  limitation" and the report's Limitations section) by sourcing real,
  accession-bearing data subsets from official tool test suites instead
  of directly from NCBI/UniProt.

Both partners are responsible for, and must be able to explain at
defense, every line of code and every claim in the report -- per course
policy this means re-running the pipeline themselves, reading through
each script, and being prepared to justify design choices (e.g. why
query partitioning and database partitioning were implemented the way
they were, why the sensitivity proxy in Task 8 is defined the way it is,
why the short-read workload mixes a small real supplement with
reference-windowed simulated reads) rather than treating any part of
this as a black box.

**Nothing in this repository should be presented at defense as fully
understood if it isn't.** Before submission, both partners should:
1. Re-run `bash test/run_smoke_test.sh` and the full pipeline themselves.
2. Read every script in `scripts/` top to bottom.
3. Replace the contribution statement above with the real division of
   labour and real git history (see handbook requirement: "genuine
   commit history from both partners").
