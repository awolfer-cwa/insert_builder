from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, Session, relationship

Base = declarative_base()

# NOTE: these models only declare the columns this tool actually touches,
# reconstructed from the Ruby gem's ActiveRecord relations and query code —
# not from introspecting the real SQL Server schema (not reachable from this
# box). The real tables almost certainly have more columns. Treat column
# *types* on tblAdvertismentSizeDimension / tblPublicationFormatSize as an
# assumption to verify: mirrored as String here (needing float() at the point
# of use) because that's the pattern production-templatebuilder's own models
# already verified for the near-identical tblAdvertismentSizeDimension table —
# not independently confirmed for every column below.


class TblCarmaSystem(Base):
    __tablename__ = "tblCARMASystem"
    vKey = Column(String, primary_key=True)
    StringValue = Column(String)


class TblPrelimOrderStatusType(Base):
    __tablename__ = "tblPrelimOrderStatusType"
    iId = Column(Integer, primary_key=True)
    Approved = Column(Boolean)
    Cancelled = Column(Boolean)
    InCancellationCycle = Column(Boolean)


class TblPrelimOrderStatus(Base):
    __tablename__ = "tblPrelimOrderStatus"
    iId = Column(Integer, primary_key=True)
    StatusTypeId = Column(Integer, ForeignKey("tblPrelimOrderStatusType.iId"))

    status_type = relationship("TblPrelimOrderStatusType")


class TblPrelimOrder(Base):
    __tablename__ = "tblPrelimOrder"
    OrderId = Column(Integer, ForeignKey("tblOrder.OrderID"), primary_key=True)
    CurrentStatusId = Column(Integer, ForeignKey("tblPrelimOrderStatus.iId"))

    status = relationship("TblPrelimOrderStatus")


class TblAdvertisementSizeDimension(Base):
    # Table name keeps the original schema's typo ("Advertisment") —
    # this must match the real table name exactly, not a corrected spelling.
    __tablename__ = "tblAdvertismentSizeDimension"
    IDAdvertisemntSizeDimension = Column(Integer, primary_key=True)
    Height = Column(String)
    Width = Column(String)
    Units = Column(String)
    StartingPageXPos = Column(String)
    StartingPageYPos = Column(String)
    InsertSpacingX = Column(String)
    InsertSpacingY = Column(String)


class TblAdvertisementSize(Base):
    __tablename__ = "tblAdvertisementSize"
    AdvertisementSizeID = Column(Integer, primary_key=True)
    SizeName = Column(String)
    Units = Column(String)
    AdvertisementSizeDimensionID = Column(
        Integer, ForeignKey("tblAdvertismentSizeDimension.IDAdvertisemntSizeDimension")
    )

    dimension = relationship("TblAdvertisementSizeDimension")


class TblRegion(Base):
    __tablename__ = "tblRegion"
    RegionID = Column(Integer, primary_key=True)
    Name = Column(String)


class TblOrderRegion(Base):
    __tablename__ = "tblOrderRegion"
    OrderID = Column(Integer, ForeignKey("tblOrder.OrderID"), primary_key=True)
    RegionID = Column(Integer, ForeignKey("tblRegion.RegionID"))

    region = relationship("TblRegion")


class TblPublicationFormatSize(Base):
    __tablename__ = "tblPublicationFormatSize"
    # Primary key name is unverified against the real schema — assumed
    # Confirmed against production via tools/inspect_format_size.py
    # (2026-11-20) — was wrongly guessed as "iID" to match the sibling
    # table's convention. PrintWidth/PrintHeight are real INTEGER columns
    # here, unlike tblAdvertismentSizeDimension's text-stored equivalents.
    PublicationFormatSizeID = Column(Integer, primary_key=True)
    PublicationFormatID = Column(Integer, ForeignKey("tblPublicationFormat.iID"))
    PrintWidth = Column(Integer)
    PrintHeight = Column(Integer)


class TblPublicationFormat(Base):
    __tablename__ = "tblPublicationFormat"
    iID = Column(Integer, primary_key=True)
    StoreByAdSize = Column(Boolean)

    format_size = relationship("TblPublicationFormatSize", uselist=False)


class TblPublication(Base):
    __tablename__ = "tblPublication"
    PublicationID = Column(Integer, primary_key=True)
    Name = Column(String)
    PublicationFormatID = Column(Integer, ForeignKey("tblPublicationFormat.iID"))

    publication_format = relationship("TblPublicationFormat")

    @property
    def publication_format_size(self):
        return self.publication_format.format_size if self.publication_format else None


class TblEdition(Base):
    __tablename__ = "tblEdition"
    EditionID = Column(Integer, primary_key=True)
    PublicationID = Column(Integer, ForeignKey("tblPublication.PublicationID"))
    Name = Column(String)

    publication = relationship("TblPublication")


