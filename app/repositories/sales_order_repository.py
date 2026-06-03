from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sales_order import SalesOrder
from app.repositories.base_repository import BaseRepository


class SalesOrderRepository(BaseRepository[SalesOrder]):
    def __init__(self) -> None:
        super().__init__(SalesOrder)

    async def find_by_rep_id_and_order_date_between(
        self,
        session: AsyncSession,
        rep_id: int,
        start: date,
        end: date,
    ) -> list[SalesOrder]:
        return await self._find_by_date_range(session, SalesOrder.rep_id == rep_id, start, end)

    async def find_by_region_id_and_order_date_between(
        self,
        session: AsyncSession,
        region_id: int,
        start: date,
        end: date,
    ) -> list[SalesOrder]:
        return await self._find_by_date_range(session, SalesOrder.region_id == region_id, start, end)

    async def find_by_product_id_and_order_date_between(
        self,
        session: AsyncSession,
        product_id: int,
        start: date,
        end: date,
    ) -> list[SalesOrder]:
        return await self._find_by_date_range(session, SalesOrder.product_id == product_id, start, end)

    async def sum_amount_by_region(
        self,
        session: AsyncSession,
        region_id: int,
        start: date,
        end: date,
    ) -> Decimal:
        return await self._sum_completed_amount(session, SalesOrder.region_id == region_id, start, end)

    async def sum_amount_by_rep(
        self,
        session: AsyncSession,
        rep_id: int,
        start: date,
        end: date,
    ) -> Decimal:
        return await self._sum_completed_amount(session, SalesOrder.rep_id == rep_id, start, end)

    async def find_rep_ranking(self, session: AsyncSession, start: date, end: date) -> list[tuple[int, Decimal]]:
        result = await session.execute(
            select(SalesOrder.rep_id, func.sum(SalesOrder.amount).label("total"))
            .where(SalesOrder.status == "COMPLETED")
            .where(SalesOrder.order_date.between(start, end))
            .group_by(SalesOrder.rep_id)
            .order_by(func.sum(SalesOrder.amount).desc())
        )
        return [(rep_id, total) for rep_id, total in result.all()]

    async def find_region_ranking(self, session: AsyncSession, start: date, end: date) -> list[tuple[int, Decimal]]:
        result = await session.execute(
            select(SalesOrder.region_id, func.sum(SalesOrder.amount).label("total"))
            .where(SalesOrder.status == "COMPLETED")
            .where(SalesOrder.order_date.between(start, end))
            .group_by(SalesOrder.region_id)
            .order_by(func.sum(SalesOrder.amount).desc())
        )
        return [(region_id, total) for region_id, total in result.all()]

    async def find_product_ranking(
        self,
        session: AsyncSession,
        start: date,
        end: date,
    ) -> list[tuple[int, Decimal, int]]:
        result = await session.execute(
            select(
                SalesOrder.product_id,
                func.sum(SalesOrder.amount).label("total"),
                func.sum(SalesOrder.quantity).label("quantity"),
            )
            .where(SalesOrder.status == "COMPLETED")
            .where(SalesOrder.order_date.between(start, end))
            .group_by(SalesOrder.product_id)
            .order_by(func.sum(SalesOrder.amount).desc())
        )
        return [(product_id, total, int(quantity)) for product_id, total, quantity in result.all()]

    async def find_monthly_trend(
        self,
        session: AsyncSession,
        region_id: int | None,
        start: date,
        end: date,
    ) -> list[tuple[str, Decimal, int]]:
        month_expr = self._month_expression(session).label("month")
        statement = (
            select(month_expr, func.sum(SalesOrder.amount), func.count())
            .where(SalesOrder.status == "COMPLETED")
            .where(SalesOrder.order_date.between(start, end))
        )
        if region_id is not None:
            statement = statement.where(SalesOrder.region_id == region_id)
        statement = statement.group_by(month_expr).order_by(month_expr)

        result = await session.execute(statement)
        return [(month, total, int(order_count)) for month, total, order_count in result.all()]

    async def find_last_order_date_by_product(self, session: AsyncSession, product_id: int) -> date | None:
        result = await session.execute(
            select(func.max(SalesOrder.order_date))
            .where(SalesOrder.product_id == product_id)
            .where(SalesOrder.status == "COMPLETED")
        )
        return result.scalar_one_or_none()

    async def find_refund_rate_by_rep(self, session: AsyncSession, start: date, end: date) -> list[tuple[int, int, int]]:
        refunded_count = func.sum(case((SalesOrder.status == "REFUNDED", 1), else_=0))
        result = await session.execute(
            select(SalesOrder.rep_id, refunded_count, func.count())
            .where(SalesOrder.order_date.between(start, end))
            .group_by(SalesOrder.rep_id)
            .order_by(SalesOrder.rep_id)
        )
        return [(rep_id, int(refunded), int(total)) for rep_id, refunded, total in result.all()]

    async def count_completed_by_region(
        self,
        session: AsyncSession,
        region_id: int,
        start: date,
        end: date,
    ) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(SalesOrder)
            .where(SalesOrder.region_id == region_id)
            .where(SalesOrder.status == "COMPLETED")
            .where(SalesOrder.order_date.between(start, end))
        )
        return int(result.scalar_one())

    async def _find_by_date_range(self, session: AsyncSession, predicate, start: date, end: date) -> list[SalesOrder]:
        result = await session.execute(
            select(SalesOrder).where(predicate).where(SalesOrder.order_date.between(start, end)).order_by(SalesOrder.id)
        )
        return list(result.scalars().all())

    async def _sum_completed_amount(self, session: AsyncSession, predicate, start: date, end: date) -> Decimal:
        result = await session.execute(
            select(func.coalesce(func.sum(SalesOrder.amount), 0))
            .where(predicate)
            .where(SalesOrder.status == "COMPLETED")
            .where(SalesOrder.order_date.between(start, end))
        )
        return result.scalar_one()

    def _month_expression(self, session: AsyncSession):
        dialect_name = session.get_bind().dialect.name
        if dialect_name == "mysql":
            return func.date_format(SalesOrder.order_date, "%Y-%m")
        return func.strftime("%Y-%m", SalesOrder.order_date)
