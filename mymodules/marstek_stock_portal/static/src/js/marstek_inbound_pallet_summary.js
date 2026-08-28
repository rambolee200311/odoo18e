(function () {
    'use strict';

    var BASE_URL = '/my/world_depot/stock/inbound_pallet_summary';
    var SHELL_URL = BASE_URL + '_page';
    var currentView = 'table'; // 'table' or 'card'

    function init() {
        var form = document.getElementById('ips_form');
        if (!form) { return; }
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            var locationId = document.getElementById('ips_location_id');
            var locationName = document.getElementById('ips_location_search');
            var dateFrom = document.getElementById('ips_date_from');
            var dateTo = document.getElementById('ips_date_to');
            var cprojectid = document.getElementById('ips_cprojectid');
            if (!locationId || !locationName || !dateFrom || !dateTo) { return; }
            var errors = [];
            if (!locationId.value.trim()) { errors.push('Please select a location.'); }
            if (!dateFrom.value) { errors.push('Start date is required.'); }
            if (!dateTo.value) { errors.push('End date is required.'); }
            if (errors.length) { showError(errors.join(' ')); return; }
            var params = new URLSearchParams();
            params.set('location_id', locationId.value.trim());
            if (locationName.value.trim()) { params.set('location_name', locationName.value.trim()); }
            params.set('date_from', dateFrom.value);
            params.set('date_to', dateTo.value);
            if (cprojectid && cprojectid.value.trim()) { params.set('cprojectid', cprojectid.value.trim()); }
            params.set('page', '1');
            window.location.href = SHELL_URL + '?' + params.toString();
        });
        initLocationSearch();
        initViewToggle();
        restoreFilters();
        loadFromQuery();
    }

    // ===== View Toggle =====
    function initViewToggle() {
        var btnTable = document.getElementById('ips_view_table');
        var btnCard = document.getElementById('ips_view_card');
        if (btnTable) {
            btnTable.addEventListener('click', function () { switchView('table'); });
        }
        if (btnCard) {
            btnCard.addEventListener('click', function () { switchView('card'); });
        }
    }

    function switchView(view) {
        currentView = view;
        var tableEl = document.getElementById('ips_table');
        var cardsEl = document.getElementById('ips_cards');
        var btnTable = document.getElementById('ips_view_table');
        var btnCard = document.getElementById('ips_view_card');
        if (view === 'table') {
            if (tableEl) tableEl.classList.remove('d-none');
            if (cardsEl) cardsEl.classList.add('d-none');
            if (btnTable) { btnTable.classList.add('active'); btnTable.classList.remove('btn-outline-primary'); btnTable.classList.add('btn-primary'); }
            if (btnCard) { btnCard.classList.remove('active'); btnCard.classList.remove('btn-primary'); btnCard.classList.add('btn-outline-primary'); }
        } else {
            if (tableEl) tableEl.classList.add('d-none');
            if (cardsEl) cardsEl.classList.remove('d-none');
            if (btnTable) { btnTable.classList.remove('active'); btnTable.classList.remove('btn-primary'); btnTable.classList.add('btn-outline-primary'); }
            if (btnCard) { btnCard.classList.add('active'); btnCard.classList.remove('btn-outline-primary'); btnCard.classList.add('btn-primary'); }
        }
    }

    // ===== Location Search =====
    var locationTimer = null;

    function initLocationSearch() {
        var searchInput = document.getElementById('ips_location_search');
        var dropdown = document.getElementById('ips_location_dropdown');
        var hiddenInput = document.getElementById('ips_location_id');
        if (!searchInput || !dropdown || !hiddenInput) return;
        searchInput.addEventListener('input', function () {
            hiddenInput.value = '';
            var query = this.value.trim();
            clearTimeout(locationTimer);
            if (query.length < 1) { hiddenInput.value = ''; searchLocations(''); return; }
            locationTimer = setTimeout(function () { searchLocations(query); }, 300);
        });
        searchInput.addEventListener('focus', function () {
            var query = this.value.trim();
            if (!hiddenInput.value) {
                console.log('[IPS] calling searchLocations with:', query || '(empty)');
                searchLocations(query);
            }
        });
        document.addEventListener('click', function (e) {
            var wrapper = document.getElementById('ips_location_wrapper');
            if (wrapper && !wrapper.contains(e.target)) { hideDropdown(); }
        });
    }

    function searchLocations(query) {
        var loading = document.getElementById('ips_location_loading');
        if (loading) loading.style.display = 'block';
        var url = '/my/marstek/stock/location_options' + (query ? '?q=' + encodeURIComponent(query) : '');
        fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .then(function (response) { return response.json(); })
            .then(function (locations) {
                if (loading) loading.style.display = 'none';
                renderDropdown(locations, query);
            })
            .catch(function () { if (loading) loading.style.display = 'none'; });
    }

    function renderDropdown(locations, query) {
        var dropdown = document.getElementById('ips_location_dropdown');
        if (!dropdown) return;
        if (!locations || locations.length === 0) {
            dropdown.innerHTML = '<div class="dropdown-item-text text-muted">No results found</div>';
            showDropdown(); return;
        }
        var html = '';
        locations.forEach(function (loc) {
            html += '<a class="dropdown-item" href="#" data-id="' + loc.location_id + '" data-name="' + escapeHtml(loc.location_name) + '">';
            html += '<i class="fa fa-map-marker me-2 text-muted"></i>' + escapeHtml(loc.location_name || '');
            html += '</a>';
        });
        dropdown.innerHTML = html;
        showDropdown();
        dropdown.querySelectorAll('.dropdown-item').forEach(function (item) {
            item.addEventListener('click', function (e) { e.preventDefault(); selectLocation(this); });
        });
    }

    function selectLocation(item) {
        var searchInput = document.getElementById('ips_location_search');
        var hiddenInput = document.getElementById('ips_location_id');
        var id = item.getAttribute('data-id');
        var name = item.getAttribute('data-name');
        if (hiddenInput) hiddenInput.value = id;
        if (searchInput) { searchInput.value = name; searchInput.setAttribute('data-name', name); }
        hideDropdown();
    }

    // ===== Filter Restore =====
    function restoreFilters() {
        var locationName = document.getElementById('ips_location_search');
        var locationId = document.getElementById('ips_location_id');
        var dateFrom = document.getElementById('ips_date_from');
        var dateTo = document.getElementById('ips_date_to');
        var cprojectid = document.getElementById('ips_cprojectid');
        if (!locationName || !locationId || !dateFrom || !dateTo) return;
        locationName.value = getQueryParam('location_name') || '';
        locationId.value = getQueryParam('location_id') || '';
        locationName.setAttribute('data-name', locationName.value);
        locationId.setAttribute('data-name', locationName.value);
        dateFrom.value = getQueryParam('date_from') || '';
        dateTo.value = getQueryParam('date_to') || '';
        if (cprojectid) { cprojectid.value = getQueryParam('cprojectid') || ''; }
    }

    // ===== Data Loading =====
    function loadFromQuery() {
        var locationId = getQueryParam('location_id');
        var dateFrom = getQueryParam('date_from');
        var dateTo = getQueryParam('date_to');
        if (!locationId || !dateFrom || !dateTo) { showEmpty(); return; }
        loadData({
            location_id: locationId, date_from: dateFrom, date_to: dateTo,
            cprojectid: getQueryParam('cprojectid') || '',
            page: getQueryParam('page') || getPathPage() || '1',
        });
    }

    function loadData(filters) {
        setLoading(true);
        var params = new URLSearchParams();
        params.set('location_id', filters.location_id);
        params.set('date_from', filters.date_from);
        params.set('date_to', filters.date_to);
        if (filters.cprojectid) { params.set('cprojectid', filters.cprojectid); }
        params.set('page', filters.page || '1');
        fetch(BASE_URL + '?' + params.toString(), {
            credentials: 'same-origin', headers: { 'Accept': 'application/json' },
        }).then(function (response) {
            return response.json().catch(function () { return { error: 'Invalid JSON response from the server.' }; });
        }).then(function (data) {
            renderData(data); setLoading(false);
        }).catch(function (err) {
            console.error('Inbound pallet summary load failed:', err);
            showError('Unable to load inbound pallet summary.'); clearData(); setLoading(false);
        });
    }

    // ===== Data Rendering =====
    function renderData(data) {
        if (!data || data.error) {
            showError(data && data.error ? data.error : 'Unable to load inbound pallet summary.');
            clearData(); return;
        }
        hideError();
        var rows = data.rows || [];
        var pager = data.pager || {};
        renderSummary(data.summary || {});
        // Group rows
        var groups = groupRows(rows);
        renderTable(groups);
        renderCards(groups);
        renderPager(pager);
        document.getElementById('ips_total').textContent = 'Total: ' + (pager.total || rows.length);
        showElement('ips_summary_card');
        toggleEmpty(rows.length === 0);
        // Apply current view
        switchView(currentView);
    }

    function groupRows(rows) {
        var map = {};
        var order = [];
        rows.forEach(function (row) {
            var key = (row.inbound_order_name || '') + '|' + (row.cproject_ids || '');
            if (!map[key]) {
                map[key] = {
                    inbound_order_name: row.inbound_order_name || '',
                    cproject_ids: row.cproject_ids || '',
                    opening_pallet_count: 0,
                    inbound_pallet_count: 0,
                    outbound_pallet_count: 0,
                    closing_pallet_count: 0,
                    closing_location_summary: row.closing_location_summary || '',
                    remain_period_age_days: 0,
                    remain_total_age_days: 0,
                    outbound_lines: []
                };
                order.push(key);
            }
            map[key].opening_pallet_count += row.opening_pallet_count || 0;
            map[key].inbound_pallet_count += row.inbound_pallet_count || 0;
            map[key].outbound_pallet_count += row.outbound_pallet_count || 0;
            map[key].closing_pallet_count += row.closing_pallet_count || 0;
            map[key].remain_period_age_days = Math.max(map[key].remain_period_age_days, row.remain_period_age_days || 0);
            map[key].remain_total_age_days = Math.max(map[key].remain_total_age_days, row.remain_total_age_days || 0);
            if (row.outbound_lines && row.outbound_lines.length) {
                map[key].outbound_lines = map[key].outbound_lines.concat(row.outbound_lines);
            }
        });
        return order.map(function (key) { return map[key]; });
    }

    function renderSummary(summary) {
        var container = document.getElementById('ips_summary');
        if (!container) return;
        var fields = [
            ['opening_pallet_count', 'Opening Pallets', 'fa-arrow-down text-info'],
            ['outbound_pallet_count', 'Outbound Pallets', 'fa-arrow-up text-danger'],
            ['closing_pallet_count', 'Closing Pallets', 'fa-box text-primary'],
        ];
        container.innerHTML = fields.map(function (field) {
            var value = summary[field[0]];
            return '<div class="col-12 col-md-4">'
                + '<div class="d-flex align-items-center">'
                + '<i class="fa ' + field[2] + ' fa-2x me-3"></i>'
                + '<div><div class="text-muted small">' + field[1] + '</div>'
                + '<div class="fs-4 fw-bold">' + formatNumber(value) + '</div></div>'
                + '</div></div>';
        }).join('');
    }

    // ===== 表格视图 =====
    function renderTable(groups) {
        var tbody = document.getElementById('ips_tbody');
        var empty = document.getElementById('ips_empty');
        if (!tbody) return;
        if (!groups || groups.length === 0) {
            tbody.innerHTML = '';
            if (empty) empty.classList.remove('d-none');
            return;
        }
        if (empty) empty.classList.add('d-none');

        var html = '';
        var totalOpening = 0, totalInbound = 0, totalOutbound = 0, totalClosing = 0;

        groups.forEach(function (group) {
            totalOpening += group.opening_pallet_count;
            totalInbound += group.inbound_pallet_count;
            totalOutbound += group.outbound_pallet_count;
            totalClosing += group.closing_pallet_count;

            var outboundLines = group.outbound_lines || [];
            var rowSpan = outboundLines.length > 0 ? outboundLines.length : 1;

            if (outboundLines.length > 0) {
                // First outbound line gets the merged cells
                html += '<tr class="ips-row" data-inbound-order="' + escapeHtml(group.inbound_order_name) + '">'
                    + '<td rowspan="' + rowSpan + '">' + escapeHtml(group.inbound_order_name) + '</td>'
                    + '<td rowspan="' + rowSpan + '">' + escapeHtml(group.cproject_ids) + '</td>'
                    + '<td rowspan="' + rowSpan + '" class="text-end">' + formatNumber(group.opening_pallet_count) + '</td>'
                    + '<td rowspan="' + rowSpan + '" class="text-end">' + formatNumber(group.inbound_pallet_count) + '</td>'
                    + '<td rowspan="' + rowSpan + '" class="text-end">' + formatNumber(group.outbound_pallet_count) + '</td>'
                    + '<td rowspan="' + rowSpan + '" class="text-end">' + formatNumber(group.closing_pallet_count) + '</td>'
//                    + '<td rowspan="' + rowSpan + '">' + escapeHtml(group.closing_location_summary) + '</td>'
                    + '<td class="text-nowrap">' + escapeHtml(outboundLines[0].outbound_date) + '</td>'
                    + '<td>' + escapeHtml(outboundLines[0].cproject_ids) + '</td>'
                    + '<td>' + escapeHtml(outboundLines[0].batch_names) + '</td>'
                    + '<td class="text-end">' + formatNumber(outboundLines[0].pallet_count) + '</td>'
                    + '<td class="text-end">' + formatNumber(outboundLines[0].stock_days) + '</td>'
                    + '</tr>';
                // Remaining outbound lines
                for (var i = 1; i < outboundLines.length; i++) {
                    html += '<tr>'
                        + '<td class="text-nowrap">' + escapeHtml(outboundLines[i].outbound_date) + '</td>'
                        + '<td>' + escapeHtml(outboundLines[i].cproject_ids) + '</td>'
                        + '<td>' + escapeHtml(outboundLines[i].batch_names) + '</td>'
                        + '<td class="text-end">' + formatNumber(outboundLines[i].pallet_count) + '</td>'
                        + '<td class="text-end">' + formatNumber(outboundLines[i].stock_days) + '</td>'
                        + '</tr>';
                }
            } else {
                // No outbound lines
                html += '<tr class="ips-row" data-inbound-order="' + escapeHtml(group.inbound_order_name) + '">'
                    + '<td>' + escapeHtml(group.inbound_order_name) + '</td>'
                    + '<td>' + escapeHtml(group.cproject_ids) + '</td>'
                    + '<td class="text-end">' + formatNumber(group.opening_pallet_count) + '</td>'
                    + '<td class="text-end">' + formatNumber(group.inbound_pallet_count) + '</td>'
                    + '<td class="text-end">' + formatNumber(group.outbound_pallet_count) + '</td>'
                    + '<td class="text-end">' + formatNumber(group.closing_pallet_count) + '</td>'
//                    + '<td>' + escapeHtml(group.closing_location_summary) + '</td>'
                    + '<td class="text-center">-</td>'
                    + '<td class="text-center">-</td>'
                    + '<td class="text-center">-</td>'
                    + '<td class="text-end">-</td>'
                    + '<td class="text-end">-</td>'
                    + '</tr>';
            }
        });

        // 汇总行
        html += '<tr class="table-info fw-bold">'
            + '<td colspan="2" class="text-end">Summary</td>'
            + '<td class="text-end">' + formatNumber(totalOpening) + '</td>'
            + '<td class="text-end">' + formatNumber(totalInbound) + '</td>'
            + '<td class="text-end">' + formatNumber(totalOutbound) + '</td>'
            + '<td class="text-end">' + formatNumber(totalClosing) + '</td>'
            + '<td></td>'
            + '<td></td>'
            + '<td></td>'
            + '<td></td>'
            + '<td></td>'
            + '</tr>';

        tbody.innerHTML = html;
    }

    // ===== 卡片视图 =====
    function renderCards(groups) {
        var container = document.getElementById('ips_cards');
        if (!container) return;
        if (!groups || groups.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-5">No data found</div>';
            return;
        }
        var html = '';
        groups.forEach(function (group) {
            var outboundLines = group.outbound_lines || [];
            var detailId = 'ips_detail_' + group.inbound_order_name.replace(/[^a-zA-Z0-9]/g, '_');
            html += '<div class="card mb-3">'
                + '<div class="card-body">'
                + '<div class="d-flex justify-content-between align-items-start mb-2">'
                + '<h6 class="mb-0">' + escapeHtml(group.inbound_order_name) + '</h6>';
            if (outboundLines.length > 0) {
                html += '<button class="btn btn-sm btn-outline-primary ips-toggle-detail" data-target="' + detailId + '">'
                    + '<i class="fa fa-chevron-down me-1"></i>Outbound (' + outboundLines.length + ')'
                    + '</button>';
            }
            html += '</div>'
                + '<div class="row g-2 mb-2">'
                + '<div class="col-6 col-md-3"><span class="text-muted small">Project IDs:</span><br/>' + escapeHtml(group.cproject_ids || '-') + '</div>'
                + '<div class="col-6 col-md-3"><span class="text-muted small">Opening:</span><br/><strong>' + formatNumber(group.opening_pallet_count) + '</strong></div>'
                + '<div class="col-6 col-md-3"><span class="text-muted small">Inbound:</span><br/><strong>' + formatNumber(group.inbound_pallet_count) + '</strong></div>'
                + '<div class="col-6 col-md-3"><span class="text-muted small">Outbound:</span><br/><strong>' + formatNumber(group.outbound_pallet_count) + '</strong></div>'
                + '<div class="col-6 col-md-3"><span class="text-muted small">Closing:</span><br/><strong>' + formatNumber(group.closing_pallet_count) + '</strong></div>'
//                + '<div class="col-6 col-md-3"><span class="text-muted small">Location:</span><br/>' + escapeHtml(group.closing_location_summary || '-') + '</div>'
                + '</div>';
            if (outboundLines.length > 0) {
                html += '<div id="' + detailId + '" class="collapse mt-2">'
                    + '<table class="table table-sm table-bordered mb-0">'
                    + '<thead class="table-light"><tr>'
                    + '<th>Outbound Date</th><th>Sunrise Ref</th><th>Batch No</th><th class="text-end">Pallet Count</th><th class="text-end">Stock Days</th>'
                    + '</tr></thead><tbody>';
                outboundLines.forEach(function (line) {
                    html += '<tr>'
                        + '<td>' + escapeHtml(line.outbound_date) + '</td>'
                        + '<td>' + escapeHtml(line.cproject_ids) + '</td>'
                        + '<td>' + escapeHtml(line.batch_names) + '</td>'
                        + '<td class="text-end">' + formatNumber(line.pallet_count) + '</td>'
                        + '<td class="text-end">' + formatNumber(line.stock_days) + '</td>'
                        + '</tr>';
                });
                html += '</tbody></table></div>';
            }
            html += '</div></div>';
        });
        container.innerHTML = html;
        // 绑定切换详情按钮
        container.querySelectorAll('.ips-toggle-detail').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var targetId = this.getAttribute('data-target');
                var detailEl = document.getElementById(targetId);
                if (!detailEl) return;
                var isOpen = detailEl.classList.toggle('show');
                var icon = this.querySelector('i');
                if (icon) {
                    icon.classList.toggle('fa-chevron-down', !isOpen);
                    icon.classList.toggle('fa-chevron-up', isOpen);
                }
            });
        });
    }

    // ===== 页码 =====
    function renderPager(pager) {
        var container = document.getElementById('ips_pager');
        if (!container) return;
        var pageCount = pager.page_count || 1;
        var current = pager.page && pager.page.num || 1;
        if (pageCount <= 1) { container.innerHTML = ''; return; }

        function pageHref(page) {
            return SHELL_URL + '?' + new URLSearchParams({
                location_id: getParam('location_id'),
                location_name: getParam('location_name'),
                date_from: getParam('date_from'),
                date_to: getParam('date_to'),
                cprojectid: getParam('cprojectid'),
                page: page
            }).toString();
        }

        var html = '<nav><ul class="pagination justify-content-center mb-0">';
        html += '<li class="page-item ' + (current <= 1 ? 'disabled' : '') + '"><a class="page-link" href="' + pageHref(current - 1) + '">Prev</a></li>';
        for (var i = 1; i <= pageCount; i++) {
            html += '<li class="page-item ' + (i === current ? 'active' : '') + '"><a class="page-link" href="' + pageHref(i) + '">' + i + '</a></li>';
        }
        html += '<li class="page-item ' + (current >= pageCount ? 'disabled' : '') + '"><a class="page-link" href="' + pageHref(current + 1) + '">Next</a></li>';
        html += '</ul></nav>';
        container.innerHTML = html;
    }

    // ===== Helpers =====
    function setLoading(loading) {
        var el = document.getElementById('ips_loading');
        if (el) { el.classList.toggle('d-none', !loading); }
    }

    function showEmpty() {
        hideElement('ips_summary_card');
        toggleEmpty(true);
    }

    function clearData() {
        var tbody = document.getElementById('ips_tbody');
        if (tbody) tbody.innerHTML = '';
        var cards = document.getElementById('ips_cards');
        if (cards) cards.innerHTML = '';
        hideElement('ips_summary_card');
        document.getElementById('ips_total').textContent = 'Total: 0';
    }

    function getPathPage() {
        var match = window.location.pathname.match(/\/page\/(\d+)/);
        return match ? match[1] : '';
    }

    function showError(message) {
        var el = document.getElementById('ips_error');
        if (el) { el.textContent = message; el.classList.remove('d-none'); }
    }

    function hideError() {
        var el = document.getElementById('ips_error');
        if (el) el.classList.add('d-none');
    }

    function showElement(id) {
        var el = document.getElementById(id);
        if (el) el.classList.remove('d-none');
    }

    function hideElement(id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('d-none');
    }

    function toggleEmpty(isEmpty) {
        var el = document.getElementById('ips_empty');
        if (el) el.classList.toggle('d-none', !isEmpty);
    }

    function getQueryParam(name) { return getParam(name); }

    function getParam(name) {
        return new URLSearchParams(window.location.search).get(name) || '';
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    function formatNumber(value) {
        if (value === null || value === undefined) return '0';
        return Number(value).toLocaleString();
    }

    function showDropdown() { var d = document.getElementById('ips_location_dropdown'); if (d) d.style.display = 'block'; }
    function hideDropdown() { var d = document.getElementById('ips_location_dropdown'); if (d) d.style.display = 'none'; }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();