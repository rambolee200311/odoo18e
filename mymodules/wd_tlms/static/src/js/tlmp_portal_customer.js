/** @odoo-module **/
import { call } from "./tlmp_portal_helper";

const partnerId = odoo.session_info?.partner_id;

if (document.getElementById('tlmp_orders_page')) {
    call('tlmp.transport.order', 'search_read', [
        [['partner_id', 'child_of', partnerId]],
        ['name', 'state', 'carrier_id', 'planned_pickup_date'],
    ]).then(function (orders) {
        var tbody = document.querySelector('#tlmp_orders_table tbody');
        orders.forEach(function (o) {
            var tr = document.createElement('tr');
            tr.innerHTML = '<td>'+o.name+'</td><td>'+o.state+'</td>';
            tbody.appendChild(tr);
        });
    });
}

if (document.getElementById('tlmp_order_detail_page')) {
    var orderId = document.getElementById('tlmp_order_detail_page').dataset.orderId;
    call('tlmp.transport.order', 'read', [[orderId]])
        .then(function (orders) {
            if (orders.length) {
                var o = orders[0];
                document.getElementById('tlmp_order_name').textContent = o.name;
                document.getElementById('tlmp_order_state').textContent = o.state;
            }
        });
}

document.addEventListener('click', function (e) {
    if (e.target.classList.contains('tlmp_btn_accept_quote')) {
        var quoteId = e.target.dataset.quoteId;
        call('tlmp.transport.quote', 'action_accept_from_portal', [[quoteId]])
            .then(function () { location.reload(); })
            .catch(function (err) { alert(err.message); });
    }
    if (e.target.classList.contains('tlmp_btn_confirm_pod')) {
        var podId = e.target.dataset.podId;
        call('tlmp.pod', 'action_confirm', [[podId]])
            .then(function () { location.reload(); });
    }
});

document.addEventListener('change', function (e) {
    if (e.target.id === 'tlmp_transport_type') {
        var type = e.target.value;
        document.querySelectorAll('.tlmp_dg_field').forEach(function (el) {
            el.style.display = (type === 'port_to_warehouse' || type === 'to_customer') ? '' : 'none';
        });
    }
});
