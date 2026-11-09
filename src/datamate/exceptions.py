"""
exceptions.py — Định nghĩa các lớp ngoại lệ nghiệp vụ của DataMate.

Cung cấp:
- DataMateError: Ngoại lệ cơ sở cho toàn bộ package.
- DataNotFoundError: Ném ra khi code mô hình không tìm thấy bảng hoặc cột cần thiết trong dữ liệu,
  chuyển tiếp thông tin cấu trúc shop thực tế cho Self-Correction Loop.
"""

from __future__ import annotations

from typing import List, Optional


class DataMateError(Exception):
    """Lớp ngoại lệ cơ sở cho hệ thống DataMate."""
    pass


class DataNotFoundError(DataMateError):
    """
    Ném ra khi hàm solution(data) không tìm thấy bảng hoặc cột cần thiết trong dữ liệu.

    Attributes:
        message (str): Thông điệp mô tả chi tiết lỗi thiếu bảng/cột.
        table_name (Optional[str]): Tên bảng mà mô hình tìm kiếm nhưng không thấy.
        column_name (Optional[str]): Tên cột mà mô hình tìm kiếm nhưng không thấy.
        available_tables (List[str]): Danh sách các bảng thực tế có trong dữ liệu shop.
        available_columns (List[str]): Danh sách các cột thực tế của bảng đang xét.
    """

    def __init__(
        self,
        message: str = "Không tìm thấy bảng hoặc cột dữ liệu cần thiết.",
        table_name: Optional[str] = None,
        column_name: Optional[str] = None,
        available_tables: Optional[List[str]] = None,
        available_columns: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.table_name = table_name
        self.column_name = column_name
        self.available_tables = available_tables or []
        self.available_columns = available_columns or []

    def __str__(self) -> str:
        parts = [self.message]
        if self.table_name:
            parts.append(f"[Bảng tìm kiếm: '{self.table_name}']")
        if self.column_name:
            parts.append(f"[Cột tìm kiếm: '{self.column_name}']")
        if self.available_tables:
            parts.append(f"[Các bảng thực tế có sẵn: {', '.join(self.available_tables[:10])}]")
        if self.available_columns:
            parts.append(f"[Các cột thực tế có sẵn: {', '.join(self.available_columns[:15])}]")
        return " ".join(parts)
