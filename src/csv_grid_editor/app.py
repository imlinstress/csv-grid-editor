import csv
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import alignment, group, lint, query, theme
from .model import CsvDocument


class EditorWindow(Gtk.ApplicationWindow):
    def __init__(self, application, path=None):
        super().__init__(application=application, title="CSV Grid Editor")
        self.set_default_size(1100, 700)
        self.accel_group = Gtk.AccelGroup()
        self.add_accel_group(self.accel_group)
        self.doc = CsvDocument()
        self.overrides = {}
        self.active_column = 0
        self.column_objects = {}
        self.renderers = {}
        self.column_map = {}
        self.bad_rows = set()
        self.issue_count = 0
        self.restore_order_item = None
        self.number_cell = None
        self.data_cells = {}
        self.header_labels = {}
        self.theme_handlers = theme.connect_settings(self._on_theme_changed)
        self._build_ui()
        if path:
            self.open_file(path)
        else:
            self.new_document()
        self.show_all()

    def _build_ui(self):
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        layout.pack_start(self._build_menu_bar(), False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.tree = Gtk.TreeView()
        self.tree.override_background_color(Gtk.StateFlags.NORMAL, theme.surface_color(self))
        self.tree.set_has_tooltip(True)
        self.tree.connect("cursor-changed", self._on_cursor_changed)
        self.tree.connect("query-tooltip", self._on_query_tooltip)
        scrolled.add(self.tree)
        layout.pack_start(scrolled, True, True, 0)

        self.status = Gtk.Statusbar()
        self.status_context = self.status.get_context_id("editor")
        layout.pack_start(self.status, False, False, 0)

        self.add(layout)
        self.connect("delete-event", self._on_delete_event)
        self.connect("destroy", self._on_destroy)

    def _build_menu_bar(self):
        bar = Gtk.MenuBar()
        file_menu = Gtk.Menu()
        self._add_item(file_menu, "_New", self._on_new, "<Control>n")
        self._add_item(file_menu, "_Open…", self._on_open, "<Control>o")
        self._add_item(file_menu, "_Save", self._on_save, "<Control>s")
        self._add_item(file_menu, "Save _As…", self._on_save_as, "<Control><Shift>s")
        file_menu.append(Gtk.SeparatorMenuItem.new())
        self._add_item(file_menu, "_Quit", self._on_quit, "<Control>q")
        bar.append(self._submenu("_File", file_menu))

        edit_menu = Gtk.Menu()
        self._add_item(edit_menu, "_Add Row", self._on_add_row, "Insert")
        self._add_item(edit_menu, "_Delete Row", self._on_delete_row, "Delete")
        self._add_item(edit_menu, "Delete _Empty Rows", self._on_delete_empty_rows, "<Control><Shift>Delete")
        self.restore_order_item = self._add_item(
            edit_menu, "Restore _Original Order", self._on_restore_order, "<Control><Shift>r"
        )
        edit_menu.append(Gtk.SeparatorMenuItem.new())
        self._add_item(edit_menu, "_Rename Column", self._on_rename_column, "F2")
        bar.append(self._submenu("_Edit", edit_menu))

        column_menu = Gtk.Menu()
        self._add_item(column_menu, "Insert Column _Left", self._on_insert_left)
        self._add_item(column_menu, "Insert Column _Right", self._on_insert_right)
        self._add_item(column_menu, "_Delete Column", self._on_delete_column)
        column_menu.append(Gtk.SeparatorMenuItem.new())
        self._add_item(column_menu, "Align _Left", self._on_align_left)
        self._add_item(column_menu, "Align _Center", self._on_align_center)
        self._add_item(column_menu, "Align _Right", self._on_align_right)
        column_menu.append(Gtk.SeparatorMenuItem.new())
        self._add_item(column_menu, "_Auto-size This Column", self._on_auto_size)
        self._add_item(column_menu, "Auto-size _All Columns", self._on_auto_size_all)
        bar.append(self._submenu("_Columns", column_menu))

        tools_menu = Gtk.Menu()
        self._add_item(tools_menu, "_CSVLint", self._on_lint)
        self._add_item(tools_menu, "_Query…", self._on_query, "<Control><Shift>q")
        self._add_item(tools_menu, "_Group By…", self._on_group_by, "<Control><Shift>g")
        tools_menu.append(Gtk.SeparatorMenuItem.new())
        self._add_item(tools_menu, "Copy as _TSV", self._on_copy_tsv)
        self._add_item(tools_menu, "Copy as _Markdown", self._on_copy_markdown)
        bar.append(self._submenu("_Tools", tools_menu))

        help_menu = Gtk.Menu()
        self._add_item(help_menu, "_About", self._on_about)
        bar.append(self._submenu("_Help", help_menu))
        return bar

    def _submenu(self, label, menu):
        item = Gtk.MenuItem.new_with_label(label)
        item.set_submenu(menu)
        return item

    def _add_item(self, menu, label, callback, accelerator=None):
        item = Gtk.MenuItem.new_with_label(label)
        item.connect("activate", callback)
        if accelerator:
            key, modifiers = Gtk.accelerator_parse(accelerator)
            item.add_accelerator("activate", self.accel_group, key, modifiers, Gtk.AccelFlags.VISIBLE)
        menu.append(item)
        return item

    def new_document(self):
        if not self._confirm_discard():
            return
        self.doc = CsvDocument.new()
        self.overrides = {}
        self.active_column = 0
        self._rebuild_view()
        self._refresh_lint()

    def open_file(self, path):
        if not self._confirm_discard():
            return
        try:
            document = CsvDocument.load(path)
        except (OSError, UnicodeError, csv.Error) as error:
            self._show_error("Could not open CSV file", str(error))
            return
        self.doc = document
        self.overrides = {}
        self.active_column = 0
        self._rebuild_view()
        self._refresh_lint()

    def _rebuild_view(self, select_row=None):
        self.tree.set_model(None)
        for column in self.tree.get_columns():
            self.tree.remove_column(column)
        self.column_objects = {}
        self.renderers = {}
        self.column_map = {}
        self.number_cell = None
        self.data_cells = {}
        self.header_labels = {}

        store = Gtk.ListStore(*([str] * len(self.doc.headers)))
        for row in self.doc.rows:
            store.append(row)
        self.store = store
        self.tree.set_model(store)

        number_column = Gtk.TreeViewColumn(title="#")
        number_cell = Gtk.CellRendererText()
        number_cell.set_property("xalign", 1.0)
        number_cell.set_property("foreground-rgba", theme.line_number_color(theme.is_dark(self)))
        number_column.pack_start(number_cell, True)
        number_column.set_cell_data_func(number_cell, self._render_line_number)
        number_column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        number_column.set_fixed_width(56)
        number_column.set_resizable(False)
        number_column.set_clickable(False)
        self.tree.append_column(number_column)
        self.number_cell = number_cell

        dark = theme.is_dark(self)
        for index, header in enumerate(self.doc.headers):
            cell = Gtk.CellRendererText()
            cell.set_property("editable", True)
            cell.set_property("foreground-rgba", theme.column_color(index, dark))
            cell.connect("edited", self._on_cell_edited, index)
            values = [header or "Column {}".format(index + 1)]
            values.extend(list(self.doc.column_values(index))[:200])
            column = Gtk.TreeViewColumn(
                title=header or "Column {}".format(index + 1),
                cell_renderer=cell,
                text=index,
            )
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(alignment.auto_width(self.tree, values))
            column.set_min_width(48)
            column.set_resizable(True)
            column.set_clickable(True)
            column.connect("clicked", self._on_column_clicked, index)
            column.set_cell_data_func(cell, self._render_cell_background)
            self.tree.append_column(column)
            label = column.get_widget()
            if label is None:
                label = Gtk.Label(label=header or "Column {}".format(index + 1))
                column.set_widget(label)
                label.show()
            label.override_color(Gtk.StateFlags.NORMAL, theme.column_color(index, dark))
            self.header_labels[index] = label
            self.data_cells[index] = cell
            self.column_objects[index] = column
            self.renderers[index] = cell
            self.column_map[column] = index
            self._apply_alignment(index)

        if select_row is not None and 0 <= select_row < len(self.doc.rows):
            self.tree.set_cursor(Gtk.TreePath.new_from_indices([select_row]), None, False)
        self._update_status()

    def _apply_alignment(self, index):
        if index not in self.renderers:
            return
        values = self.doc.column_values(index)
        chosen = alignment.resolve_alignment(values, self.overrides.get(index))
        xalign = alignment.ALIGN_XALIGN[chosen]
        self.renderers[index].set_property("xalign", xalign)
        self.column_objects[index].set_alignment(xalign)

    def _row_background(self, index, bad=False):
        path, _ = self.tree.get_cursor()
        if path is not None and path.get_indices()[0] == index:
            return theme.selection_color(self)
        return theme.background_color(self, index, bad)

    def _render_line_number(self, column, cell, model, tree_iter, data=None):
        index = model.get_path(tree_iter).get_indices()[0]
        cell.set_property("text", str(index + 1))
        cell.set_property("background-rgba", self._row_background(index, index in self.bad_rows))

    def _render_cell_background(self, column, cell, model, tree_iter, data=None):
        index = model.get_path(tree_iter).get_indices()[0]
        cell.set_property("background-rgba", self._row_background(index, index in self.bad_rows))

    def apply_theme(self):
        dark = theme.is_dark(self)
        surface = theme.surface_color(self)
        self.override_background_color(Gtk.StateFlags.NORMAL, surface)
        self.tree.override_background_color(Gtk.StateFlags.NORMAL, surface)
        if self.number_cell is not None:
            self.number_cell.set_property("foreground-rgba", theme.line_number_color(dark))
        for index, cell in self.data_cells.items():
            cell.set_property("foreground-rgba", theme.column_color(index, dark))
        for index, label in self.header_labels.items():
            label.override_color(Gtk.StateFlags.NORMAL, theme.column_color(index, dark))
        self.tree.queue_draw()

    def _on_theme_changed(self, *args):
        if self.theme_handlers:
            theme.sync_system_settings()
            GLib.idle_add(self.apply_theme)

    def _on_destroy(self, widget=None):
        theme.disconnect_settings(self.theme_handlers)
        self.theme_handlers = []

    def _on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        position = widget.get_path_at_pos(int(x), int(y))
        if not position:
            return False
        column = position[1]
        index = self.column_map.get(column)
        if index is None:
            return False
        header = GLib.markup_escape_text(self.doc.headers[index])
        tooltip.set_markup("<b>Col #{}</b> — Header: {}".format(index + 1, header))
        return True

    def _refresh_lint(self):
        issues = lint.check(self.doc)
        self.bad_rows = lint.bad_rows(issues)
        self.issue_count = len(issues)
        if self.tree.get_model() is not None:
            self.tree.queue_draw()
        self._update_status()
        return issues

    def _update_status(self):
        marker = " *" if self.doc.dirty else ""
        self.set_title("{}{} — CSV Grid Editor".format(self.doc.name, marker))
        issues = "    {} CSV issues".format(self.issue_count) if self.issue_count else ""
        grouped = "    Grouped by: {}".format(", ".join(self.doc.group_columns)) if self.doc.grouped else ""
        message = "{}    {} rows × {} columns{}{}{}".format(
            self.doc.name, len(self.doc.rows), len(self.doc.headers), marker, grouped, issues
        )
        if self.restore_order_item is not None:
            self.restore_order_item.set_sensitive(self.doc.grouped)
        self.status.pop(self.status_context)
        self.status.push(self.status_context, message)

    def _current_row(self):
        path, _ = self.tree.get_cursor()
        return path.get_indices()[0] if path else None

    def _confirm_discard(self):
        if not self.doc.dirty:
            return True
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Unsaved changes",
        )
        dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("_Discard changes", Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.format_secondary_text("Changes to {} will be lost.".format(self.doc.name))
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.ACCEPT

    def _show_error(self, title, message):
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _on_delete_event(self, widget, event):
        return not self._confirm_discard()

    def _on_cursor_changed(self, tree):
        _, column = tree.get_cursor()
        if column in self.column_map:
            self.active_column = self.column_map[column]
        tree.queue_draw()

    def _on_column_clicked(self, column, index):
        self.active_column = index

    def _on_cell_edited(self, renderer, path, new_text, column):
        row = int(path)
        self.doc.set_cell(row, column, new_text)
        self.store[row][column] = new_text
        self._update_status()

    def _on_new(self, widget=None):
        self.new_document()

    def _on_open(self, widget=None):
        dialog = Gtk.FileChooserDialog(
            title="Open CSV file",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=("_Cancel", Gtk.ResponseType.CANCEL, "_Open", Gtk.ResponseType.ACCEPT),
        )
        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("CSV files")
        csv_filter.add_pattern("*.csv")
        dialog.add_filter(csv_filter)
        all_filter = Gtk.FileFilter()
        all_filter.set_name("All files")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)
        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if path:
            self.open_file(path)

    def _perform_save(self):
        if not self.doc.path:
            self._on_save_as()
            return
        try:
            self.doc.save()
        except OSError as error:
            self._show_error("Could not save CSV file", str(error))
            return
        self._update_status()

    def _on_save(self, widget=None):
        self._perform_save()

    def _on_save_as(self, widget=None):
        dialog = Gtk.FileChooserDialog(
            title="Save CSV file",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
            buttons=("_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.ACCEPT),
        )
        dialog.set_current_name(self.doc.name)
        dialog.set_do_overwrite_confirmation(True)
        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if not path:
            return
        try:
            self.doc.save(path)
        except OSError as error:
            self._show_error("Could not save CSV file", str(error))
            return
        self._rebuild_view()

    def _on_quit(self, widget=None):
        if self._confirm_discard():
            self.destroy()
            self.get_application().quit()

    def _on_add_row(self, widget=None):
        current = self._current_row()
        index = current + 1 if current is not None else len(self.doc.rows)
        self.doc.insert_row(index)
        self._rebuild_view(index)

    def _on_delete_row(self, widget=None):
        current = self._current_row()
        if current is None:
            return
        self.doc.delete_row(current)
        self._rebuild_view(min(current, len(self.doc.rows) - 1))

    def _on_delete_empty_rows(self, widget=None):
        if not self.doc.delete_empty_rows():
            return
        self._rebuild_view()
        self._refresh_lint()

    def _on_rename_column(self, widget=None):
        index = self.active_column
        if not 0 <= index < len(self.doc.headers):
            return
        dialog = Gtk.Dialog(
            title="Rename column",
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            buttons=("_Cancel", Gtk.ResponseType.CANCEL, "_Rename", Gtk.ResponseType.ACCEPT),
        )
        entry = Gtk.Entry()
        entry.set_text(self.doc.headers[index])
        entry.set_activates_default(True)
        content = dialog.get_content_area()
        content.pack_start(entry, False, False, 8)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        content.show_all()
        response = dialog.run()
        value = entry.get_text()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            self.doc.set_header(index, value)
            self._rebuild_view()

    def _on_insert_left(self, widget=None):
        self.doc.insert_column(self.active_column)
        self._rebuild_view()

    def _on_insert_right(self, widget=None):
        self.doc.insert_column(self.active_column + 1)
        self.active_column += 1
        self._rebuild_view()

    def _on_delete_column(self, widget=None):
        self.doc.delete_column(self.active_column)
        self.active_column = min(self.active_column, len(self.doc.headers) - 1)
        self._rebuild_view()

    def _set_alignment(self, value):
        self.overrides[self.active_column] = value
        self._apply_alignment(self.active_column)

    def _on_align_left(self, widget=None):
        self._set_alignment("left")

    def _on_align_center(self, widget=None):
        self._set_alignment("center")

    def _on_align_right(self, widget=None):
        self._set_alignment("right")

    def _auto_size(self, index):
        values = [self.doc.headers[index] or "Column {}".format(index + 1)]
        values.extend(list(self.doc.column_values(index))[:200])
        self.column_objects[index].set_fixed_width(alignment.auto_width(self.tree, values))

    def _on_auto_size(self, widget=None):
        if self.active_column in self.column_objects:
            self._auto_size(self.active_column)

    def _on_auto_size_all(self, widget=None):
        for index in self.column_objects:
            self._auto_size(index)

    def _on_lint(self, widget=None):
        issues = self._refresh_lint()
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO if not issues else Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text="CSVLint",
        )
        if issues:
            body = "\n".join("Line {}: {}".format(issue.line, issue.message) for issue in issues[:40])
            if len(issues) > 40:
                body += "\n… and {} more".format(len(issues) - 40)
        else:
            body = "No issues found. Field counts and quoting are consistent."
        dialog.format_secondary_text(body)
        dialog.run()
        dialog.destroy()

    def _on_query(self, widget=None):
        dialog = Gtk.Dialog(
            title="Query CSV",
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            buttons=("_Cancel", Gtk.ResponseType.CANCEL, "_Run", Gtk.ResponseType.ACCEPT),
        )
        entry = Gtk.Entry()
        entry.set_text("SELECT *")
        entry.set_activates_default(True)
        hint = Gtk.Label(label="Example: SELECT a1, a2 WHERE a2 == 'x' ORDER BY a1 LIMIT 10")
        content = dialog.get_content_area()
        content.pack_start(entry, False, False, 6)
        content.pack_start(hint, False, False, 6)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        content.show_all()
        response = dialog.run()
        statement = entry.get_text()
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        try:
            headers, rows = query.run(self.doc, statement)
        except query.QueryError as error:
            self._show_error("Query error", str(error))
            return
        results = ResultsWindow(self.get_application(), headers, rows)
        results.present()

    def _on_group_by(self, widget=None):
        dialog = Gtk.Dialog(
            title="Group by columns",
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            buttons=("_Cancel", Gtk.ResponseType.CANCEL, "_Group", Gtk.ResponseType.ACCEPT),
        )
        content = dialog.get_content_area()
        hint = Gtk.Label(label="Select columns to group by:")
        hint.set_xalign(0.0)
        content.pack_start(hint, False, False, 4)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(180)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        checks = []
        for index, header in enumerate(self.doc.headers):
            check = Gtk.CheckButton(label=header or "Column {}".format(index + 1))
            check.set_active(index == self.active_column)
            box.pack_start(check, False, False, 0)
            checks.append(check)
        scrolled.add(box)
        content.pack_start(scrolled, True, True, 4)
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        content.show_all()
        response = dialog.run()
        indices = [index for index, check in enumerate(checks) if check.get_active()]
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return
        if not indices:
            self._show_error("Group By", "Select at least one column.")
            return
        try:
            order = group.group_indices(self.doc, indices)
        except ValueError as error:
            self._show_error("Group By", str(error))
            return
        self.doc.reorder_rows(order)
        self.doc.grouped = True
        self.doc.group_columns = [self.doc.headers[index] for index in indices]
        self._rebuild_view()
        self._refresh_lint()

    def _on_restore_order(self, widget=None):
        if not self.doc.grouped:
            return
        self.doc.restore_original_order()
        self._rebuild_view()
        self._refresh_lint()

    def _copy_to_clipboard(self, text):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()

    def _on_copy_tsv(self, widget=None):
        def escape(value):
            return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")

        lines = ["\t".join(escape(value) for value in self.doc.headers)]
        for row in self.doc.rows:
            lines.append("\t".join(escape(value) for value in row))
        self._copy_to_clipboard("\n".join(lines))

    def _on_copy_markdown(self, widget=None):
        def escape(value):
            return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")

        separator = "| " + " | ".join(["---"] * len(self.doc.headers)) + " |"
        lines = ["| " + " | ".join(escape(value) for value in self.doc.headers) + " |", separator]
        for row in self.doc.rows:
            lines.append("| " + " | ".join(escape(value) for value in row) + " |")
        self._copy_to_clipboard("\n".join(lines))

    def _on_about(self, widget=None):
        dialog = Gtk.AboutDialog()
        dialog.set_transient_for(self)
        dialog.set_program_name("CSV Grid Editor")
        dialog.set_version("1.4.1")
        dialog.set_comments("Rainbow CSV-style editing with aligned columns, line numbers, lint and queries.")
        dialog.set_authors(["Local User"])
        dialog.run()
        dialog.destroy()


