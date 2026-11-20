"""One-off diagnostic — shows exactly which folder/filename the code
searches for a given order's artwork .indd, to compare against what's
actually present in the test Dropbox folder.
Run: python -m tools.inspect_order_artwork --tenant <name> --invoice <number>
"""
import argparse
from sqlalchemy.orm import Session
from insert_builder.config.settings import settings
from insert_builder.database.provision import get_engine, get_single_tenant
from insert_builder.database.tenant import get_tenant_engine, TblOrder, get_system_flag
from insert_builder.builder.prepare_orders import _order_directory

parser = argparse.ArgumentParser()
parser.add_argument("--tenant", required=True)
parser.add_argument("--invoice", required=True)
args = parser.parse_args()

with Session(get_engine(settings)) as provision_session:
    tenant = get_single_tenant(provision_session, args.tenant)
    tenant_engine = get_tenant_engine(tenant)
    with Session(tenant_engine) as session:
        order = session.query(TblOrder).filter_by(UserInvoiceNumber=args.invoice).first()
        if order is None:
            print(f"No order found with UserInvoiceNumber={args.invoice}")
        else:
            file_ads_by_region = get_system_flag(session, "FileAdsByRegion")
            file_ads_by_format = get_system_flag(session, "FileAdsByFormat")
            directory = _order_directory(order, file_ads_by_region, file_ads_by_format)
            print("file_ads_by_region:", file_ads_by_region)
            print("file_ads_by_format:", file_ads_by_format)
            print("Expected directory:", directory)
            print("Expected filename pattern:", f"{order.UserInvoiceNumber}.*.indd")
