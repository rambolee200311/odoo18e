// ========================================
// Marstek Stock Portal - 入库单卡片展开
// 功能：点击卡片展开时，通过 ORM 获取托盘详情
// ========================================
(function() {
    'use strict';

    window.marstekToggleInboundCard = function(element) {
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

            var inboundId = cardItem.getAttribute('data-inbound-id');
            if (inboundId && !details.hasAttribute('data-loaded')) {
                loadPalletDetails(inboundId, details);
                details.setAttribute('data-loaded', 'true');
            }
        }
    };

    function loadPalletDetails(inboundId, container) {
        container.innerHTML = '<div class="text-center py-3"><i class="fa fa-spinner fa-spin"></i> 加载中...</div>';

        var params = {
            model: 'world.depot.inbound.order',
            method: 'get_inbound_detail_grouped',
            args: [parseInt(inboundId)],
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
                renderPalletDetails(data.result, container, inboundId);
            } else {
                container.innerHTML = '<div class="text-danger text-center py-3"><i class="fa fa-exclamation-triangle"></i> 获取数据失败</div>';
            }
        }).catch(function(err) {
            console.error('加载托盘详情失败:', err);
            container.innerHTML = '<div class="text-danger text-center py-3"><i class="fa fa-exclamation-triangle"></i> 加载失败</div>';
        });
    }

    function renderPalletDetails(result, container, inboundId) {
        var html = '';
        var pallets = result || [];

        if (pallets.length === 0) {
            html = '<div class="text-muted text-center py-3">暂无托盘数据</div>';
        } else {
            pallets.forEach(function(pallet, index) {
                html += '<div class="pallet-section mb-2">';
                html += '<div class="fw-bold text-dark"><i class="fa fa-cube me-1"></i>托盘号：' + escapeHtml(pallet.package_name || 'N/A') + '</div>';
                var products = pallet.products || [];
                products.forEach(function(p) {
                    html += '<div class="ms-3 text-muted small">';
                    html += '商品：' + escapeHtml(p.product_name || p.product_code || 'N/A');
                    html += ' <span class="text-success">数量：' + formatQuantity(p.quantity) + '</span>';
                    html += '</div>';
                });
                if (index < pallets.length - 1) {
                    html += '<hr class="my-2"/>';
                }
                html += '</div>';
            });
            html += '<div class="text-center mt-3 pt-2 border-top">';
            html += '<a href="/my/marstek/inbounds/' + inboundId + '" class="btn btn-sm btn-outline-primary">';
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
