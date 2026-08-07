/** @odoo-module **/
import { call } from "./tlmp_portal_helper";

const partnerId = odoo.session_info?.partner_id;

if (document.getElementById('tlmp_inquiries_page')) {
    call('tlmp.transport.inquiry', 'search_read', [
        [['partner_id', '=', partnerId]],
        ['name', 'state', 'total_amount'],
    ]).then(function (inquiries) {
        var tbody = document.querySelector('#tlmp_inquiries_table tbody');
        inquiries.forEach(function (i) {
            var tr = document.createElement('tr');
            tr.innerHTML = '<td>'+i.name+'</td><td>'+i.state+'</td>';
            tbody.appendChild(tr);
        });
    });
}
