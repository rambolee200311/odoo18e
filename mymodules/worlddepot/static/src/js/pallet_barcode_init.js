odoo.define('worlddepot.pallet_barcode_init', function(require) {
    "use strict";

    var $ = require('jquery');  // 明确引入jQuery
    var core = require('web.core');
    var PackageBarcode = require('stock_barcode.PackageBarcode');
    var PalletBarcode = require('worlddepot.pallet_barcode');

    // 覆盖原始组件
    PackageBarcode.include({
        init: function(parent, options) {
            this._super.apply(this, arguments);

            // 添加托盘扫描组件作为子组件
            this.palletBarcode = new PalletBarcode(this, options);
        },

        start: function() {
            var self = this;
            return this._super.apply(this, arguments).then(function() {
                return self.palletBarcode.appendTo(self.$el);
            });
        }
    });
});