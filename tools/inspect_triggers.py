"""One-off diagnostic — lists triggers on tblOrder. SQL Server triggers can
make the reported UPDATE rowcount unreliable, which is a likely explanation
for the StaleDataError hit when clearing PageNumber (0 rows reported
'updated' despite the row existing and matching on its real primary key).
Run: python -m tools.inspect_triggers --tenant <name>
"""
import argparse
from sqlalchemy import text
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
    with Session(tenant_engine) as session:
        rows = session.execute(text("""
            SELECT t.name AS trigger_name, t.is_disabled
            FROM sys.triggers t
            WHERE t.parent_id = OBJECT_ID('tblOrder')
        """)).all()
        if not rows:
            print("No triggers found on tblOrder.")
        for row in rows:
            print(row)
