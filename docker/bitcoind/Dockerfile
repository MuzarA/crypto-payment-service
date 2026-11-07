# Bitcoin Core (open-source криптокошелёк + узел) из официальных бинарников bitcoincore.org
FROM debian:bookworm-slim

ARG BITCOIN_VERSION=27.1
ARG TARGETARCH

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && case "${TARGETARCH:-amd64}" in \
        amd64) ARCH=x86_64-linux-gnu ;; \
        arm64) ARCH=aarch64-linux-gnu ;; \
        *) echo "unsupported arch ${TARGETARCH}" && exit 1 ;; \
    esac \
 && BASE=https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION} \
 && FILE=bitcoin-${BITCOIN_VERSION}-${ARCH}.tar.gz \
 && curl -fsSLO ${BASE}/${FILE} \
 && curl -fsSLO ${BASE}/SHA256SUMS \
 && grep " ${FILE}\$" SHA256SUMS | sha256sum -c - \
 && tar -xzf ${FILE} -C /usr/local --strip-components=1 \
 && rm -f ${FILE} SHA256SUMS \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

VOLUME ["/root/.bitcoin"]
EXPOSE 18443
CMD ["bitcoind", "-regtest", "-printtoconsole"]