class ResultsWindow(Gtk.ApplicationWindow):
    def __init__(self, application, headers, rows, title="Query results — CSV Grid Editor"):
        super().__init__(application=application, title=title)
        self.set_default_size(1000, 650)
        self.number_cell = None
        self.data_cells = {}
        self.header_labels = {}
        self.theme_handlers = theme.connect_settings(self._on_theme_changed)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.tree = Gtk.TreeView()
        self.tree.override_background_color(Gtk.StateFlags.NORMAL, theme.surface_color(self))
        self.tree.connect("cursor-changed", self._on_cursor_changed)
        store = Gtk.ListStore(*([str] * len(headers)))
        for row in rows:
            store.append(row)
        self.tree.set_model(store)
        dark = theme.is_dark(self)

        number_column = Gtk.TreeViewColumn(title="#")
        number_cell = Gtk.CellRendererText()
        number_cell.set_property("xalign", 1.0)
        number_cell.set_property("foreground-rgba", theme.line_number_color(dark))
        number_column.pack_start(number_cell, True)
        number_column.set_cell_data_func(number_cell, self._render_line_number)
        number_column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        number_column.set_fixed_width(56)
        number_column.set_resizable(False)
        self.tree.append_column(number_column)
        self.number_cell = number_cell

        for index, header in enumerate(headers):
            cell = Gtk.CellRendererText()
            cell.set_property("foreground-rgba", theme.column_color(index, dark))
            values = [header] + [row[index] for row in rows[:200]]
            column = Gtk.TreeViewColumn(title=header, cell_renderer=cell, text=index)
            column.set_cell_data_func(cell, self._render_cell_background)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(alignment.auto_width(self.tree, values))
            column.set_resizable(True)
            self.tree.append_column(column)
            label = column.get_widget()
            if label is not None:
                label.override_color(Gtk.StateFlags.NORMAL, theme.column_color(index, dark))
            self.data_cells[index] = cell
            self.header_labels[index] = label

        scrolled.add(self.tree)
        self.add(scrolled)
        self.connect("destroy", self._on_destroy)
        self.show_all()

    def _row_background(self, index):
        path, _ = self.tree.get_cursor()
        if path is not None and path.get_indices()[0] == index:
            return theme.selection_color(self)
        return theme.background_color(self, index)

    def _render_line_number(self, column, cell, model, tree_iter, data=None):
        index = model.get_path(tree_iter).get_indices()[0]
        cell.set_property("text", str(index + 1))
        cell.set_property("background-rgba", self._row_background(index))

    def _render_cell_background(self, column, cell, model, tree_iter, data=None):
        index = model.get_path(tree_iter).get_indices()[0]
        cell.set_property("background-rgba", self._row_background(index))

    def _on_cursor_changed(self, tree):
        tree.queue_draw()

    def apply_theme(self):
        dark = theme.is_dark(self)
        surface = theme.surface_color(self)
        self.override_background_color(Gtk.StateFlags.NORMAL, surface)
        self.tree.override_background_color(Gtk.StateFlags.NORMAL, surface)
        if self.number_cell is not None:
            self.number_cell.set_property("foreground-rgba", theme.line_number_color(dark))
        for index, cell in self.data_cells.items():
            cell.set_property("foreground-rgba", theme.column_color(index, dark))
        for index, label in self.header_labels.items():
            if label is not None:
                label.override_color(Gtk.StateFlags.NORMAL, theme.column_color(index, dark))
        self.tree.queue_draw()

    def _on_theme_changed(self, *args):
        if self.theme_handlers:
            theme.sync_system_settings()
            GLib.idle_add(self.apply_theme)

    def _on_destroy(self, widget=None):
        theme.disconnect_settings(self.theme_handlers)
        self.theme_handlers = []


class CsvGridApplication(Gtk.Application):
    def __init__(self):
        theme.sync_system_settings()
        super().__init__(
            application_id="org.local.csvgrideditor",
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = EditorWindow(self)
        self.window.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        if n_files:
            self.window.open_file(files[0].get_path())


def main():
    application = CsvGridApplication()
    return application.run(sys.argv)
