from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_MISSING = [":", "..", "...", "n.a.", "n/a", "na", "nan", "null", "none", "-", "–", "—", "x", "c", ".", "/",
                   "#n/a", "#value!", "#div/0!", "n.v.", "k.a.", "s.o.", "nd", "n.d."]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Label(_M):
    column: str
    value: str


class IdColumn(_M):
    index: int = Field(ge=0)
    name: str


class ValueColumn(_M):
    index: int = Field(ge=0)
    name: str
    flag_index: int | None = Field(default=None, ge=0)


class Wide(_M):
    name: str
    levels: list[str] | None = None


class Block(_M):
    header_rows: list[int] = Field(default_factory=list)
    data_start: int = Field(ge=0)
    data_end: int = Field(ge=0)
    label: Label | None = None
    id_columns: list[IdColumn] = Field(default_factory=list)
    value_columns: list[ValueColumn] = Field(default_factory=list)
    wide: Wide | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.data_end < self.data_start:
            raise ValueError("data_end is before data_start")
        if not self.id_columns and not self.value_columns:
            raise ValueError("a block needs at least one column")
        if self.wide and not self.value_columns:
            raise ValueError("wide needs value columns")
        return self


class Recipe(_M):
    sheet: str | None = None
    blocks: list[Block] = Field(min_length=1)
    missing_markers: list[str] = Field(default_factory=lambda: list(DEFAULT_MISSING))
    decimal: Literal[".", ","] = "."
    thousands: Literal["", ",", ".", " "] = ""
    aggregates: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
