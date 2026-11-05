from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt, QSize
from PySide6.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
    QFont,
    QColor,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


class PythonHighlighter(QSyntaxHighlighter):
    KEYWORDS = {
        "def", "class", "return", "if", "elif", "else", "for", "while",
        "try", "except", "finally", "with", "import", "from", "as",
        "pass", "break", "continue", "raise", "yield", "lambda",
        "global", "nonlocal", "assert", "del", "and", "or", "not",
        "in", "is", "None", "True", "False", "async", "await",
    }
    BUILTINS = {
        "print", "len", "str", "int", "float", "list", "dict", "tuple",
        "set", "range", "map", "filter", "zip", "enumerate", "open",
        "input", "type", "isinstance", "super", "self", "cls",
    }

    def __init__(self, document):
        super().__init__(document)

        fmt_key = QTextCharFormat()
        fmt_key.setForeground(QColor("#FF79C6"))
        fmt_key.setFontWeight(QFont.Bold)

        fmt_builtin = QTextCharFormat()
        fmt_builtin.setForeground(QColor("#8BE9FD"))

        fmt_str = QTextCharFormat()
        fmt_str.setForeground(QColor("#F1FA8C"))

        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor("#6272A4"))
        fmt_comment.setFontItalic(True)

        fmt_num = QTextCharFormat()
        fmt_num.setForeground(QColor("#BD93F9"))

        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        self._rules.append((QRegularExpression(
            r"\b(" + "|".join(self.KEYWORDS) + r")\b"), fmt_key))
        self._rules.append((QRegularExpression(
            r"\b(" + "|".join(self.BUILTINS) + r")\b"), fmt_builtin))
        self._rules.append((QRegularExpression(
            r"\b\d+(\.\d+)?\b"), fmt_num))

        self._triple_str = (QRegularExpression(r'"""'), fmt_str)
        self._single_str = (QRegularExpression(r"'''"), fmt_str)
        self._dq_str = (QRegularExpression(r'"([^"\\]|\\.)*"'), fmt_str)
        self._sq_str = (QRegularExpression(r"'([^'\\]|\\.)*'"), fmt_str)
        self._comment = (QRegularExpression(r"#[^\n]*"), fmt_comment)

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        for pattern, fmt in (self._dq_str, self._sq_str, self._comment):
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class CppHighlighter(QSyntaxHighlighter):
    KEYWORDS = {
        "int", "void", "char", "float", "double", "bool", "string",
        "class", "struct", "namespace", "template", "typename",
        "if", "else", "for", "while", "do", "switch", "case", "break",
        "continue", "return", "goto", "try", "catch", "throw",
        "public", "private", "protected", "virtual", "override",
        "const", "static", "inline", "explicit", "friend",
        "new", "delete", "this", "nullptr", "true", "false",
        "include", "using", "typedef", "#define", "#include", "#ifdef",
        "#ifndef", "#endif", "#pragma",
    }

    def __init__(self, document):
        super().__init__(document)

        fmt_key = QTextCharFormat()
        fmt_key.setForeground(QColor("#FF79C6"))
        fmt_key.setFontWeight(QFont.Bold)

        fmt_str = QTextCharFormat()
        fmt_str.setForeground(QColor("#F1FA8C"))

        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor("#6272A4"))
        fmt_comment.setFontItalic(True)

        fmt_num = QTextCharFormat()
        fmt_num.setForeground(QColor("#BD93F9"))

        fmt_preproc = QTextCharFormat()
        fmt_preproc.setForeground(QColor("#50FA7B"))

        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = [
            (QRegularExpression(r"\b(" + "|".join(self.KEYWORDS) + r")\b"), fmt_key),
            (QRegularExpression(r"\b\d+(\.\d+)?[lf]?\b"), fmt_num),
            (QRegularExpression(r'"([^"\\]|\\.)*"'), fmt_str),
            (QRegularExpression(r"'([^'\\]|\\.)*'"), fmt_str),
            (QRegularExpression(r"//[^\n]*"), fmt_comment),
            (QRegularExpression(r"#\w+.*"), fmt_preproc),
        ]

        self._block_comment_fmt = fmt_comment

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        self.setCurrentBlockState(0)
        start_idx = 0
        if self.previousBlockState() != 1:
            start_idx = QRegularExpression(r"/\*").match(text).capturedStart()
        while start_idx >= 0:
            end_match = QRegularExpression(r"\*/").match(text, start_idx + 2)
            if end_match.hasMatch():
                self.setFormat(start_idx, end_match.capturedEnd() - start_idx, self._block_comment_fmt)
                start_idx = QRegularExpression(r"/\*").match(text, end_match.capturedEnd()).capturedStart()
            else:
                self.setFormat(start_idx, len(text) - start_idx, self._block_comment_fmt)
                self.setCurrentBlockState(1)
                break


class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self._file_path: str | None = None
        self._dirty = False

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_number_area_width(0)
        self._highlight_current_line()

        font = QFont("Consolas, 'Courier New', monospace")
        font.setPointSize(10)
        self.setFont(font)

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #282A36;
                color: #F8F8F2;
                border: none;
            }
            QPlainTextEdit:focus {
                outline: none;
            }
        """)

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#21222C"))

        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_num + 1)
                painter.setPen(QColor("#6272A4"))
                painter.drawText(0, top, self.line_number_area.width() - 5,
                                 self.fontMetrics().height(), Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_num += 1

    def _update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(cr.left(), cr.top(),
                                          self.line_number_area_width(), cr.height())

    def _highlight_current_line(self):
        extra = QTextEdit.ExtraSelection()
        extra.format.setBackground(QColor("#44475A"))
        extra.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        extra.cursor = self.textCursor()
        extra.cursor.clearSelection()
        self.setExtraSelections([extra])

    def set_file(self, path: str):
        self._file_path = path
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix in (".py", ".pyi"):
            self._highlighter = PythonHighlighter(self.document())
        elif suffix in (".cpp", ".cxx", ".cc", ".c++", ".h", ".hpp", ".hxx", ".c"):
            self._highlighter = CppHighlighter(self.document())
        else:
            self._highlighter = None

    def file_path(self) -> str | None:
        return self._file_path

    def set_dirty(self, dirty: bool):
        self._dirty = dirty

    def is_dirty(self) -> bool:
        return self._dirty