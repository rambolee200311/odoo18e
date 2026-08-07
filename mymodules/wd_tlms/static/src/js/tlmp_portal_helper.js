/** @odoo-module **/
import { rpc } from "@web/core/network/rpc";

export function call(model, method, args, kwargs) {
    kwargs = kwargs || {};
    return rpc('/web/dataset/call_kw', {
        model: model,
        method: method,
        args: args,
        kwargs: kwargs,
    });
}

export function searchRead(model, domain, fields) {
    return call(model, 'search_read', [domain, fields]);
}
