from typing import Literal

from pydantic import BaseModel

from app.models.sales_rep import SalesRep


SalesRole = Literal["SALES_REP", "SALES_MANAGER", "SALES_DIRECTOR"]


class CurrentUser(BaseModel):
    username: str
    role: SalesRole
    region_id: int | None
    rep_id: int

    @classmethod
    def from_sales_rep(cls, rep: SalesRep) -> "CurrentUser":
        return cls(
            username=rep.name,
            role=rep.role,  # type: ignore[arg-type]
            region_id=rep.region_id,
            rep_id=rep.id,
        )

    @property
    def is_sales_rep(self) -> bool:
        return self.role == "SALES_REP"

    @property
    def is_sales_manager(self) -> bool:
        return self.role == "SALES_MANAGER"

    @property
    def is_sales_director(self) -> bool:
        return self.role == "SALES_DIRECTOR"

    def permission_description(self) -> str:
        if self.is_sales_director:
            return "all company sales data"
        if self.is_sales_manager:
            return f"region_id={self.region_id}"
        return f"rep_id={self.rep_id}, region_id={self.region_id}"
