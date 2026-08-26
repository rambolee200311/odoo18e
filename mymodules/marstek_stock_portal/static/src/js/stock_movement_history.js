(function () {
    'use strict';

    var BASE_URL = '/my/world_depot/stock/movement_history';
    var API_URL = BASE_URL;
    var SHELL_URL = BASE_URL + '_page';


    function init() {
        var form = document.getElementById('stock_history_form');
        if (!form) {
            return;
        }
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            var locationId = document.getElementById('location_id');
            var locationName = document.getElementById('location_search');
            var dateFrom = document.getElementById('date_from');
            var dateTo = document.getElementById('date_to');

            if (!locationId || !locationName || !dateFrom || !dateTo) {
                return;
            }
            var errors = [];
            if (!locationId.value.trim()) {
                errors.push('Please select a location.');
            }
            if (!dateFrom.value) {
                errors.push('Start date is required.');
            }
            if (!dateTo.value) {
                errors.push('End date is required.');
            }
            if (errors.length) {
                showError(errors.join(' '));
                return;
            }

            var params = new URLSearchParams();
            params.set('location_id', locationId.value.trim());
            if (locationName.value.trim()) {
                params.set('location_name', locationName.value.trim());
            }
            params.set('date_from', dateFrom.value);
            params.set('date_to', dateTo.value);
            params.set('page', '1');
            var viewMode = getQueryParam('view_mode');
            if (viewMode) {
                params.set('view_mode', viewMode);
            }
            window.location.href = SHELL_URL + '?' + params.toString();
        });

        restoreFilters();
        loadFromQuery();
    }

    function restoreFilters() {
        var locationName = document.getElementById('location_search');
        var locationId = document.getElementById('location_id');
        var dateFrom = document.getElementById('date_from');
        var dateTo = document.getElementById('date_to');
        if (!locationName || !locationId || !dateFrom || !dateTo) {
            return;
        }
        locationName.value = getQueryParam('location_name') || '';
        locationId.value = getQueryParam('location_id') || '';
        locationName.setAttribute('data-name', locationName.value);
        locationId.setAttribute('data-name', locationName.value);
        dateFrom.value = getQueryParam('date_from') || '';
        dateTo.value = getQueryParam('date_to') || '';
    }

    function loadFromQuery() {
        var locationId = getQueryParam('location_id');
        var dateFrom = getQueryParam('date_from');
        var dateTo = getQueryParam('date_to');
        if (!locationId || !dateFrom || !dateTo) {
            showEmpty();
            return;
        }
        loadData({
            location_id: locationId,
            date_from: dateFrom,
            date_to: dateTo,
            page: getQueryParam('page') || getPathPage() || '1',
        });
    }

    function loadData(filters) {
        setLoading(true);
        var params = new URLSearchParams();
        params.set('location_id', filters.location_id);
        params.set('date_from', filters.date_from);
        params.set('date_to', filters.date_to);
        params.set('page', filters.page || '1');

        fetch(API_URL + '?' + params.toString(), {
            credentials: 'same-origin',
            headers: {'Accept': 'application/json'},
        }).then(function (response) {
            return response.json().catch(function () {
                return {error: 'Invalid JSON response from the server.'};
            });
        }).then(function (data) {
            renderData(data);
            setLoading(false);
        }).catch(function (err) {
            console.error('Stock movement history load failed:', err);
            showError('Unable to load stock movement history.');
            clearData();
            setLoading(false);
        });
    }

    function renderData(data) {
        if (!data || data.error) {
            showError(data && data.error ? data.error : 'Unable to load stock movement history.');
            clearData();
            return;
        }
        hideError();
        var rows = data.rows || [];
        var pager = data.pager || {};
        renderSummary(data.summary || {});
        renderTable(rows);
        renderCards(rows);
        renderPager(pager);
        document.getElementById('stock_history_total').textContent = 'Total: ' + (pager.total || 0);
        showElement('stock_history_summary_card');
        toggleEmpty(rows.length === 0);
    }

    function renderSummary(summary) {
        var container = document.getElementById('stock_history_summary');
        if (!container) {
            return;
        }
        var fields = [
            ['opening_pallet_count', 'Opening Pallets'],
            ['opening_product_summary', 'Opening Products'],
            ['inbound_pallet_count', 'Inbound Pallets'],
            ['inbound_product_summary', 'Inbound Products'],
            ['outbound_pallet_count', 'Outbound Pallets'],
            ['outbound_product_summary', 'Outbound Products'],
            ['closing_pallet_count', 'Closing Pallets'],
            ['closing_product_summary', 'Closing Products'],
        ];
        container.innerHTML = fields.map(function (field) {
            var value = summary[field[0]];
            return '<div class="col-6 col-lg-3">'
                + '<div class="text-muted small fw-bold">' + escapeHtml(field[1]) + '</div>'
                + '<div class="fs-6">' + escapeHtml(value === undefined || value === null ? '0' : value) + '</div>'
                + '</div>';
        }).join('');
    }

    function renderTable(rows) {
        var tbody = document.getElementById('movement_history_tbody');
        if (!tbody) {
            return;
        }
        tbody.innerHTML = rows.map(function (row, index) {
            var title = row.row_type === 'loose' ? 'No Pallet' : row.package_name;
            var subtitle = row.row_type === 'loose' ? row.product_name : row.pallet_no;
            return '<tr class="movement-row" data-index="' + index + '" tabindex="0">'
                + '<td><i class="fa fa-chevron-right movement-arrow me-1"></i>'
                + '<div>' + escapeHtml(title || '') + '</div>'
                + (subtitle ? '<div class="text-muted small">' + escapeHtml(subtitle) + '</div>' : '')
                + '</td>'
                + '<td>' + escapeHtml(row.lot_summary || '') + '</td>'
                + '<td class="text-nowrap">' + escapeHtml(row.closing_location_name || '') + '</td>'
                + movementCell(row.opening_pallet_count, row.opening_product_summary)
                + movementCell(row.inbound_pallet_count, row.inbound_product_summary)
                + movementCell(row.outbound_pallet_count, row.outbound_product_summary)
                + movementCell(row.closing_pallet_count, row.closing_product_summary)
                + '<td class="text-end">' + escapeHtml(row.period_stock_days) + '</td>'
                + '<td class="text-end">' + escapeHtml(row.closing_age_days) + '</td>'
                + '<td class="text-nowrap">' + escapeHtml(row.lifecycle_start_datetime || '') + '</td>'
                + '</tr>'
                + '<tr class="movement-detail-row d-none" data-detail="' + index + '">'
                + '<td colspan="10">' + renderRowDetails(row) + '</td>'
                + '</tr>';
        }).join('');

        tbody.querySelectorAll('.movement-row').forEach(function (row) {
            row.addEventListener('click', function () {
                toggleRowDetail(row);
            });
            row.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    toggleRowDetail(row);
                }
            });
        });
    }

    function movementCell(count, summary) {
        return '<td>'
            + '<div class="text-nowrap">' + escapeHtml(formatNumber(count)) + '</div>'
            + (summary ? '<div class="text-muted small">' + escapeHtml(summary) + '</div>' : '')
            + '</td>';
    }

    function toggleRowDetail(row) {
        var index = row.getAttribute('data-index');
        var detail = document.querySelector('[data-detail="' + index + '"]');
        var arrow = row.querySelector('.movement-arrow');
        if (!detail || !arrow) {
            return;
        }
        var hidden = detail.classList.contains('d-none');
        detail.classList.toggle('d-none', !hidden);
        arrow.classList.toggle('fa-chevron-down', !hidden);
        arrow.classList.toggle('fa-chevron-up', hidden);
    }

    function renderRowDetails(row) {
        var html = '<div class="p-3">';
        html += '<div class="detail-grid">' + detailItem('Type', row.row_type) + detailItem('Pallet No.', row.pallet_no)
            + detailItem('Lot', row.lot_summary) + detailItem('Location', row.closing_location_name)
            + detailItem('Lifecycle State', row.lifecycle_state) + detailItem('First Inbound', row.lifecycle_start_datetime)
            + detailItem('Consumed', row.consumed_datetime) + detailItem('Period Stock Days', row.period_stock_days)
            + detailItem('Closing Age Days', row.closing_age_days) + detailItem('Inbound Orders', row.inbound_order_names)
            + detailItem('Outbound Orders', row.outbound_order_names) + detailItem('Inbound Pickings', row.inbound_picking_names)
            + detailItem('Outbound Pickings', row.outbound_picking_names) + detailItem('Picking State', row.picking_state_summary)
            + '</div>';
        html += renderStockLines(row.stock_line_ids || []);
        html += renderOperationLines(row.operation_line_ids || []);
        html += '</div>';
        return html;
    }

    function detailItem(label, value) {
        return '<div class="detail-item"><label>' + escapeHtml(label) + '</label><span>'
            + escapeHtml(value === undefined || value === null ? '' : value) + '</span></div>';
    }

    function renderStockLines(lines) {
        if (!lines.length) {
            return '';
        }
        var headers = ['Product Code', 'Product', 'Lot', 'UOM', 'Opening', 'Inbound', 'Outbound', 'On Hand', 'Reserved', 'Available', 'Closing Location', 'Reservation Note'];
        var body = lines.map(function (line) {
            return '<tr>'
                + '<td>' + escapeHtml(line.product_code || '') + '</td>'
                + '<td>' + escapeHtml(line.product_name || '') + '</td>'
                + '<td>' + escapeHtml(withId(line.lot_name, line.lot_id)) + '</td>'
                + '<td>' + escapeHtml(line.uom_name || '') + '</td>'
                + '<td class="text-end">' + formatNumber(line.opening_quantity) + '</td>'
                + '<td class="text-end">' + formatNumber(line.inbound_quantity) + '</td>'
                + '<td class="text-end">' + formatNumber(line.outbound_quantity) + '</td>'
                + '<td class="text-end">' + formatNumber(line.on_hand_quantity) + '</td>'
                + '<td class="text-end">' + formatNumber(line.reserved_quantity) + '</td>'
                + '<td class="text-end">' + formatNumber(line.available_quantity) + '</td>'
                + '<td>' + escapeHtml(line.closing_location_name || '') + '</td>'
                + '<td>' + escapeHtml(line.reservation_note || '') + '</td>'
                + '</tr>';
        }).join('');
        return '<h6 class="mt-3 fw-bold">Stock Lines</h6>'
            + '<div class="table-responsive">' + tableHtml(headers, body) + '</div>';
    }

    function renderOperationLines(lines) {
        if (!lines.length) {
            return '';
        }
        var headers = ['Direction', 'Inbound Order', 'Outbound Order', 'Picking', 'State', 'Product Code', 'Product', 'Lot', 'Planned', 'Reserved', 'Done', 'UOM', 'Operation Time', 'Source Location', 'Destination Location'];
        var body = lines.map(function (line) {
            return '<tr>'
                + '<td>' + escapeHtml(line.direction || '') + '</td>'
                + '<td>' + escapeHtml(withId(line.inbound_order_name, line.inbound_order_id)) + '</td>'
                + '<td>' + escapeHtml(withId(line.outbound_order_name, line.outbound_order_id)) + '</td>'
                + '<td>' + escapeHtml(withId(line.picking_name, line.picking_id)) + '</td>'
                + '<td>' + escapeHtml(line.picking_state || '') + '</td>'
                + '<td>' + escapeHtml(line.product_code || '') + '</td>'
                + '<td>' + escapeHtml(withId(line.product_name, line.product_id)) + '</td>'
                + '<td>' + escapeHtml(withId(line.lot_name, line.lot_id)) + '</td>'
                + '<td class="text-end">' + formatNumber(line.planned_quantity) + '</td>'
                + '<td class="text-end">' + formatNumber(line.reserved_quantity) + '</td>'
                + '<td class="text-end">' + formatNumber(line.done_quantity) + '</td>'
                + '<td>' + escapeHtml(line.uom_name || '') + '</td>'
                + '<td class="text-nowrap">' + escapeHtml(line.operation_datetime || '') + '</td>'
                + '<td>' + escapeHtml(line.source_location_name || '') + '</td>'
                + '<td>' + escapeHtml(line.destination_location_name || '') + '</td>'
                + '</tr>';
        }).join('');
        return '<h6 class="mt-3 fw-bold">Operation Lines</h6>'
            + '<div class="table-responsive">' + tableHtml(headers, body) + '</div>';
    }

    function tableHtml(headers, body) {
        return '<table class="table table-sm table-bordered mb-2">'
            + '<thead class="table-light"><tr>' + headers.map(function (header) {
                return '<th class="text-nowrap">' + escapeHtml(header) + '</th>';
            }).join('') + '</tr></thead>'
            + '<tbody>' + body + '</tbody></table>';
    }

    function renderCards(rows) {
        var container = document.getElementById('movement_history_cards');
        if (!container) {
            return;
        }
        container.innerHTML = rows.map(function (row) {
            var title = row.row_type === 'loose' ? 'No Pallet' : row.package_name;
            var subtitle = row.row_type === 'loose' ? row.product_name : row.pallet_no;
            return '<div class="stock-card-item mb-3">'
                + '<div class="card-item-header" onclick="window.marstekToggleCard(this)">'
                + '<div class="card-summary">'
                + '<span class="summary-item"><i class="fa fa-cubes me-1 text-primary"></i><strong>' + escapeHtml(title || '') + '</strong></span>'
                + (subtitle ? '<span class="summary-item"><i class="fa fa-cube me-1 text-info"></i>' + escapeHtml(subtitle) + '</span>' : '')
                + '<span class="summary-item"><i class="fa fa-map-marker me-1 text-muted"></i>' + escapeHtml(row.closing_location_name || '') + '</span>'
                + '<div class="summary-row">'
                + '<span class="summary-item"><i class="fa fa-sign-in me-1 text-success"></i>In: ' + escapeHtml(row.inbound_pallet_count || 0) + '</span>'
                + '<span class="summary-item"><i class="fa fa-sign-out me-1 text-danger"></i>Out: ' + escapeHtml(row.outbound_pallet_count || 0) + '</span>'
                + '<span class="summary-item"><i class="fa fa-box me-1 text-primary"></i>Closing: ' + escapeHtml(row.closing_pallet_count || 0) + '</span>'
                + '<span class="summary-item"><i class="fa fa-clock-o me-1 text-muted"></i>' + escapeHtml(row.period_stock_days || 0) + ' days</span>'
                + '</div>'
                + '</div>'
                + '<i class="card-arrow fa fa-chevron-down"></i>'
                + '</div>'
                + '<div class="card-item-details">' + renderRowDetails(row) + '</div>'
                + '</div>';
        }).join('');
    }

    function renderPager(pager) {
        var container = document.getElementById('stock_history_pager');
        if (!container) {
            return;
        }
        var pageCount = Number(pager.page_count || 1);
        if (pageCount <= 1) {
            container.innerHTML = '';
            return;
        }
        var current = Number(pager.page && pager.page.num || 1);
        var baseParams = new URLSearchParams(window.location.search);
        baseParams.delete('page');

        function pageHref(page) {
            var params = new URLSearchParams(baseParams.toString());
            params.set('page', String(page));
            return SHELL_URL + '?' + params.toString();
        }

        function pageItem(num, label, extraClass) {
            return '<li class="page-item ' + (extraClass || '') + '">'
                + '<a class="page-link" href="' + pageHref(num) + '">' + escapeHtml(label || num) + '</a></li>';
        }

        var html = '<nav aria-label="Stock history pages"><ul class="pagination pagination-sm justify-content-center mb-0">';
        html += '<li class="page-item ' + (current <= 1 ? 'disabled' : '') + '">'
            + '<a class="page-link" href="' + pageHref(Math.max(1, current - 1)) + '">Prev</a></li>';
        (pager.pages || []).forEach(function (page) {
            html += pageItem(page.num, page.num, page.num === current ? 'active' : '');
        });
        html += '<li class="page-item ' + (current >= pageCount ? 'disabled' : '') + '">'
            + '<a class="page-link" href="' + pageHref(Math.min(pageCount, current + 1)) + '">Next</a></li>';
        html += '</ul></nav>';
        container.innerHTML = html;
    }

    function toggleEmpty(empty) {
        showElement('movement_history_empty', empty);
        showElement('movement_history_card_empty', empty);
    }

    function showEmpty() {
        hideElement('stock_history_summary_card');
        clearData();
        toggleEmpty(true);
        document.getElementById('stock_history_total').textContent = 'Total: 0';
    }

    function clearData() {
        var tbody = document.getElementById('movement_history_tbody');
        var cards = document.getElementById('movement_history_cards');
        var pager = document.getElementById('stock_history_pager');
        if (tbody) tbody.innerHTML = '';
        if (cards) cards.innerHTML = '';
        if (pager) pager.innerHTML = '';
        hideElement('stock_history_summary_card');
        document.getElementById('stock_history_total').textContent = 'Total: 0';
    }

    function setLoading(loading) {
        showElement('stock_history_loading', loading);
    }

    function showError(message) {
        var alert = document.getElementById('stock_history_error');
        if (!alert) {
            return;
        }
        alert.textContent = message;
        alert.classList.remove('d-none');
    }

    function hideError() {
        var alert = document.getElementById('stock_history_error');
        if (alert) {
            alert.classList.add('d-none');
        }
    }

    function showElement(id, show) {
        var element = document.getElementById(id);
        if (!element) {
            return;
        }
        element.classList.toggle('d-none', show === false);
    }

    function hideElement(id) {
        showElement(id, false);
    }

    function getQueryParam(name) {
        return new URLSearchParams(window.location.search).get(name) || '';
    }

    function getPathPage() {
        var match = window.location.pathname.match(/\/page\/(\d+)$/);
        return match ? match[1] : '';
    }

    function formatNumber(value) {
        if (value === null || value === undefined || value === '') {
            return '';
        }
        var num = Number(value);
        if (!isFinite(num)) {
            return String(value);
        }
        return num.toLocaleString();
    }

    function withId(name, id) {
        if (!id) {
            return name || '';
        }
        return (name ? name + ' ' : '') + '(' + id + ')';
    }

    function escapeHtml(text) {
        if (text === null || text === undefined) {
            return '';
        }
        var div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
