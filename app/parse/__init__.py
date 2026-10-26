from app.parse.detect import detect, detect_full
from app.parse.execute import execute, summarize
from app.parse.grid import Grid, read_grid
from app.parse.recipe import Block, IdColumn, Label, Recipe, ValueColumn, Wide
from app.parse.values import MAX_COLS, MAX_ROWS, ParseError


def parse_file(raw: bytes, name: str, sheet: str | None = None) -> dict:
    grid, sheets = read_grid(raw, name, sheet)
    recipe, conf, alternatives, issues = detect_full(grid)
    out = execute(grid, recipe)
    reading = out["reading"]
    reading["confidence"] = round(min(conf, reading["confidence"]), 2)
    reading["issues"] = list(dict.fromkeys(issues + reading["issues"]))
    reading["alternatives"] = [{"summary": a["summary"], "recipe": a["recipe"].model_dump()} for a in alternatives]
    out.update(name=name[:120], sheet=grid.sheet, sheets=sheets)
    return out


__all__ = ["Block", "Grid", "IdColumn", "Label", "MAX_COLS", "MAX_ROWS", "ParseError", "Recipe", "ValueColumn", "Wide", "detect",
           "detect_full", "execute", "parse_file", "read_grid", "summarize"]
