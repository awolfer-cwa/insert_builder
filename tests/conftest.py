import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from insert_builder.database import provision, tenant


@pytest.fixture
def provision_session():
    engine = create_engine("sqlite:///:memory:")
    provision.Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def tenant_session():
    engine = create_engine("sqlite:///:memory:")
    tenant.Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
