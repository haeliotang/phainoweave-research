# Fixed-toolchain offline reproduction environment for R1-D experiments.
# Build: docker build -t phainoweave-repro:1.94-py311 containers/repro
FROM rust:1.94-slim@sha256:cf09adf8c3ebaba10779e5c23ff7fe4df4cccdab8a91f199b0c142c53fef3e1a

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip make \
    && rm -rf /var/lib/apt/lists/*

RUN rustup component add rustfmt clippy

RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir \
        pytest==8.4.2 \
        numpy==2.4.4 \
        sympy==1.14.0 \
        scipy==1.17.1
ENV PATH="/venv/bin:/usr/local/cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV CARGO_HOME="/usr/local/cargo"
WORKDIR /work

CMD ["bash"]
