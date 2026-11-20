from sqlalchemy import update
from sqlalchemy.orm import Session
from insert_builder.database.tenant import TblOrder


def apply_page_numbers(session: Session, orders: list[dict], result: dict) -> None:
    """Direct port of UpdatePageNumberTask — only real orders (is_dummy == 0)
    get their PageNumber written back, matching the Ruby original's guard.
    Correlates by array index rather than invoice_number since filler orders
    (is_dummy == 2) have no invoice_number at all and would collide on None.

    Uses an explicit UPDATE rather than order.PageNumber = <value> — tblOrder
    has several active triggers (tools/inspect_triggers.py confirmed this
    against production) that make the ORM's post-flush rowcount check
    unreliable and raise a false StaleDataError even when the row updates
    correctly."""
    placed = {p["index"]: p["page_name"] for p in result.get("placed_orders", [])}
    for i, order_dict in enumerate(orders):
        if order_dict["is_dummy"] != 0:
            continue
        page_name = placed.get(i)
        if page_name is None:
            continue
        session.execute(update(TblOrder).where(TblOrder.OrderID == order_dict["order_id"]).values(PageNumber=page_name))
