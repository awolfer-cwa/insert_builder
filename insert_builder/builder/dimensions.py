def dimension_fields(dimension) -> dict:
    """Converts the dimension columns (stored as text in the DB) to floats
    for the job JSON — see the assumption noted in database/tenant.py.
    Shared between prepare_orders.py and filler_catalog.py."""
    if dimension is None:
        return {"width": 0.0, "height": 0.0, "starting_page_x_pos": 0.0,
                "starting_page_y_pos": 0.0, "insert_spacing_x": 0.0, "insert_spacing_y": 0.0}
    return {
        "width": float(dimension.Width),
        "height": float(dimension.Height),
        "starting_page_x_pos": float(dimension.StartingPageXPos),
        "starting_page_y_pos": float(dimension.StartingPageYPos),
        "insert_spacing_x": float(dimension.InsertSpacingX),
        "insert_spacing_y": float(dimension.InsertSpacingY),
    }
