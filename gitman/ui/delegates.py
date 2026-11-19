"""Custom painting for status badges."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

from .repo_model import Roles


class BadgeDelegate(QStyledItemDelegate):
    """Draws a compact rounded badge instead of plain text."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        background = QColor("#ffffff")
        brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if brush is not None and hasattr(brush, "color"):
            background = brush.color()
        if selected:
            background = QColor("#eef2ff")
        elif hovered:
            background = QColor("#f8faff")
        painter.fillRect(option.rect, background)

        painter.setPen(QPen(QColor("#f1f4f9"), 1))
        painter.drawLine(
            option.rect.left(),
            option.rect.bottom(),
            option.rect.right(),
            option.rect.bottom(),
        )

        text = str(index.data(Roles.BadgeText) or "")
        if not text:
            painter.restore()
            return

        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        if font.pointSizeF() > 0:
            font.setPointSizeF(max(8.0, font.pointSizeF() * 0.96))
        painter.setFont(font)

        fg = QColor(str(index.data(Roles.BadgeFg) or "#64748b"))
        bg = QColor(str(index.data(Roles.BadgeBg) or "#f1f5f9"))
        if not fg.isValid():
            fg = QColor("#64748b")
        if not bg.isValid():
            bg = QColor("#f1f5f9")

        metrics = QFontMetrics(font)
        max_width = max(24, option.rect.width() - 24)
        display = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max_width - 16)
        text_width = metrics.horizontalAdvance(display)
        badge_width = min(max_width, text_width + 18)
        badge_height = 24
        x = option.rect.left() + 12
        y = option.rect.center().y() - badge_height // 2 + 1
        badge_rect = QRectF(x, y, badge_width, badge_height)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(badge_rect, 7.5, 7.5)

        painter.setPen(fg)
        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            display,
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        size = super().sizeHint(option, index)
        size.setHeight(max(38, size.height()))
        return size


class CommitCellDelegate(QStyledItemDelegate):
    """Two-line commit cell: subject on top, date below."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        background = QColor("#ffffff")
        brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if brush is not None and hasattr(brush, "color"):
            background = brush.color()
        if selected:
            background = QColor("#eef2ff")
        elif hovered:
            background = QColor("#f8faff")
        painter.fillRect(option.rect, background)

        painter.setPen(QPen(QColor("#f1f4f9"), 1))
        painter.drawLine(
            option.rect.left(),
            option.rect.bottom(),
            option.rect.right(),
            option.rect.bottom(),
        )

        subject = str(index.data(Roles.CommitSubject) or "")
        date_text = str(index.data(Roles.CommitDate) or "")
        left = option.rect.left() + 12
        width = max(10, option.rect.width() - 24)

        if not date_text:
            font = QFont(option.font)
            if font.pointSizeF() > 0:
                font.setPointSizeF(max(8.0, font.pointSizeF() * 0.95))
            painter.setFont(font)
            painter.setPen(QColor("#94a3b8"))
            metrics = QFontMetrics(font)
            text = metrics.elidedText(
                subject or "—", Qt.TextElideMode.ElideRight, width
            )
            painter.drawText(
                QRect(left, option.rect.top() + 4, width, option.rect.height() - 8),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                text,
            )
            painter.restore()
            return

        subject_font = QFont(option.font)
        subject_font.setWeight(QFont.Weight.Medium)
        if subject_font.pointSizeF() > 0:
            subject_font.setPointSizeF(max(8.0, subject_font.pointSizeF() * 0.98))
        painter.setFont(subject_font)
        subject_metrics = QFontMetrics(subject_font)
        subject_text = subject_metrics.elidedText(
            subject, Qt.TextElideMode.ElideRight, width
        )
        painter.setPen(QColor("#1e293b"))
        painter.drawText(
            QRect(left, option.rect.top() + 5, width, 19),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            subject_text,
        )

        date_font = QFont(option.font)
        if date_font.pointSizeF() > 0:
            date_font.setPointSizeF(max(7.5, date_font.pointSizeF() * 0.82))
        date_font.setWeight(QFont.Weight.Normal)
        painter.setFont(date_font)
        date_metrics = QFontMetrics(date_font)
        date_display = date_metrics.elidedText(
            date_text, Qt.TextElideMode.ElideRight, width
        )
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(
            QRect(left, option.rect.top() + 23, width, 15),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            date_display,
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        size = super().sizeHint(option, index)
        size.setHeight(max(44, size.height()))
        return size
