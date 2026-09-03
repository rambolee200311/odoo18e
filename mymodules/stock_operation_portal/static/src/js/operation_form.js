// Stock Operation Portal - Inbound Order Form Handler
import publicWidget from "@web/legacy/js/public/public_widget";

// ---- Collapsible section toggle (standalone, like marstek_inbound_card.js) ----
window.toggleSection = function(sectionId) {
    var content = document.getElementById(sectionId);
    if (!content) return;
    var icon = document.getElementById('icon_' + sectionId.replace('section_', ''));
    if (content.style.display === 'none') {
        content.style.display = 'block';
        if (icon) { icon.classList.remove('fa-chevron-right'); icon.classList.add('fa-chevron-down'); }
    } else {
        content.style.display = 'none';
        if (icon) { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-right'); }
    }
};

publicWidget.registry.InboundOrderForm = publicWidget.Widget.extend({
    selector: '#inbound_order_form',
    events: {
        'click .add-line': '_onAddPalletLine',
        'click .remove-line': '_onRemovePalletLine',
        'click .add-product': '_onAddProductLine',
        'click .remove-product': '_onRemoveProductLine',
        'submit': '_onFormSubmit',
    },

    start: function () {
        this._super.apply(this, arguments);
        this._productOptionsHtml = '';
        var $firstSelect = this.$('.pallet-line:first .product-select');
        if ($firstSelect.length) {
            this._productOptionsHtml = $firstSelect.html();
        }
    },

    // --------------------------------------------------------
    // Pallet line management
    // --------------------------------------------------------
    _onAddPalletLine: function (ev) {
        ev.preventDefault();
        var $container = this.$('#pallet_lines_container');
        this.$('#empty_lines_hint').hide();
        this._clearValidation();

        var idx = $container.find('.pallet-line').length + 1;
        var opts = this._productOptionsHtml || '<option value="">-- No products loaded --</option>';

        var html = '<div class="operation-line-item pallet-line" data-line-id="">'
            + '<div class="d-flex justify-content-between align-items-start mb-2">'
            + '<h6 class="mb-0">Pallet #' + idx + '</h6>'
            + '<button type="button" class="btn btn-sm btn-outline-danger remove-line"><i class="fa fa-trash"/></button>'
            + '</div>'
            + '<div class="row g-2 mb-2">'
            + '<div class="col-md-3"><label class="form-label">Pallet No</label><input type="text" class="form-control pallet_no" placeholder="e.g. PALLET-001"/></div>'
            + '<div class="col-md-2"><label class="form-label">Pallets <span class="text-danger">*</span></label><input type="number" class="form-control pallets" min="0.01" step="0.01" value="1"/></div>'
            + '<div class="col-md-2"><label class="form-label">Type</label><input type="text" class="form-control pallet_type" placeholder="e.g. WOOD"/></div>'
            + '<div class="col-md-5"><label class="form-label">Remark</label><input type="text" class="form-control line_remark"/></div>'
            + '</div>'
            + '<div class="ms-3">'
            + '<div class="d-flex justify-content-between align-items-center mb-1">'
            + '<small class="fw-bold text-muted">Products</small>'
            + '<button type="button" class="btn btn-sm btn-outline-success add-product"><i class="fa fa-plus"/> Add Product</button>'
            + '</div>'
            + '<table class="table table-sm table-bordered product-table mb-0">'
            + '<thead class="table-light"><tr><th style="min-width:200px">Product <span class="text-danger">*</span></th>'
            + '<th style="width:100px">Qty <span class="text-danger">*</span></th>'
            + '<th style="width:110px">Gross Wt (kg)</th><th style="width:110px">Net Wt (kg)</th>'
            + '<th>Remark</th><th style="width:40px"></th></tr></thead>'
            + '<tbody></tbody></table></div></div>';

        $container.append(html);
    },

    _onRemovePalletLine: function (ev) {
        ev.preventDefault();
        $(ev.currentTarget).closest('.pallet-line').remove();
        this._renumberPallets();
        if (!this.$('.pallet-line').length) {
            this.$('#empty_lines_hint').show();
        }
        this._clearValidation();
    },

    _renumberPallets: function () {
        this.$('.pallet-line').each(function (i) {
            $(this).find('h6').first().text('Pallet #' + (i + 1));
        });
    },

    // --------------------------------------------------------
    // Product line management
    // --------------------------------------------------------
    _onAddProductLine: function (ev) {
        ev.preventDefault();
        var $tbody = $(ev.currentTarget).closest('.ms-3').find('.product-table tbody');
        var opts = this._productOptionsHtml || '<option value="">-- No products --</option>';

        var html = '<tr class="product-line" data-product-line-id="">'
            + '<td><select class="form-select form-select-sm product-select" required="required"><option value="">-- Select --</option>' + opts + '</select></td>'
            + '<td><input type="number" class="form-control form-control-sm product-qty" min="0.01" step="0.01" value="1" required="required"/></td>'
            + '<td><input type="number" class="form-control form-control-sm product-gross" min="0" step="0.01" value="0"/></td>'
            + '<td><input type="number" class="form-control form-control-sm product-net" min="0" step="0.01" value="0"/></td>'
            + '<td><input type="text" class="form-control form-control-sm product-remark"/></td>'
            + '<td class="text-center"><button type="button" class="btn btn-sm btn-link text-danger remove-product"><i class="fa fa-times"/></button></td>'
            + '</tr>';
        $tbody.append(html);
        this._clearValidation();
    },

    _onRemoveProductLine: function (ev) {
        ev.preventDefault();
        $(ev.currentTarget).closest('.product-line').remove();
        this._clearValidation();
    },

    // --------------------------------------------------------
    // Validation helpers
    // --------------------------------------------------------
    _clearValidation: function () {
        this.$el.prev('.js-validation-error').remove();
    },

    _showErrors: function (errors) {
        this._clearValidation();
        var html = '<div class="alert alert-danger js-validation-error"><strong><i class="fa fa-exclamation-triangle me-1"/>Please fix the following:</strong><ul class="mb-0 mt-1">';
        errors.forEach(function (e) { html += '<li>' + e + '</li>'; });
        html += '</ul></div>';
        this.$el.before(html);
        this.$el.closest('.container').get(0).scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    // --------------------------------------------------------
    // Form submission -> JSON POST
    // --------------------------------------------------------
    _onFormSubmit: function (ev) {
        ev.preventDefault();
        var self = this;
        var $form = this.$el;

        var payload = {
            project_id: $form.find('[name="project_id"]').val() || '',
            reference: ($form.find('[name="reference"]').val() || '').trim(),
            date: $form.find('[name="date"]').val() || '',
            a_date: $form.find('[name="a_date"]').val() || '',
            bl_no: ($form.find('[name="bl_no"]').val() || '').trim(),
            cntr_no: ($form.find('[name="cntr_no"]').val() || '').trim(),
            is_adr: $form.find('[name="is_adr"]').is(':checked'),
            remark: ($form.find('[name="remark"]').val() || '').trim(),
            lines: [],
        };

        this.$('.pallet-line').each(function () {
            var $pallet = $(this);
            var lineId = $pallet.attr('data-line-id');
            var palletData = {
                pallet_no: ($pallet.find('.pallet_no').val() || '').trim(),
                pallets: parseFloat($pallet.find('.pallets').val()) || 1,
                pallet_type: ($pallet.find('.pallet_type').val() || '').trim(),
                remark: ($pallet.find('.line_remark').val() || '').trim(),
                products: [],
            };
            if (lineId) palletData.id = parseInt(lineId);

            $pallet.find('.product-line').each(function () {
                var $prod = $(this);
                var prodId = $prod.attr('data-product-line-id');
                var pd = {
                    product_id: parseInt($prod.find('.product-select').val()) || 0,
                    quantity: parseFloat($prod.find('.product-qty').val()) || 1,
                    gross_weight: parseFloat($prod.find('.product-gross').val()) || 0,
                    net_weight: parseFloat($prod.find('.product-net').val()) || 0,
                    remark: ($prod.find('.product-remark').val() || '').trim(),
                };
                if (prodId) pd.id = parseInt(prodId);
                palletData.products.push(pd);
            });
            payload.lines.push(palletData);
        });

        // ---- Frontend validation ----
        var errors = [];
        if (!payload.project_id) {
            errors.push('Please select a project.');
        }
        if (!payload.reference) {
            errors.push('Reference is required.');
        }
        if (!payload.date) {
            errors.push('Order date is required.');
        }
        if (!payload.a_date) {
            errors.push('Arrival date is required.');
        }
        if (payload.lines.length === 0) {
            errors.push('Please add at least one pallet line.');
        }
        payload.lines.forEach(function (line, i) {
            if (line.products.length === 0) {
                errors.push('Pallet #' + (i + 1) + ': must have at least one product.');
            }
            line.products.forEach(function (p, j) {
                if (!p.product_id) {
                    errors.push('Pallet #' + (i + 1) + ', Product #' + (j + 1) + ': please select a product.');
                }
                if (p.quantity <= 0) {
                    errors.push('Pallet #' + (i + 1) + ', Product #' + (j + 1) + ': quantity must be greater than 0.');
                }
            });
        });
        if (errors.length > 0) {
            self._showErrors(errors);
            return;
        }
        // ---- End validation ----

        var $btn = $form.find('#btn_submit_inbound');
        var origHtml = $btn.html();
        $btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin me-1"/> Saving...');

        fetch(window.location.href, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            redirect: 'follow',
        }).then(function (resp) {
            if (resp.redirected) {
                window.location.href = resp.url;
                return;
            }
            return resp.text().then(function (html) {
                document.open();
                document.write(html);
                document.close();
            });
        }).catch(function () {
            $btn.prop('disabled', false).html(origHtml);
            alert('An error occurred. Please try again.');
        });
    },
});

export default publicWidget.registry.InboundOrderForm;