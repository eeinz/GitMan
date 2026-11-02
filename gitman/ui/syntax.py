"""Syntax highlighting for unified git diffs."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self._addition = QTextCharFormat()
        self._addition.setForeground(QColor("#7ee787"))
        self._deletion = QTextCharFormat()
        self._deletion.setForeground(QColor("#ff9b95"))
        self._hunk = QTextCharFormat()
        self._hunk.setForeground(QColor("#79c0ff"))
        self._hunk.setFontWeight(QFont.Weight.DemiBold)
        self._header = QTextCharFormat()
        self._header.setForeground(QColor("#8b949e"))
        self._meta = QTextCharFormat()
        self._meta.setForeground(QColor("#d2a8ff"))
        self._binary = QTextCharFormat()
        self._binary.setForeground(QColor("#f2cc60"))

    def highlightBlock(self, text: str) -> None:
        if text.startswith(("diff --git", "index ", "--- ", "+++ ", "new file", "deleted file")):
            self.setFormat(0, len(text), self._header)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk)
        elif text.startswith(("rename from", "rename to", "similarity index", "copy from", "copy to")):
            self.setFormat(0, len(text), self._meta)
        elif text.startswith("Binary files") or text.startswith("GIT binary patch"):
            self.setFormat(0, len(text), self._binary)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self._addition)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._deletion)
