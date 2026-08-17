// ========================================
// Marstek Stock Portal - 通用表格工具
// 功能：手机端列展开/收起、表头固定、表格/卡片视图切换
// ========================================
(function() {
    'use strict';

    // ========================================
    // 手机端表格展开/收起控制
    // ========================================
    function initMobileTableToggle() {
        var tableContainers = document.querySelectorAll('.table-responsive');

        tableContainers.forEach(function(container) {
            var table = container.querySelector('table');
            if (!table || table.classList.contains('no-mobile-toggle')) return;
            if (container.querySelector('.mobile-table-toggle')) return;

            if (!container.style.maxHeight && !container.classList.contains('table-scroll-fixed')) {
                container.style.maxHeight = '60vh';
                container.style.overflow = 'auto';
            }

            var allThs = table.querySelectorAll('thead th');
            var allRows = table.querySelectorAll('tbody tr');
            var colCount = allThs.length;
            var showColumns = 2;
            var isExpanded = false;

            for (var i = showColumns; i < colCount; i++) {
                if (allThs[i]) allThs[i].classList.add('col-hidden-mobile');
                allRows.forEach(function(row) {
                    var cells = row.querySelectorAll('td');
                    if (cells[i]) cells[i].classList.add('col-hidden-mobile');
                });
            }

            var toggleBtn = document.createElement('div');
            toggleBtn.className = 'd-md-none text-center py-2 bg-light border-bottom mobile-table-toggle';
            toggleBtn.innerHTML = '<button type="button" class="btn btn-sm btn-outline-primary">' +
                '<i class="fa fa-arrows-alt-h me-1"></i> 展开查看更多列</button>';

            container.insertBefore(toggleBtn, container.firstChild);

            toggleBtn.querySelector('button').addEventListener('click', function(e) {
                e.stopPropagation();
                isExpanded = !isExpanded;
                var btn = this;

                if (isExpanded) {
                    for (var i = 0; i < colCount; i++) {
                        if (allThs[i]) allThs[i].classList.remove('col-hidden-mobile');
                        allRows.forEach(function(row) {
                            var cells = row.querySelectorAll('td');
                            if (cells[i]) cells[i].classList.remove('col-hidden-mobile');
                        });
                    }
                    btn.innerHTML = '<i class="fa fa-times me-1"></i> 收起';
                    btn.classList.remove('btn-outline-primary');
                    btn.classList.add('btn-secondary');
                } else {
                    for (var i = showColumns; i < colCount; i++) {
                        if (allThs[i]) allThs[i].classList.add('col-hidden-mobile');
                        allRows.forEach(function(row) {
                            var cells = row.querySelectorAll('td');
                            if (cells[i]) cells[i].classList.add('col-hidden-mobile');
                        });
                    }
                    btn.innerHTML = '<i class="fa fa-arrows-alt-h me-1"></i> 展开查看更多列';
                    btn.classList.remove('btn-secondary');
                    btn.classList.add('btn-outline-primary');
                }
            });
        });
    }

    // ========================================
    // 表头固定样式（通用）
    // ========================================
    function initStickyHeaders() {
        document.querySelectorAll('.table-responsive').forEach(function(container) {
            var thead = container.querySelector('thead');
            if (thead && !thead.classList.contains('sticky-header-applied')) {
                thead.classList.add('sticky-header-applied');
            }
        });
    }

    // ========================================
    // 卡片折叠/展开功能（通用）
    // ========================================
    function initCardToggle() {
        // 全局卡片折叠函数，供 onclick 调用
        window.marstekToggleCard = function(element) {
            var details = element.nextElementSibling;
            var arrow = element.querySelector('.card-arrow');

            if (!details || !arrow) return;

            if (details.style.display === 'block') {
                details.style.display = 'none';
                arrow.classList.remove('fa-chevron-up');
                arrow.classList.add('fa-chevron-down');
                element.classList.remove('active');
            } else {
                details.style.display = 'block';
                arrow.classList.remove('fa-chevron-down');
                arrow.classList.add('fa-chevron-up');
                element.classList.add('active');
            }
        };
    }

    // ========================================
    // 视图切换功能（通用）
    // ========================================
    function initViewSwitch() {
        var tableView = document.getElementById('table_view');
        var cardView = document.getElementById('card_view');
        var viewTable = document.getElementById('view_table');
        var viewCard = document.getElementById('view_card');

        if (!tableView || !cardView || !viewTable || !viewCard) return;

        var urlParams = new URLSearchParams(window.location.search);

        // 更新分页链接
        function updatePagerLinks(viewMode) {
            // Odoo 分页链接选择器 - 覆盖所有可能的样式
            var selectors = [
                '.o_pager a',
                '.o_pager li a', 
                '.o_pager_value',
                '.pagination a',
                '.pager a',
                '.o_pager form a',
                'a[href*="/page/"]',
                '.pager li a'
            ];
            
            selectors.forEach(function(selector) {
                document.querySelectorAll(selector).forEach(function(link) {
                    var href = link.getAttribute('href');
                    if (!href) return;
                    
                    try {
                        var url = new URL(href, window.location.origin);
                        url.searchParams.set('view_mode', viewMode);
                        link.setAttribute('href', url.pathname + url.search);
                    } catch (e) {
                        // 如果 URL 解析失败，使用字符串操作
                        var newHref;
                        if (href.indexOf('view_mode=') !== -1) {
                            newHref = href.replace(/view_mode=[^&]*/, 'view_mode=' + viewMode);
                        } else {
                            var separator = href.indexOf('?') === -1 ? '?' : '&';
                            newHref = href + separator + 'view_mode=' + viewMode;
                        }
                        link.setAttribute('href', newHref);
                    }
                });
            });
        }

        // 从 URL 参数恢复视图状态
        var savedView = urlParams.get('view_mode');
        if (savedView === 'table') {
            // 表格视图（URL 明确指定了 table）
            viewTable.checked = true;
            tableView.style.display = 'block';
            cardView.style.display = 'none';
        } else {
            // 卡片视图（默认）- 包括 view_mode=card 或无 view_mode 参数
            viewCard.checked = true;
            tableView.style.display = 'none';
            cardView.style.display = 'block';
        }
        // 无论哪种情况，都更新分页链接
        updatePagerLinks(savedView === 'table' ? 'table' : 'card');

        // 切换事件
        viewTable.addEventListener('change', function() {
            if (this.checked) {
                tableView.style.display = 'block';
                cardView.style.display = 'none';
                urlParams.set('view_mode', 'table');
                history.replaceState(null, '', '?' + urlParams.toString());
                updatePagerLinks('table');
            }
        });

        viewCard.addEventListener('change', function() {
            if (this.checked) {
                tableView.style.display = 'none';
                cardView.style.display = 'block';
                urlParams.set('view_mode', 'card');
                history.replaceState(null, '', '?' + urlParams.toString());
                updatePagerLinks('card');
            }
        });
    }

    // ========================================
    // 分组切换功能（库存页：product / package）
    // ========================================
    function initGroupModeSwitch() {
        var groupProduct = document.getElementById('group_product');
        var groupPackage = document.getElementById('group_package');

        if (!groupProduct || !groupPackage) return;
        if (groupProduct.getAttribute('data-group-bound') || groupPackage.getAttribute('data-group-bound')) return;
        groupProduct.setAttribute('data-group-bound', '1');
        groupPackage.setAttribute('data-group-bound', '1');

        function navigateGroupMode(groupMode) {
            var urlParams = new URLSearchParams(window.location.search);
            var pathname = window.location.pathname.replace(/\/page\/\d+$/, '');
            urlParams.set('stock_group_mode', groupMode);
            window.location.href = pathname + '?' + urlParams.toString();
        }

        groupProduct.addEventListener('change', function() {
            if (this.checked) navigateGroupMode('product');
        });

        groupPackage.addEventListener('change', function() {
            if (this.checked) navigateGroupMode('package');
        });
    }

    // ========================================
    // 初始化
    // ========================================
    function init() {
        initMobileTableToggle();
        initStickyHeaders();
        initCardToggle();
        initViewSwitch();
        initGroupModeSwitch();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        setTimeout(init, 100);
        setTimeout(init, 500);
        setTimeout(init, 1000);
    }
})();
