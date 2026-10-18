# FalkorDB for hosted deployments (Render private service).
# Same pinned image as compose.yaml; the password comes from the FALKORDB_PASSWORD environment variable at
# start-up (Render cannot interpolate one env var inside another), AOF persistence on, browser UI off.
FROM falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a
ENV BROWSER=0
ENTRYPOINT ["/bin/sh", "-c", "export REDIS_ARGS=\"--appendonly yes --requirepass ${FALKORDB_PASSWORD:?FALKORDB_PASSWORD is required}\"; exec /var/lib/falkordb/bin/run.sh"]
