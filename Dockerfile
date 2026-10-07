# Dockerfile -- alternative to environment.yml for the reproducibility
# bundle (handbook: "container definition OR locked environment file").
#
# Build:  docker build -t distributed-blast .
# Run:    docker run --rm -v "$PWD/results:/proj/results" distributed-blast
#
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ncbi-blast+ \
        diamond-aligner \
        mmseqs2 \
        python3 \
        python3-pip \
        python3-matplotlib \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /proj
COPY . /proj

# One documented command reproduces the headline result (see README).
CMD ["bash", "-c", "scripts/fetch_data.sh && python3 scripts/build_databases.py && python3 scripts/build_workloads.py && python3 scripts/distributed_search.py && python3 scripts/scaling_benchmark.py && python3 scripts/tool_comparison.py && python3 scripts/db_growth_model.py"]
