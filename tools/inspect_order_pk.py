"""One-off diagnostic — checks tblOrder's real primary key and the type of
OrderID/PageNumber against production, since tenant.py's schema was
reconstructed from how the Ruby code used columns, not from introspection.
Run from the project root: python tools/inspect_order_pk.py --tenant <name>
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
    print("Primary key:", inspector.get_pk_constraint("tblOrder"))
    for col in inspector.get_columns("tblOrder"):
        if col["name"] in ("OrderID", "PageNumber"):
            print(col)
