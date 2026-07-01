Column Reorder
==============

Overview
--------

``column_reorder_tspl`` adds drag-and-drop column reordering to Odoo backend
list views. Users can rearrange visible columns directly from the list header,
and the selected order is stored in the browser for that specific list view.

The module is designed for users who want a more flexible working layout in
tree views without modifying the underlying XML view definition.

Features
--------

- Drag and reorder labeled list-view columns from the backend UI.
- Preserve the selected column order in browser local storage.
- Keep saved order per list view using the Odoo view key.
- Apply the behavior to the standard web list renderer.
- Support account file-upload list views.
- Support sale onboarding list views.
- Leave Odoo sorting and column resizing behavior intact.

How It Works
------------

When a backend list view is opened:

- the module computes a unique key for the active list view
- any previously saved column order is loaded from browser local storage
- visible columns are reordered before the renderer displays them
- users can drag a column header using the handle icon
- the new order is stored immediately after the drop action

The saved order is filtered against the current set of available columns so the
view continues to work even if optional columns or view definitions change.

Technical Behavior
------------------

- The module patches ``@web/views/list/list_renderer``.
- Column order is stored with the prefix
  ``column_reorder_tspl.columns,`` in browser local storage.
- Reordering is enabled only on non-small screens.
- Reordering is disabled while a record is being edited.
- Only labeled field columns are draggable.
- The module extends the QWeb templates for ``web.ListRenderer``,
  ``account.FileUploadListRenderer``, and ``sale.SaleListRenderer`` to inject a
  drag handle into column headers.

Installation
------------

1. Place the module in your custom addons path.
2. Restart the Odoo server.
3. Update the Apps list.
4. Install the module ``Column Reorder``.
5. Open any backend list view with multiple labeled columns.

Usage
-----

1. Open a backend list view.
2. Hover over a column header.
3. Drag the handle icon shown next to the column label.
4. Drop the column in the desired position.
5. Refresh or revisit the view to see the order persist in the browser.

Files
-----

- ``static/src/js/list_renderer_patch.js``: patches the list renderer and
  stores column order in browser local storage
- ``static/src/xml/list_renderer.xml``: injects drag handles into list headers
- ``static/src/scss/list_renderer.scss``: styles the column drag handle
- ``__manifest__.py``: module metadata and backend asset registration

Version History
---------------

**18.0.1.0.0**

- Odoo 18 compatibility update
- Added list-view column drag-and-drop persistence
- Added header handle templates and styling for supported list renderers
