"""One-off diagnostic — tblPublicationFormatSize's primary key was a guessed
assumption in tenant.py (matched to its sibling table's iID convention,
noted as unverified at the time). Confirmed wrong against production:
'Invalid column name iID'. Checking the real columns here.
Run: python -m tools.inspect_format_size --tenant <name>
"""
import argparse
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from insert_builder.config.settings import settings
from insert_builder.database.provision import get_engine, get_single_tenant
from insert_builder.database.tenant import get_tenant_engine

parser = argparse.ArgumentParser()
parser.add_argument("--tenant", required=True)
args = parser.parse_args()

with Session(get_engine(settings)) as provision_session:
    tenant = get_single_tenant(provision_session, args.tenant)
    tenant_engine = get_tenant_engine(tenant)
    inspector = inspect(tenant_engine)
    print("Primary key:", inspector.get_pk_constraint("tblPublicationFormatSize"))
    for col in inspector.get_columns("tblPublicationFormatSize"):
        print(col)
