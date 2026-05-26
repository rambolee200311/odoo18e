// ========================================
// Marstek Stock Portal - 出库单卡片展开
// 功能：点击卡片展开时，通过 ORM 获取出库单详情
// ========================================
(function() {
    'use strict';

    // 出库单卡片折叠/展开
    window.marstekToggleOutboundCard = function(element) {
        var cardItem = element.closest('.stock-card-item');
        var details = element.nextElementSibling;
        var arrow = element.querySelector('.card-arrow');

        if (!details || !arrow || !cardItem) return;

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

            var outboundId = cardItem.getAttribute('data-outbound-id');
            if (outboundId && !details.hasAttribute('data-loaded')) {
                loadOutboundDetails(outboundId, details);
                details.setAttribute('data-loaded', 'true');
            }
        }
    };

    function loadOutboundDetails(outboundId, container) {
        container.innerHTML = '<div class="text-center py-3"><i class="fa fa-spinner fa-spin"></i> 加载中...</div>';

        var params = {
            model: 'world.depot.outbound.order',
            method: 'get_outbound_detail_grouped',
            args: [parseInt(outboundId)],
            kwargs: {}
        };

        fetch('/web/dataset/call_kw', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: params, id: Math.random()})
        }).then(function(response) {
            return response.json();
        }).then(function(data) {
            if (data.result) {
                renderOutboundDetails(data.result, container, outboundId);
            } else {
                container.innerHTML = '<div class="text-danger text-center py-3"><i class="fa fa-exclamation-triangle"></i> 获取数据失败</div>';
            }
        }).catch(function(err) {
            console.error('加载出库详情失败:', err);
            container.innerHTML = '<div class="text-danger text-center py-3"><i class="fa fa-exclamation-triangle"></i> 加载失败</div>';
        });
    }

    function renderOutboundDetails(result, container, outboundId) {
        var html = '';
        var items = result || [];

        if (items.length === 0) {
            html = '<div class="text-muted text-center py-3">暂无出库数据</div>';
        } else {
            items.forEach(function(item, index) {
                html += '<div class="pallet-section mb-2">';
                html += '<div class="fw-bold text-dark"><i class="fa fa-truck me-1"></i>出库单：' + escapeHtml(item.outbound_no || 'N/A') + ' <span class="text-success">(' + formatQuantity(item.total_quantity || 0) + ' 件)</span></div>';
                var products = item.products || [];
                products.forEach(function(p) {
                    html += '<div class="ms-3 text-muted small">';
                    html += '商品：' + escapeHtml(p.product_name || p.product_code || 'N/A');
                    html += ' <span class="text-success">数量：' + formatQuantity(p.quantity) + '</span>';
                    html += '</div>';
                });
                if (index < items.length - 1) {
                    html += '<hr class="my-2"/>';
                }
                html += '</div>';
            });

            html += '<div class="text-center mt-3 pt-2 border-top">';
            html += '<a href="/my/marstek/outbounds/' + outboundId + '" class="btn btn-sm btn-outline-primary">';
            html += '<i class="fa fa-external-link me-1"></i>查看详情</a>';
            html += '</div>';
        }
        container.innerHTML = html;
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatQuantity(qty) {
        if (!qty && qty !== 0) return '0';
        var num = parseFloat(qty);
        return isNaN(num) ? '0' : num.toLocaleString();
    }
})();
