// Stock Operation Portal - Product lookup
odoo.define('stock_operation_portal.product_lookup', function (require) {
    "use strict";

    var publicWidget = require('web.public.widget');

    publicWidget.registry.ProductLookup = publicWidget.Widget.extend({
        selector: '.product_lookup',
        events: {
            'input .product-code-input': '_onProductCodeInput',
            'click .product-item': '_onProductSelect',
        },

        init: function () {
            this._super.apply(this, arguments);
            this.searchTimeout = null;
        },

        start: function () {
            return this._super.apply(this, arguments);
        },

        _onProductCodeInput: function (ev) {
            var self = this;
            var code = $(ev.currentTarget).val();
            
            if (this.searchTimeout) {
                clearTimeout(this.searchTimeout);
            }

            if (code.length < 2) {
                this.$('.product-results').hide();
                return;
            }

            this.searchTimeout = setTimeout(function () {
                self._searchProduct(code);
            }, 300);
        },

        _searchProduct: function (code) {
            var self = this;
            this._rpc({
                route: '/stock_operation_portal/search_product',
                params: { code: code }
            }).then(function (result) {
                self._displayResults(result);
            });
        },

        _displayResults: function (results) {
            var $results = this.$('.product-results');
            if (results.length === 0) {
                $results.hide();
                return;
            }
            var html = '<ul class="list-group">';
            results.forEach(function (p) {
                html += '<li class="list-group-item product-item" data-id="' + p.id + '">' + p.name + '</li>';
            });
            html += '</ul>';
            $results.html(html).show();
        },

        _onProductSelect: function (ev) {
            var productId = $(ev.currentTarget).data('id');
            var productName = $(ev.currentTarget).text();
            this.$('.product-code-input').val(productName);
            this.$('.product-id-input').val(productId);
            this.$('.product-results').hide();
        },
    });

    return publicWidget.registry.ProductLookup;
});
