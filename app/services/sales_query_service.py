from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_context import CurrentUser
from app.core.user_context import get_current_user
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

    @property
    def current_user(self) -> CurrentUser | None:
        return get_current_user()

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
        rep_id, region_id = await self._order_scope(session, rep_id=rep_id, region_id=region_id)
        if self._is_invalid_scope(rep_id, region_id):
            return []

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
        if self.current_user and self.current_user.is_sales_rep:
            return await self.order_repository.sum_amount_by_rep(session, self.current_user.rep_id, start, end)
        region_id = self._region_scope(region_id)
        if region_id == -1:
            return Decimal("0")
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

        rows = await self._scoped_rep_ranking(session, start, end)
        for rep_id, total in rows:
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

        rows = await self._scoped_region_ranking(session, start, end)
        for region_id, total in rows:
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

        rows = await self._scoped_product_ranking(session, start, end)
        for product_id, total, quantity in rows:
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
        if self.current_user and self.current_user.is_sales_rep:
            raw = await self.order_repository.find_monthly_trend_by_rep(session, self.current_user.rep_id, start, end)
        else:
            scoped_region_id = self._region_scope(region_id)
            if scoped_region_id == -1:
                return []
            raw = await self.order_repository.find_monthly_trend(session, scoped_region_id, start, end)
        return [MonthlyTrendDTO(month=month, total_amount=total, order_count=count) for month, total, count in raw]

    def calc_growth_rate(self, current: Decimal, previous: Decimal | None) -> Decimal | None:
        if previous is None or previous == 0:
            return None
        rate = (current - previous) / previous * Decimal("100")
        return rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def query_last_order_date(self, session: AsyncSession, product_id: int) -> date | None:
        if self.current_user and self.current_user.is_sales_rep:
            return await self.order_repository.find_last_order_date_by_product_and_rep(
                session,
                product_id,
                self.current_user.rep_id,
            )
        if self.current_user and self.current_user.is_sales_manager:
            if self.current_user.region_id is None:
                return None
            return await self.order_repository.find_last_order_date_by_product_and_region(
                session,
                product_id,
                self.current_user.region_id,
            )
        return await self.order_repository.find_last_order_date_by_product(session, product_id)

    async def query_order_count(self, session: AsyncSession, region_id: int, start: date, end: date) -> int:
        if self.current_user and self.current_user.is_sales_rep:
            return await self.order_repository.count_completed_by_rep(session, self.current_user.rep_id, start, end)
        region_id = self._region_scope(region_id)
        if region_id == -1 or region_id is None:
            return 0
        return await self.order_repository.count_completed_by_region(session, region_id, start, end)

    async def query_refund_rates(self, session: AsyncSession, start: date, end: date) -> list[tuple[int, int, int]]:
        if self.current_user and self.current_user.is_sales_rep:
            rows = await self.order_repository.find_refund_rate_by_rep(session, start, end)
            return [row for row in rows if row[0] == self.current_user.rep_id]
        if self.current_user and self.current_user.is_sales_manager:
            if self.current_user.region_id is None:
                return []
            return await self.order_repository.find_refund_rate_by_region(session, self.current_user.region_id, start, end)
        return await self.order_repository.find_refund_rate_by_rep(session, start, end)

    async def get_rep_name(self, session: AsyncSession, rep_id: int) -> str:
        rep = await self.rep_repository.find_by_id(session, rep_id)
        return rep.name if rep else "Unknown sales rep"

    async def get_region_name(self, session: AsyncSession, region_id: int) -> str:
        region = await self.region_repository.find_by_id(session, region_id)
        return region.name if region else "Unknown region"

    async def get_region_id_by_name(self, session: AsyncSession, region_name: str) -> int | None:
        region = await self.region_repository.find_by_name(session, region_name)
        if region is None:
            return None
        scoped_region_id = self._region_scope(region.id)
        return None if scoped_region_id == -1 else region.id

    async def get_rep_id_by_name(self, session: AsyncSession, rep_name: str) -> int | None:
        rep = await self.rep_repository.find_by_name(session, rep_name)
        if rep is None:
            return None
        scoped_rep_id, scoped_region_id = await self._order_scope(session, rep_id=rep.id, region_id=None)
        if self._is_invalid_scope(scoped_rep_id, scoped_region_id):
            return None
        return rep.id

    async def visible_regions(self, session: AsyncSession) -> list[SalesRegion]:
        if self.current_user is None or self.current_user.is_sales_director:
            return await self.region_repository.find_all(session)
        if self.current_user.is_sales_rep or self.current_user.region_id is None:
            return []
        region = await self.region_repository.find_by_id(session, self.current_user.region_id)
        return [region] if region else []

    async def visible_sales_reps(self, session: AsyncSession) -> list[SalesRep]:
        if self.current_user is None or self.current_user.is_sales_director:
            return await self.rep_repository.find_by_role(session, "SALES_REP")
        if self.current_user.is_sales_rep:
            rep = await self.rep_repository.find_by_id(session, self.current_user.rep_id)
            return [rep] if rep else []
        if self.current_user.region_id is None:
            return []
        reps = await self.rep_repository.find_by_region_id(session, self.current_user.region_id)
        return [rep for rep in reps if rep.role == "SALES_REP"]

    async def _order_scope(
        self,
        session: AsyncSession,
        *,
        rep_id: int | None,
        region_id: int | None,
    ) -> tuple[int | None, int | None]:
        if self.current_user is None or self.current_user.is_sales_director:
            return rep_id, region_id
        if self.current_user.is_sales_rep:
            if rep_id is not None and rep_id != self.current_user.rep_id:
                return -1, -1
            if region_id is not None and region_id != self.current_user.region_id:
                return -1, -1
            return self.current_user.rep_id, self.current_user.region_id
        if self.current_user.region_id is None:
            return -1, -1
        if region_id is not None and region_id != self.current_user.region_id:
            return -1, -1
        if rep_id is not None:
            rep = await self.rep_repository.find_by_id(session, rep_id)
            if rep is None or rep.region_id != self.current_user.region_id:
                return -1, -1
            return rep_id, self.current_user.region_id
        return None, self.current_user.region_id

    def _region_scope(self, region_id: int | None) -> int | None:
        if self.current_user is None or self.current_user.is_sales_director:
            return region_id
        if self.current_user.region_id is None:
            return -1
        if region_id is not None and region_id != self.current_user.region_id:
            return -1
        return self.current_user.region_id

    async def _scoped_rep_ranking(
        self,
        session: AsyncSession,
        start: date,
        end: date,
    ) -> list[tuple[int, Decimal]]:
        if self.current_user is None or self.current_user.is_sales_director:
            return await self.order_repository.find_rep_ranking(session, start, end)
        if self.current_user.is_sales_rep:
            rows = await self.order_repository.find_rep_ranking(session, start, end)
            return [row for row in rows if row[0] == self.current_user.rep_id]
        if self.current_user.region_id is None:
            return []
        return await self.order_repository.find_rep_ranking_by_region(session, self.current_user.region_id, start, end)

    async def _scoped_region_ranking(
        self,
        session: AsyncSession,
        start: date,
        end: date,
    ) -> list[tuple[int, Decimal]]:
        if self.current_user is None or self.current_user.is_sales_director:
            return await self.order_repository.find_region_ranking(session, start, end)
        if self.current_user.is_sales_rep:
            if self.current_user.region_id is None:
                return []
            total = await self.order_repository.sum_amount_by_rep(session, self.current_user.rep_id, start, end)
            return [] if total == 0 else [(self.current_user.region_id, total)]
        if self.current_user.region_id is None:
            return []
        return await self.order_repository.find_region_ranking_by_region(session, self.current_user.region_id, start, end)

    async def _scoped_product_ranking(
        self,
        session: AsyncSession,
        start: date,
        end: date,
    ) -> list[tuple[int, Decimal, int]]:
        if self.current_user is None or self.current_user.is_sales_director:
            return await self.order_repository.find_product_ranking(session, start, end)
        if self.current_user.is_sales_rep:
            return await self.order_repository.find_product_ranking_by_rep(session, self.current_user.rep_id, start, end)
        if self.current_user.region_id is None:
            return []
        return await self.order_repository.find_product_ranking_by_region(session, self.current_user.region_id, start, end)

    def _is_invalid_scope(self, rep_id: int | None, region_id: int | None) -> bool:
        return rep_id == -1 or region_id == -1

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
