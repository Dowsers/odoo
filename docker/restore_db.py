#!/usr/bin/env python3
"""Restore an Odoo backup (zip with dump.sql and the filestore) into a database.

``odoo db load`` always restores a *copy*: it gives the database a new
identifier (database.uuid) and a new secret key (database.secret, which signs
sessions and tokens), and resets web.base.url. For a migration or a disaster
recovery the database must come back unchanged, so this script calls the same
Odoo function with ``copy=False``, like the "this database was moved" choice of
the database manager.

Usage: restore_db.py [--neutralize] [--force] <database> <backup.zip>
    --neutralize  test copy: new identifier and secret, no e-mail sent,
                  scheduled actions disabled
    --force       drop the database first if it exists

The connection settings come from the Odoo configuration file (ODOO_RC).
"""
import argparse
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import odoo.init  # noqa: E402, F401 - core setup, must come first
from odoo.service.db import exp_db_exist, exp_drop, restore_db  # noqa: E402
from odoo.tools import config  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Restore an Odoo backup.")
    parser.add_argument('--neutralize', action='store_true')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('database')
    parser.add_argument('backup')
    args = parser.parse_args()

    if not zipfile.is_zipfile(args.backup):
        sys.exit("%s is not an Odoo backup (zip file with dump.sql)." % args.backup)
    config.parse_config([], setup_logging=True)
    config['list_db'] = True  # database management is what this script is for
    if exp_db_exist(args.database):
        if not args.force:
            sys.exit("Database %s already exists: use --force to replace it." % args.database)
        exp_drop(args.database)
    restore_db(args.database, args.backup, copy=args.neutralize, neutralize_database=args.neutralize)
    print("Database %s restored%s." % (args.database, " as a neutralized copy" if args.neutralize else ""))


if __name__ == '__main__':
    main()
