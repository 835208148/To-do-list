"""Queries and CSV export for task records."""
import csv
import os
import tempfile
from pathlib import Path


def read_tasks(db, date_range=None, *, completed_only=False, keyword="", include_times=False):
    where = ""
    parameters = ()
    order = "done, sort_order, id DESC"
    if completed_only or date_range is not None:
        where = "WHERE done = 1"
        order = "completed_on DESC, sort_order, id DESC"
    if date_range is not None:
        where += " AND completed_on BETWEEN ? AND ?"
        parameters = date_range

    columns = "id, title, done, deadline, completed_on, note"
    if include_times:
        columns += ", created_at, completed_at"
    rows = db.execute(
        f"SELECT {columns} FROM tasks "
        f"{where} ORDER BY {order}", parameters
    ).fetchall()
    keyword = keyword.strip().casefold()
    if not keyword:
        return rows
    return [row for row in rows if keyword in row[1].casefold() or keyword in row[5].casefold()]


def spreadsheet_text(value):
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def export_tasks(path, rows):
    path = Path(path)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8-sig", newline="", dir=path.parent,
        prefix=".todo-export-", suffix=".tmp", delete=False
    ) as output:
        staged = Path(output.name)
        try:
            writer = csv.writer(output)
            writer.writerow(("事项", "备注", "截止时间", "状态", "完成日期"))
            for _, title, done, deadline, completed_on, note in rows:
                writer.writerow((
                    spreadsheet_text(title), spreadsheet_text(note),
                    deadline.replace("T", " ") if deadline else "",
                    "已完成" if done else "未完成", completed_on or "",
                ))
            output.close()
            os.replace(staged, path)
        finally:
            output.close()
            staged.unlink(missing_ok=True)
