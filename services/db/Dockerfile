FROM postgres:16.15-alpine

COPY init.sql /docker-entrypoint-initdb.d/10-init.sql
COPY seed.sh /docker-entrypoint-initdb.d/20-seed.sh
COPY demo-history.sql /docker-entrypoint-initdb.d/30-demo-history.sql
COPY entrypoint-wrapper.sh /usr/local/bin/mirror-db-entrypoint
RUN chmod 0555 /docker-entrypoint-initdb.d/20-seed.sh /usr/local/bin/mirror-db-entrypoint

ENTRYPOINT ["/usr/local/bin/mirror-db-entrypoint"]
CMD ["postgres"]

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" || exit 1
