/** @odoo-module **/

import { _t } from '@web/core/l10n/translation';
import { rpc } from '@web/core/network/rpc';
import { registry } from '@web/core/registry';
//import { MainComponent } from 'stock_barcode/static/src/components/main';
import { Component, EventBus, onPatched, onWillStart, onWillUnmount, useState, useSubEnv } from "@odoo/owl";
import MainComponent from '@stock_barcode/components/main';
import { scanBarcode } from '@web/core/barcode/barcode_dialog';

class PalletScanClientAction extends MainComponent {
    setup() {
        super.setup();
        // 覆盖原有方法
        this._overridePutInPack();
    }

    _overridePutInPack() {
        // 保存原有方法引用
        const originalPutInPack = this.env.model._putInPack;
        // 覆盖方法
        this.env.model._putInPack = async () => {
            try {
                // 1. 先阻止默认行为
                await this._handlePalletScan();
                // 2. 不调用原始方法 - 完全接管流程
            } catch (error) {
                this.notification.add(_t('操作失败: ') + error.message, { type: 'danger' });
            }
        };
    }

    async _handlePalletScan() {
        const barcode = await scanBarcode(this.env, {
            title: _t("托盘扫描"),
            placeholder: _t("请扫描托盘条码...")
        });

        if (barcode) {
            await this.updatePallet(barcode);
        } else {
            this.notification.add(_t('未检测到条码'), { type: 'warning' });
        }
    }

    async updatePallet(barcode) {
        try {
            const result = await rpc({
                route: '/stock_barcode/update_pallet',
                params: { pallet_barcode: barcode,
                        res_id: this.env.model.context.active_id },
            });

            if (result.status === 'success') {
                this.notification.add(_t('托盘更新成功'), {
                    type: 'success',
                    sticky: false
                });
                // 更新前端显示
                this.env.model.notify();
            } else {
                throw new Error(result.message || _t("未知错误"));
            }
        } catch (error) {
            this.notification.add(_t('更新失败: ') + error.message, {
                type: 'danger',
                sticky: true
            });
        }
    }
}
/*
class PalletScanClientAction extends MainComponent {
    setup() {
        super.setup();
        this.onClickPutInPack = this.onClickPutInPack.bind(this);
    }

    start() {
        super.start();
        this.el.addEventListener('click', this.onClickPutInPack);
    }

    async onClickPutInPack(event) {
        if (event.target.classList.contains('o_put_in_pack')) {
            event.preventDefault();
            try {
                await this.env.model._putInPack();
                const barcode = await scanBarcode(this.env);
                if (barcode) {
                    this.updatePallet(barcode);
                } else {
                    this.notification.add(_t('No barcode detected.'), { type: 'danger' });
                }
            } catch (error) {
                this.notification.add(_t('Failed to put in pack: ') + error.message, { type: 'danger' });
            }
        }
    }

    updatePallet(barcode) {
        rpc({
            route: '/stock_barcode/update_pallet',
            params: { pallet_barcode: barcode },
        }).then((result) => {
            if (result.status === 'success') {
                this.notification.add(_t('Pallet updated successfully.'), { type: 'success' });
            } else {
                this.notification.add(_t('Failed to update pallet: ') + result.message, { type: 'danger' });
            }
        }).catch((error) => {
            this.notification.add(_t('Error: ') + error.message, { type: 'danger' });
        });
    }
}
*/
registry.category('actions').add('worlddepot.pallet_scan', PalletScanClientAction);