class TblOrder(Base):
    __tablename__ = "tblOrder"
    OrderID = Column(Integer, primary_key=True)
    EditionID = Column(Integer, ForeignKey("tblEdition.EditionID"))
    AdvertisementSizeID = Column(Integer, ForeignKey("tblAdvertisementSize.AdvertisementSizeID"))
    UserInvoiceNumber = Column(String)
    PageNumber = Column(String, nullable=True)

    edition = relationship("TblEdition")
    ad_size = relationship("TblAdvertisementSize")
    prelim_order = relationship("TblPrelimOrder", uselist=False)
    order_region = relationship("TblOrderRegion", uselist=False)

    @property
    def publication(self):
        return self.edition.publication if self.edition else None

    @property
    def region(self):
        return self.order_region.region if self.order_region else None

    @property
    def advertisement_size_dimension(self):
        return self.ad_size.dimension if self.ad_size else None

    @property
    def prelim_order_status_type(self):
        if not self.prelim_order or not self.prelim_order.status:
            return None
        return self.prelim_order.status.status_type


class TblDistribution(Base):
    __tablename__ = "tblDistribution"
    DistributionID = Column(Integer, primary_key=True)
    EditionID = Column(Integer, ForeignKey("tblEdition.EditionID"))
    Name = Column(String)
    ReadyToRun = Column(Boolean, default=False)
    InDesignCreateDate = Column(DateTime, nullable=True)
    # No DistributionName column — confirmed against the real schema
    # (inspect_schema.py, 2026-11-19). The Ruby original's
    # journal_builder.rb#retrieve_template referenced one anyway (a third
    # bug in that file, same copy-paste-from-handbook pattern as the other
    # two — almost certainly meant to mirror tblSubDistribution's real
    # SubDistributionName column). Fixed here to use Name instead of
    # carrying the bug forward.

    edition = relationship("TblEdition")

    @property
    def publication(self):
        return self.edition.publication if self.edition else None


class TblRegionalDistribution(Base):
    __tablename__ = "tblRegionalDistribution"
    # Composite usage in the Ruby model has no single declared PK column;
    # DistributionID is used here as the SQLAlchemy primary key for mapping
    # purposes only — verify against the real schema before relying on
    # uniqueness.
    DistributionID = Column(Integer, ForeignKey("tblDistribution.DistributionID"), primary_key=True)
    RegionID = Column(Integer, ForeignKey("tblRegion.RegionID"))


class TblSubdistributionOrder(Base):
    __tablename__ = "tblSubDistributionOrder"
    iSubDistributionOrderID = Column(Integer, primary_key=True)
    SubDistributionID = Column(Integer, ForeignKey("tblSubDistribution.iSubDistributionID"))
    OrderID = Column(Integer, ForeignKey("tblOrder.OrderID"), nullable=True)
    AdvertisementSizeID = Column(Integer, ForeignKey("tblAdvertisementSize.AdvertisementSizeID"), nullable=True)
    # 0 = real order, 1 = dummy order (placed via its own jpg), 2 = filler (no order at all)
    isDummy = Column(Integer, default=0)
    FileData = Column(String, nullable=True)
    guid = Column(String, nullable=True)

    order = relationship("TblOrder")
    advertisement_size = relationship("TblAdvertisementSize")


class TblSubdistribution(Base):
    __tablename__ = "tblSubDistribution"
    iSubDistributionID = Column(Integer, primary_key=True)
    EditionID = Column(Integer, ForeignKey("tblEdition.EditionID"))
    RegionID = Column(Integer, ForeignKey("tblRegion.RegionID"), nullable=True)
    SubDistributionName = Column(String)
    TemplateAdSize = Column(String, nullable=True)
    ReadyToRun = Column(Boolean, default=False)
    InDesignCreateDate = Column(DateTime, nullable=True)

    edition = relationship("TblEdition")
    region = relationship("TblRegion")

    @property
    def publication(self):
        return self.edition.publication if self.edition else None


def get_tenant_engine(tenant):
    """Creates a SQL Server connection engine for the given tenant."""
    url = (
        f"mssql+pyodbc://{tenant.username}:{tenant.password}@{tenant.host}:{tenant.port}/{tenant.name}"
        f"?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    )
    return create_engine(url)


def get_outstanding_distributions(session: Session, manual_distribution=None) -> list:
    query = session.query(TblDistribution)
    if manual_distribution:
        return query.filter_by(DistributionID=manual_distribution).all()
    return query.filter_by(ReadyToRun=True).all()


def get_outstanding_subdistributions(session: Session, manual_subdistribution=None) -> list:
    query = session.query(TblSubdistribution)
    if manual_subdistribution:
        return query.filter_by(iSubDistributionID=manual_subdistribution).all()
    return query.filter_by(ReadyToRun=True).all()


def get_system_flag(session: Session, key: str) -> bool:
    """Mirrors CarmaInstance#file_ads_by_region?/file_ads_by_format? — reads
    a tblCARMASystem flag and treats the string 'true' as the only true value,
    matching the Ruby original's exact string comparison."""
    row = session.query(TblCarmaSystem).filter_by(vKey=key).first()
    return bool(row and row.StringValue == "true")
