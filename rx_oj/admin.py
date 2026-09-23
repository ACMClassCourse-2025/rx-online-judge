"""Operator-only account provisioning: python -m rx_oj.admin --help."""

import argparse
import getpass
import sqlite3
import sys

from .auth import password_hash, username
from .config import Settings
from .db import Database


def main():
    parser = argparse.ArgumentParser(description="Manage judge accounts (no web registration)")
    actions = parser.add_subparsers(dest="action", required=True)
    for command in ("create-user", "reset-password", "disable-user", "enable-user"):
        action = actions.add_parser(command)
        action.add_argument("username")
        if command in ("create-user", "reset-password"):
            action.add_argument(
                "--password-stdin",
                action="store_true",
                help="Read password from stdin instead of a hidden prompt",
            )
        if command == "create-user":
            action.add_argument("--admin", action="store_true")
    actions.add_parser("list-users")
    args = parser.parse_args()
    db = Database(Settings().db_path)
    try:
        if args.action == "list-users":
            with db.connect() as conn:
                for row in conn.execute(
                    "SELECT username, is_admin, active FROM users ORDER BY username"
                ):
                    print(
                        f"{row['username']}\t{'admin' if row['is_admin'] else 'student'}\t"
                        f"{'active' if row['active'] else 'disabled'}"
                    )
            return
        name = username(args.username)
        account = db.user_by_name(name)
        if args.action == "create-user" and account:
            raise ValueError("Username already exists")
        if args.action != "create-user" and not account:
            raise ValueError("Account does not exist")
        if args.action in ("create-user", "reset-password"):
            password = (
                sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass()
            )
            if not args.password_stdin and getpass.getpass("Confirm password: ") != password:
                raise ValueError("Passwords do not match")
            encoded = password_hash(password)
            if args.action == "create-user":
                db.create_user(name, encoded, args.admin)
            else:
                db.reset_password(account["id"], encoded)
        else:
            db.set_active(account["id"], args.action == "enable-user")
        print(f"{args.action}: {name}")
    except (ValueError, sqlite3.IntegrityError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
