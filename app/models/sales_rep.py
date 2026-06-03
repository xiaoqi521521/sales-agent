from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SalesRep(Base):
    __tablename__ = "sales_rep"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("sales_region.id"), nullable=False)

    region: Mapped["SalesRegion"] = relationship(back_populates="sales_reps")
    orders: Mapped[list["SalesOrder"]] = relationship(back_populates="sales_rep")
