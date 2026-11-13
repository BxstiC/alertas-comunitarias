FROM postgres:16-alpine

COPY replica-entrypoint.sh /usr/local/bin/replica-entrypoint.sh
RUN chmod 755 /usr/local/bin/replica-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/replica-entrypoint.sh"]
CMD ["postgres"]
