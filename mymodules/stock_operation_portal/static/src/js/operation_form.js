// Stock Operation Portal - 表单处理
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.OperationForm = publicWidget.Widget.extend({
    selector: '.operation_form',
    events: {
        'click .add-line': '_onAddLine',
        'click .remove-line': '_onRemoveLine',
        'change .product-select': '_onProductChange',
    },

    init: function () {
        this._super.apply(this, arguments);
    },

    start: function () {
        return this._super.apply(this, arguments);
    },

    _onAddLine: function (ev) {
        var $table = $(ev.currentTarget).closest('table');
        var $row = $table.find('tbody tr').last();
        var $newRow = $row.clone();
        $newRow.find('input, select').val('');
        $table.find('tbody').append($newRow);
    },

    _onRemoveLine: function (ev) {
        var $row = $(ev.currentTarget).closest('tr');
        var $table = $row.closest('table');
        if ($table.find('tbody tr').length > 1) {
            $row.remove();
        }
    },

    _onProductChange: function (ev) {
        var productId = $(ev.currentTarget).val();
        // 通过 RPC 接口获取产品信息
    },
});

export default publicWidget.registry.OperationForm;