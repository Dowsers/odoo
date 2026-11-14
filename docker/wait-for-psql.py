#!/usr/bin/env python3
"""Wait until PostgreSQL accepts connections (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD).

Exit code 1 after DB_WAIT_TIMEOUT seconds (default 60).
"""
import os
import sys
import time

import psycopg2

timeout = int(os.environ.get('DB_WAIT_TIMEOUT', '60'))
deadline = time.monotonic() + timeout
error = None
while time.monotonic() < deadline:
    try:
        psycopg2.connect(
            host=os.environ['DB_HOST'], port=os.environ['DB_PORT'], user=os.environ['DB_USER'],
            password=os.environ['DB_PASSWORD'], dbname='postgres', connect_timeout=5,
        ).close()
        sys.exit(0)
    except psycopg2.OperationalError as exception:
        error = exception
        time.sleep(1)
print("PostgreSQL unreachable after %s seconds: %s" % (timeout, str(error).strip()), file=sys.stderr)
sys.exit(1)
