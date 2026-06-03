from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep
from app.repositories.product_repository import ProductRepository
from app.repositories.sales_order_repository import SalesOrderRepository
from app.repositories.sales_region_repository import SalesRegionRepository
from app.repositories.sales_rep_repository import SalesRepRepository
from app.schemas.sales import (
    MonthlyTrendDTO,
    OrderSummaryDTO,
    ProductSalesDTO,
    RegionSalesDTO,
    RepSalesDTO,
)


class SalesQueryService:
    def __init__(
        self,
        order_repository: SalesOrderRepository | None = None,
        rep_repository: SalesRepRepository | None = None,
        product_repository: ProductRepository | None = None,
        region_repository: SalesRegionRepository | None = None,
    ) -> None:
        self.order_repository = order_repository or SalesOrderRepository()
        self.rep_repository = rep_repository or SalesRepRepository()
        self.product_repository = product_repository or ProductRepository()
        self.region_repository = region_repository or SalesRegionRepository()

    async def query_orders(
        self,
        session: AsyncSession,
        *,
        rep_id: int | None,
        region_id: int | None,
        start: date,
        end: date,
        product_id: int | None = None,
    ) -> list[OrderSummaryDTO]:
        if rep_id is not None:
            orders = await self.order_repository.find_by_rep_id_and_order_date_between(session, rep_id, start, end)
        elif region_id is not None:
            orders = await self.order_repository.find_by_region_id_and_order_date_between(session, region_id, start, end)
        elif product_id is not None:
            orders = await self.order_repository.find_by_product_id_and_order_date_between(
                session,
                product_id,
                start,
                end,
            )
        else:
            orders = [
                order
                for order in await self.order_repository.find_all(session)
                if start <= order.order_date <= end
            ]

        rep_map = await self._rep_map(session)
        return [self._to_order_summary(order, rep_map) for order in orders]

    async def query_total_amount(
        self,
        session: AsyncSession,
        region_id: int | None,
        start: date,
        end: date,
    ) -> Decimal:
        if region_id is not None:
            return await self.order_repository.sum_amount_by_region(session, region_id, start, end)

        total = Decimal("0")
        for order in await self.order_repository.find_all(session):
            if order.status == "COMPLETED" and start <= order.order_date <= end:
                total += order.amount
        return total

    async def query_rep_ranking(
        self,
        session: AsyncSession,
        start: date,
        end: date,
        top_n: int,
    ) -> list[RepSalesDTO]:
        rep_map = await self._rep_map(session)
        region_map = await self._region_map(session)
        result: list[RepSalesDTO] = []

        for rep_id, total in await self.order_repository.find_rep_ranking(session, start, end):
            rep = rep_map.get(rep_id)
            if rep is None:
                continue
            region = region_map.get(rep.region_id)
            result.append(
                RepSalesDTO(
                    rep_id=rep.id,
                    rep_name=rep.name,
                    region_id=rep.region_id,
                    region_name=region.name if region else "Unknown region",
                    total_amount=total,
                    order_count=0,
                )
            )
            if len(result) >= top_n:
                break

        return result

    async def query_region_ranking(
        self,
        session: AsyncSession,
        start: date,
        end: date,
    ) -> list[RegionSalesDTO]:
        region_map = await self._region_map(session)
        result: list[RegionSalesDTO] = []

        for region_id, total in await self.order_repository.find_region_ranking(session, start, end):
            region = region_map.get(region_id)
            result.append(
                RegionSalesDTO(
                    region_id=region_id,
                    region_name=region.name if region else "Unknown region",
                    total_amount=total,
                    order_count=0,
                    total_profit=Decimal("0"),
                )
            )

        return result

    async def query_product_ranking(
        self,
        session: AsyncSession,
        start: date,
        end: date,
        top_n: int,
    ) -> list[ProductSalesDTO]:
        product_map = await self._product_map(session)
        result: list[ProductSalesDTO] = []

        for product_id, total, quantity in await self.order_repository.find_product_ranking(session, start, end):
            product = product_map.get(product_id)
            if product is None:
                continue
            result.append(
                ProductSalesDTO(
                    product_id=product.id,
                    sku_code=product.sku_code,
                    product_name=product.name,
                    category=product.category,
                    total_amount=total,
                    total_quantity=quantity,
                )
            )
            if len(result) >= top_n:
                break

        return result

    async def query_monthly_trend(
        self,
        session: AsyncSession,
        region_id: int | None,
        months: int,
        today: date | None = None,
    ) -> list[MonthlyTrendDTO]:
        end = today or date.today()
        start = self._minus_months(end, months).replace(day=1)
        raw = await self.order_repository.find_monthly_trend(session, region_id, start, end)
        return [MonthlyTrendDTO(month=month, total_amount=total, order_count=count) for month, total, count in raw]

    def calc_growth_rate(self, current: Decimal, previous: Decimal | None) -> Decimal | None:
        if previous is None or previous == 0:
            return None
        rate = (current - previous) / previous * Decimal("100")
        return rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def query_last_order_date(self, session: AsyncSession, product_id: int) -> date | None:
        return await self.order_repository.find_last_order_date_by_product(session, product_id)

    async def query_order_count(self, session: AsyncSession, region_id: int, start: date, end: date) -> int:
        return await self.order_repository.count_completed_by_region(session, region_id, start, end)

    async def query_refund_rates(self, session: AsyncSession, start: date, end: date) -> list[tuple[int, int, int]]:
        return await self.order_repository.find_refund_rate_by_rep(session, start, end)

    async def get_rep_name(self, session: AsyncSession, rep_id: int) -> str:
        rep = await self.rep_repository.find_by_id(session, rep_id)
        return rep.name if rep else "Unknown sales rep"

    async def get_region_name(self, session: AsyncSession, region_id: int) -> str:
        region = await self.region_repository.find_by_id(session, region_id)
        return region.name if region else "Unknown region"

    async def get_region_id_by_name(self, session: AsyncSession, region_name: str) -> int | None:
        region = await self.region_repository.find_by_name(session, region_name)
        return region.id if region else None

    async def get_rep_id_by_name(self, session: AsyncSession, rep_name: str) -> int | None:
        rep = await self.rep_repository.find_by_name(session, rep_name)
        return rep.id if rep else None

    async def _rep_map(self, session: AsyncSession) -> dict[int, SalesRep]:
        return {rep.id: rep for rep in await self.rep_repository.find_all(session)}

    async def _region_map(self, session: AsyncSession) -> dict[int, SalesRegion]:
        return {region.id: region for region in await self.region_repository.find_all(session)}

    async def _product_map(self, session: AsyncSession) -> dict[int, Product]:
        return {product.id: product for product in await self.product_repository.find_all(session)}

    def _to_order_summary(self, order: SalesOrder, rep_map: dict[int, SalesRep]) -> OrderSummaryDTO:
        rep = rep_map.get(order.rep_id)
        return OrderSummaryDTO(
            order_no=order.order_no,
            rep_name=rep.name if rep else "Unknown sales rep",
            customer_name=order.customer_name,
            amount=order.amount,
            status=order.status,
            order_date=order.order_date,
        )

    def _minus_months(self, value: date, months: int) -> date:
        month_index = value.year * 12 + value.month - 1 - months
        year = month_index // 12
        month = month_index % 12 + 1
        return value.replace(year=year, month=month, day=min(value.day, 28))
