from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SalesRegion(Base):
    __tablename__ = "sales_region"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    sales_reps: Mapped[list["SalesRep"]] = relationship(back_populates="region")
    orders: Mapped[list["SalesOrder"]] = relationship(back_populates="region")
