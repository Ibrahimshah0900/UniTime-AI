from __future__ import annotations

import argparse
import getpass

from fastapi import HTTPException

from backend.auth_service import create_privileged_account
from backend.auth_types import UserRole
from backend.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a privileged UniTime AI user account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", dest="full_name", required=True)
    parser.add_argument("--role", required=True, choices=["faculty", "coordinator", "admin"])
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")

    try:
        with SessionLocal() as db:
            user = create_privileged_account(
                db,
                email=args.email,
                full_name=args.full_name,
                password=password,
                role=UserRole(args.role),
            )
    except (ValueError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        raise SystemExit(detail) from exc

    print(f"Created {user.role} account: {user.email}")


if __name__ == "__main__":
    main()
