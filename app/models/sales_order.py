from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SalesOrder(Base):
    __tablename__ = "sales_order"
    __table_args__ = (
        Index("ix_sales_order_order_date", "order_date"),
        Index("ix_sales_order_region_date", "region_id", "order_date"),
        Index("ix_sales_order_rep_date", "sales_rep_id", "order_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    region_id: Mapped[int] = mapped_column(ForeignKey("sales_region.id"), nullable=False)
    sales_rep_id: Mapped[int] = mapped_column(ForeignKey("sales_rep.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    region: Mapped["SalesRegion"] = relationship(back_populates="orders")
    sales_rep: Mapped["SalesRep"] = relationship(back_populates="orders")
    product: Mapped["Product"] = relationship(back_populates="orders")
