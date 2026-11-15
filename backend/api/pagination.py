"""Lists: ?page=1&page_size=20 in, {"items", "total", "page", "page_size"} out."""
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageParams:
    """Use as ``params: PageParams = Depends()``."""

    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        self.page = page
        self.page_size = page_size


def paginate(db: Session, stmt: Select, params: PageParams) -> tuple[list, int]:
    """The rows of the asked page and the total number of rows."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(
        stmt.limit(params.page_size).offset((params.page - 1) * params.page_size)
    ).all()
    return list(rows), total
