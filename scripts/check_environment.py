"""Verify the local Exasol connection and Python UDF without printing credentials."""

import argparse
import hashlib
import ipaddress
import json
import os
import socket
import ssl
from pathlib import Path

import pyexasol


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-dir", type=Path, default=Path("private/exasol-rootful"))
    parser.add_argument("--write-env", action="store_true", help="Create a private .env if absent")
    args = parser.parse_args()
    deployment = json.loads((args.deployment_dir / "deployment.json").read_text())
    secrets = json.loads((args.deployment_dir / "secrets.json").read_text())
    settings = deployment["connection"]
    host = settings["host"]
    port = settings["dbPort"]
    if not ipaddress.ip_address(host).is_loopback:
        raise SystemExit("This feasibility check only trusts a local loopback deployment.")

    # Bootstrap the certificate only over the locally bound database port.
    # Subsequent connections verify its SHA-256 fingerprint through pyexasol.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with (
        socket.create_connection((host, port), timeout=10) as raw_socket,
        context.wrap_socket(raw_socket, server_hostname=host) as tls_socket,
    ):
        fingerprint = hashlib.sha256(tls_socket.getpeercert(binary_form=True)).hexdigest()

    dsn = f"{host}/{fingerprint}:{port}"
    connection = pyexasol.connect(
        dsn=dsn,
        user=settings["username"],
        password=secrets["dbPassword"],
        encryption=True,
        connection_timeout=10,
    )
    try:
        sql_result = connection.execute("SELECT 1").fetchone()[0]
        udf_result = connection.execute("SELECT MILAAN_CHECK.PING()").fetchone()[0]
        if sql_result != 1 or udf_result != "pong":
            raise SystemExit("Unexpected SQL or Python UDF result.")
        report = {
            "sql_connection": "passed",
            "python_udf": "pong",
            "pyexasol": pyexasol.__version__,
            "tls": "encrypted, SHA-256 certificate fingerprint verified",
            "dsn": dsn,
            "database_version": connection.execute(
                "SELECT PARAM_VALUE FROM EXA_METADATA WHERE PARAM_NAME = 'databaseProductVersion'"
            ).fetchone()[0],
        }
        report_path = args.deployment_dir.parent / "environment-check.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        if args.write_env:
            env_path = Path(".env")
            if env_path.exists():
                print("Existing .env preserved.")
            else:
                env_values = {
                    "EXASOL_DSN": dsn,
                    "EXASOL_USER": settings["username"],
                    "EXASOL_PASSWORD": secrets["dbPassword"],
                }
                descriptor = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as env_file:
                    env_file.write("# Local Exasol connection. Never commit this file.\n")
                    for key, value in env_values.items():
                        env_file.write(f"{key}={json.dumps(value)}\n")
                    if os.geteuid() == 0 and "SUDO_UID" in os.environ:
                        os.fchown(
                            env_file.fileno(),
                            int(os.environ["SUDO_UID"]),
                            int(os.environ["SUDO_GID"]),
                        )
                print("Created .env with owner-only permissions.")
        print(json.dumps(report, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
