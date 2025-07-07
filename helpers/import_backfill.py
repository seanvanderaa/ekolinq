"""CLI command to import legacy pickup requests from ./import/backfill.csv

Usage:
    flask import-backfill [--path PATH]

Drop this file somewhere on the PYTHONPATH (e.g. *app/helpers/import_backfill.py*).  Then, from your application
factory you can simply do::

    from app.helpers import import_backfill  # <- adjust to your real module path
    import_backfill.register(app)

That exposes a `flask import-backfill` command that reads the legacy CSV and
inserts one **PickupRequest** per row, zeroing‑out personal data, forcing
`status="Complete"`, and letting the model’s *before_insert* listener generate
the `request_id` for you.
"""

import csv
from datetime import datetime

import click
from flask.cli import with_appcontext

from flask import current_app
from models import PickupRequest, db


@click.command("import-backfill")
@click.option(
    "--path",
    default="import/backfill.csv",
    show_default=True,
    help="Path to the legacy CSV you want to ingest.",
)
@click.option(
    "--purge/--no-purge",
    default=False,
    help="Delete previous backfill entries (identified by admin_notes) before importing.",
)
@with_appcontext
def import_backfill(path: str, purge: bool) -> None:
    """Read *path* and insert each row into **pickup_requests**.

    CSV columns expected (tab- or comma-delimited):
        Last Name, First Name, Address 1, Address 2, City, Zip, Email,
        Phone, Last Pick-Up / Drop-Off, Awareness

    Rows with no discernible date or where date == "inquiry" are skipped.
    Personal data is zeroed/defaulted, *status* is "Complete", and the
    model’s before_insert listener supplies request_id.

    Both request_date and date_filed will be set to the parsed date.
    """
    # Optional purge of previous backfills
    if purge:
        deleted = db.session.query(PickupRequest) \
            .filter(PickupRequest.admin_notes == 'Imported via import-backfill CLI') \
            .delete(synchronize_session=False)
        db.session.commit()
        click.echo(f"✔ Deleted {deleted} previous imported rows.")

    # Load file sample for delimiter sniff
    with open(path, "r", encoding="utf-8", newline="") as fh:
        sample = fh.read(1024)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
            delim = dialect.delimiter
        except csv.Error:
            delim = '\t' if '\t' in sample else ','
        fh.seek(0)
        reader = csv.DictReader(fh, delimiter=delim)
        rows = list(reader)                 # pull every row into memory
        rows_added = 0

        for row in reversed(rows): 
            raw_date = (row.get('Last Pick-Up / Drop-Off') or '').strip()
            if not raw_date or raw_date.lower() == 'inquiry':
                continue
            # parse MM/DD/YY to YYYY-MM-DD
            try:
                parsed_date = datetime.strptime(raw_date, "%m/%d/%y").date().isoformat()
            except ValueError:
                continue
            # merge address lines
            address = f"{(row.get('Address 1') or '').strip()} {(row.get('Address 2') or '').strip()}".strip()

            pickup = PickupRequest(
                fname=None,
                lname=None,
                email="",
                phone_number=None,

                address=(row.get('Address 1') or '').strip(),
                address2=(row.get('Address 2') or '').strip(),
                city=(row.get('City') or '').strip(),
                zipcode=(row.get('Zip') or '').strip(),

                status="Complete",
                awareness=(row.get('Awareness') or 'Unknown').strip(),
                request_date=parsed_date,

                date_filed=parsed_date,
                admin_notes='Imported via import-backfill CLI',
            )
            db.session.add(pickup)
            rows_added += 1

        db.session.commit()
        click.echo(
            f"✔ Imported {rows_added} rows from '{path}' (delimiter '{delim}')."
        )


def register(app):
    """Attach the CLI command to *app*. Call this from create_app()."""
    app.cli.add_command(import_backfill)
