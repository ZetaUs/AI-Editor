from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QInputDialog,
    QMessageBox,
    QStyle,
)
from PySide6.QtGui import QAction


class FileTree(QTreeWidget):
    file_requested = Signal(str)
    file_created = Signal(str)
    file_deleted = Signal(str)
    file_renamed = Signal(str, str)
    directory_created = Signal(str)

    def __init__(self, base_dir: Path, history=None, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.history = history
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.itemDoubleClicked.connect(self._on_double_click)
        self._reload()

    def _reload(self):
        self.clear()
        root_item = self._build_item(self.base_dir)
        root_item.setData(0, Qt.UserRole, str(self.base_dir))
        root_item.setExpanded(True)
        self.addTopLevelItem(root_item)

    def _build_item(self, path: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem([path.name or str(path)])
        item.setData(0, Qt.UserRole, str(path))
        if path.is_dir():
            item.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
            try:
                children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                for child in children:
                    if child.name.startswith("."):
                        continue
                    item.addChild(self._build_item(child))
            except PermissionError:
                pass
        else:
            item.setIcon(0, self.style().standardIcon(QStyle.SP_FileIcon))
        return item

    def refresh(self):
        self._reload()

    def _current_path(self) -> Path | None:
        item = self.currentItem()
        if item:
            return Path(item.data(0, Qt.UserRole))
        return None

    def _show_menu(self, pos):
        item = self.itemAt(pos)
        path = Path(item.data(0, Qt.UserRole)) if item else self.base_dir
        is_dir = path.is_dir() if item else True

        menu = QMenu(self)

        if is_dir:
            act_new_file = QAction("New File", self)
            act_new_file.triggered.connect(lambda: self._create_file(path))
            menu.addAction(act_new_file)

            act_new_dir = QAction("New Folder", self)
            act_new_dir.triggered.connect(lambda: self._create_dir(path))
            menu.addAction(act_new_dir)
            menu.addSeparator()

        if item is not None:
            act_rename = QAction("Rename", self)
            act_rename.triggered.connect(lambda: self._rename(path))
            menu.addAction(act_rename)

            act_delete = QAction("Delete", self)
            act_delete.triggered.connect(lambda: self._delete(path))
            menu.addAction(act_delete)
            menu.addSeparator()

        act_refresh = QAction("Refresh", self)
        act_refresh.triggered.connect(self.refresh)
        menu.addAction(act_refresh)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _create_file(self, dir_path: Path):
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            target = dir_path / name
            if target.exists():
                QMessageBox.warning(self, "Error", f"{name} already exists")
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
            if self.history:
                self.history.record_create(str(target.relative_to(self.base_dir)))
            self.file_created.emit(str(target))
            self.refresh()

    def _create_dir(self, dir_path: Path):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            target = dir_path / name
            if target.exists():
                QMessageBox.warning(self, "Error", f"{name} already exists")
                return
            target.mkdir(parents=True, exist_ok=True)
            if self.history:
                self.history.record_create(str(target.relative_to(self.base_dir)))
            self.directory_created.emit(str(target))
            self.refresh()

    def _rename(self, path: Path):
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=path.name)
        if ok and new_name and new_name != path.name:
            new_path = path.parent / new_name
            if new_path.exists():
                QMessageBox.warning(self, "Error", f"{new_name} already exists")
                return
            if self.history:
                old_rel = str(path.relative_to(self.base_dir))
                new_rel = str(new_path.relative_to(self.base_dir))
                self.history.record_rename(old_rel, new_rel)
            path.rename(new_path)
            self.file_renamed.emit(str(path), str(new_path))
            self.refresh()

    def _delete(self, path: Path):
        rel = path.relative_to(self.base_dir)
        reply = QMessageBox.question(
            self, "Delete", f"Delete {rel}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            content = None
            if path.is_file():
                content = path.read_text(encoding="utf-8", errors="replace")
                path.unlink()
            else:
                content = None
                import shutil
                shutil.rmtree(path)
            if self.history:
                self.history.record_delete(str(rel), content)
            self.file_deleted.emit(str(path))
            self.refresh()

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        path = Path(item.data(0, Qt.UserRole))
        if path.is_file():
            self.file_requested.emit(str(path))