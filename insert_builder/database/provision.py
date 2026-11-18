import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, Column, String, Integer, Boolean
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()


class CarmaTenant(Base):
    # Maps to the carma_databases table in the shared carma_provision registry
    __tablename__ = "carma_databases"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    host = Column(String)
    port = Column(Integer)
    username = Column(String)
    # Password is stored encrypted — decrypted at runtime by the password property below.
    encrypted_password = Column(String)
    encrypted_password_iv = Column(String)
    entity_encryption_key = Column(String)
    # Only tenants with this set to True get processed. The column name is
    # specific to this tool — template_builder uses a different flag on the
    # same table.
    insert_builder_enabled = Column(Boolean, default=False)

    @property
    def password(self) -> str:
        """Decrypts the tenant's SQL Server password using AES-256-GCM."""
        encryption_key = os.environ.get("PUBLISHER_ENCRYPTION_KEY", "")
        if not encryption_key or not self.encrypted_password or not self.encrypted_password_iv:
            return ""
        try:
            key = base64.b64decode(encryption_key)
            iv = base64.b64decode(self.encrypted_password_iv)
            encrypted = base64.b64decode(self.encrypted_password)
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(iv, encrypted, None).decode("utf-8")
        except Exception:
            return ""


def get_engine(settings):
    """Builds a SQLAlchemy engine to connect to the carma_provision MySQL database."""
    url = (
        f"mysql+pymysql://{settings.database_username}:{settings.database_password}"
        f"@{settings.database_host}:{settings.database_port}/{settings.database_name}"
    )
    return create_engine(url)


def get_active_tenants(session: Session) -> list:
    """Returns all tenants with insert_builder_enabled set to True."""
    return session.query(CarmaTenant).filter_by(insert_builder_enabled=True).all()


def get_single_tenant(session: Session, database_name: str) -> CarmaTenant:
    """Returns one specific tenant by name."""
    return session.query(CarmaTenant).filter_by(name=database_name).first()
