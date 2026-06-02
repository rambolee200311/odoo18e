/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * Outbound Flow Component
 *
 * 扫码流程：
 *  ─────────────────────────────────────────────────────────────────────
 *  整托出库: 步骤码(P) → 托盘条码 → [系统自动填充SN/批次/数量] → 完成
 *  拆托出库: 步骤码(D) → 托盘条码 → 产品条码 → [SN(多个) | 批次号] → 完成
 *  循环: → 托盘条码 → 产品条码 → [SN(多个) | 批次号] → ... → 完成
 *  ─────────────────────────────────────────────────────────────────────
 *  完成所有托盘后，确认出库
 */
export class OutboundFlow extends Component {
    static template = "stock_barcode_lite.OutboundPage";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            order: null,
            pallets: [],          // [{pallet_no, products:[{id,product_*,quantity,qty_done,sn_list:[],lot_id}], mode, is_complete}]
            currentPalletIndex: -1,
            currentItemIndex: -1, // 拆托模式下当前产品索引
            scanMode: "order",   // "order" | "step" | "pallet" | "product" | "qty" | "sn"
            message: "",
            messageType: "info",
            loading: false,
            totalScanned: 0,
            totalRequired: 0,
        });

        this.barcodeInputRef = useRef("barcodeInput");

        onMounted(() => {
            this._bindVisibilityChange();
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.addEventListener("input", this._onBarcodeInput.bind(this));
                barcodeInput.addEventListener("keydown", this._onBarcodeKeydown.bind(this));
                barcodeInput.focus();
            }
        });

        onWillUnmount(() => {
            this._unbindVisibilityChange();
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.removeEventListener("input", this._onBarcodeInput.bind(this));
                barcodeInput.removeEventListener("keydown", this._onBarcodeKeydown.bind(this));
            }
        });
    }

    _bindVisibilityChange() {
        this._onVisibilityChange = () => {
            if (document.visibilityState === "visible") {
                this._focusBarcodeInput();
            }
        };
        document.addEventListener("visibilitychange", this._onVisibilityChange);
    }

    _unbindVisibilityChange() {
        if (this._onVisibilityChange) {
            document.removeEventListener("visibilitychange", this._onVisibilityChange);
            this._onVisibilityChange = null;
        }
    }

    _focusBarcodeInput() {
        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
        }
    }

    _onBarcodeInput(ev) {
        const input = ev.target;
        const value = input.value;
        if (ev.inputType === "insertLineFeed" || value.includes("\n")) {
            const barcode = value.replace(/\n/g, "").replace(/\r/g, "").trim();
            if (barcode) {
                this.onBarcodeScanned(barcode);
            }
            input.value = "";
        }
    }

    _onBarcodeKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const input = ev.target;
            const barcode = input.value.trim();
            if (barcode) {
                this.onBarcodeScanned(barcode);
            }
            input.value = "";
            input.focus();
        }
    }

    async onBarcodeScanned(barcode) {
        if (!barcode || this.state.loading) return;
        this.state.loading = true;
        try {
            switch (this.state.scanMode) {
                case "order":    await this.scanOrder(barcode);    break;
                case "step":     await this.scanStep(barcode);     break;
                case "pallet":   await this.scanPallet(barcode);   break;
                case "product":  await this.scanProduct(barcode);  break;
                case "qty":      await this.scanQty(barcode);      break;
                case "sn":       await this.scanSN(barcode);       break;
            }
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
        } finally {
            this.state.loading = false;
        }
    }

    // ════════════════════════════════════════════
    // 阶段1: 扫出库单
    // ════════════════════════════════════════════
    async scanOrder(barcode) {
        const orders = await this.orm.searchRead(
            "world.depot.outbound.order",
            [["reference", "=", barcode]],
            ["id", "billno", "reference", "state"],
            { limit: 1 }
        );
        if (orders.length === 0) {
            throw new Error(_t("Outbound order not found: ") + barcode);
        }
        const order = orders[0];
        if (order.state === "confirm" || order.state === "cancel") {
            throw new Error(_t("Order state is ") + order.state + ", cannot scan");
        }
        this.state.order = order;
        await this.loadPallets(order.id);
        this.state.scanMode = "step";
        this.showMessage(
            _t("Loaded ") + order.reference + " (" + order.billno + ") — " + this.state.pallets.length + " pallet(s)",
            "success"
        );
        this.flashScreen();
    }

    async loadPallets(orderId) {
        // 读取托盘明细，serial_numbers 是已扫SN的逗号分隔文本
        const lines = await this.orm.searchRead(
            "world.depot.outbound.order.product",
            [["outbound_order_id", "=", orderId]],
            ["id", "product_id", "quantity", "serial_numbers", "pallet_no"],
            { limit: 2000 }
        );

        // 按托盘号分组
        const palletMap = new Map();
        for (const line of lines) {
            const pn = line.pallet_no || "";
            if (!palletMap.has(pn)) {
                palletMap.set(pn, {
                    pallet_no: pn,
                    products: [],
                    mode: null,
                    is_complete: false,
                });
            }
            // 解析已扫的 SN 列表
            const snList = line.serial_numbers
                ? line.serial_numbers.split(",").map(s => s.trim()).filter(Boolean)
                : [];
            palletMap.get(pn).products.push({
                id: line.id,
                product_id: line.product_id,
                product_name: line.product_id?.[1] || "Unknown",
                quantity: line.quantity || 0,
                qty_done: snList.length,  // 前端用 SN 数量作为已扫数量
                sn_list: snList,
                batch_count: 0,
            });
        }

        // 补全产品条码/EAN
        const productIds = [...new Set(lines.map(l => l.product_id?.[0]).filter(Boolean))];
        const products = productIds.length > 0
            ? await this.orm.read("product.product", productIds, ["id", "name", "barcode", "default_code"])
            : [];
        const productMap = new Map(products.map(p => [p.id, p]));

        for (const pallet of palletMap.values()) {
            for (const item of pallet.products) {
                const p = productMap.get(item.product_id?.[0]) || {};
                item.product_barcode = p.barcode || "";
                item.product_code = p.default_code || "";
                if (!item.product_name || item.product_name === "Unknown") {
                    item.product_name = p.name || "Unknown";
                }
            }
            pallet.total_qty = pallet.products.reduce((s, p) => s + p.quantity, 0);
        }

        this.state.pallets = Array.from(palletMap.values());
        this.state.totalRequired = this.state.pallets.reduce((s, p) => s + p.total_qty, 0);
        this._refreshTotals();
    }

    // ════════════════════════════════════════════
    // 阶段2: 扫步骤码
    // ════════════════════════════════════════════
    async scanStep(barcode) {
        const code = barcode.toUpperCase().trim();
        if (code !== "P" && code !== "D") {
            throw new Error(_t("Invalid step code. Use P (whole pallet) or D (disassembly)"));
        }
        const unhandled = this.state.pallets.filter(p => !p.is_complete);
        if (unhandled.length === 0) {
            throw new Error(_t("All pallets complete. Reset to start over."));
        }

        this.state._lastStepCode = code;
        this.state.scanMode = "pallet";

        const modeLabel = code === "P" ? _t("Whole Pallet") : _t("Disassembly");
        this.showMessage(
            _t("Mode: ") + modeLabel + " — scan pallet barcode",
            "info"
        );
        this.flashScreen();
    }

    // ════════════════════════════════════════════
    // 阶段3: 扫托盘
    // ════════════════════════════════════════════
    async scanPallet(barcode) {
        const pallet = this.state.pallets.find(p => p.pallet_no === barcode);
        if (!pallet) {
            throw new Error(_t("Pallet ") + barcode + " not found");
        }
        if (pallet.is_complete) {
            throw new Error(_t("Pallet ") + pallet.pallet_no + " already complete");
        }

        const index = this.state.pallets.indexOf(pallet);
        this.state.currentPalletIndex = index;
        this.state.currentItemIndex = -1;

        const lastCode = this.state._lastStepCode || "D";
        pallet.mode = lastCode === "P" ? "whole" : "disassembly";

        if (pallet.mode === "whole") {
            // ══ 整托模式：系统自动填充 → 完成 ══
            await this._handleWholePallet(pallet);
        } else {
            // ══ 拆托模式：等待扫产品 ══
            this.state.scanMode = "product";
            this.showMessage(
                _t("Pallet [") + pallet.pallet_no + "] — " + pallet.products.length + " product(s), scan product barcode",
                "success"
            );
            this.flashScreen();
        }
    }

    // ════════════════════════════════════════════
    // 整托处理：系统自动填充
    // ════════════════════════════════════════════
    async _handleWholePallet(pallet) {
        // 整托：qty_done 补到 quantity，SN/批次由系统处理
        for (const item of pallet.products) {
            item.qty_done = item.quantity;
            // SN 和 batch_count 留空，由后端自动填充批次/SN信息
            // 这里前端只标记状态，不额外填数据
        }
        pallet.is_complete = true;
        this._refreshTotals();

        this.showMessage(
            _t("Whole pallet [") + pallet.pallet_no + "] complete (auto-filled)",
            "success"
        );
        this.flashScreen([100, 200, 100], true);
        this._advanceToNextPallet();
    }

    // ════════════════════════════════════════════
    // 阶段4: 扫产品（拆托模式）
    // ════════════════════════════════════════════
    async scanProduct(barcode) {
        const pallet = this.state.pallets[this.state.currentPalletIndex];
        if (!pallet) return;

        const item = pallet.products.find(
            p => p.product_barcode === barcode || p.product_code === barcode
        );
        if (!item) {
            throw new Error(
                _t("Product ") + barcode + " not found in pallet [" + pallet.pallet_no + "]"
            );
        }

        // 如果已经扫过该产品，不再重复选入
        if (item.qty_done > 0 && item.qty_done >= item.quantity) {
            throw new Error(
                _t("Product ") + item.product_name + " already fully scanned"
            );
        }

        const itemIndex = pallet.products.indexOf(item);
        this.state.currentItemIndex = itemIndex;
        // 初始数量 +1
        item.qty_done = (item.qty_done || 0) + 1;
        item.batch_count = 0;
        item.sn_list = [];

        this._refreshTotals();
        this.showMessage(
            _t("") + item.product_name + " x" + item.qty_done + " — scan SN or scan repeatedly for qty",
            "success"
        );
        this.flashScreen();

        // 立刻进入 qty 模式（用于连续扫码计数量）
        this.state.scanMode = "qty";
    }

    // ════════════════════════════════════════════
    // 阶段5: 扫码计数 / SN / 批次号
    // ════════════════════════════════════════════

    /**
     * 扫码计数：同一产品多次扫码，累计数量
     * 如果扫到的是SN标签/批次码，则切换到SN模式
     */
    async scanQty(barcode) {
        const pallet = this.state.pallets[this.state.currentPalletIndex];
        if (!pallet) return;

        const item = pallet.products[this.state.currentItemIndex];
        if (!item) return;

        // 判断是SN还是计数扫码
        // SN特征：较长字符串、含字母数字混合等（非纯数字或短数字）
        const isSN = this._isLikelySN(barcode);

        if (isSN) {
            // 切换到 SN 模式处理
            this.state.scanMode = "sn";
            await this.scanSN(barcode);
            return;
        }

        // 纯计数扫码：+1
        const newQty = (item.qty_done || 0) + 1;
        if (newQty > item.quantity) {
            this.showMessage(
                _t("Warning: ") + item.product_name + " exceeds qty (" + newQty + "/" + item.quantity + ")",
                "danger"
            );
            this.flashScreen([200, 100, 200], true);
            // 不增加数量
        } else {
            item.qty_done = newQty;
            this._refreshTotals();
            this.showMessage(
            _t("") + item.product_name + " x" + newQty + " (" + newQty + "/" + item.quantity + ")",
                "success"
            );
            this.flashScreen();
        }

        // 检查是否完成该产品
        await this._tryFinishCurrentItem(pallet, item);
    }

    /**
     * SN 扫码（拆托模式）
     */
    async scanSN(barcode) {
        const pallet = this.state.pallets[this.state.currentPalletIndex];
        if (!pallet) return;

        const item = pallet.products[this.state.currentItemIndex];
        if (!item) return;

        if (item.sn_list.includes(barcode)) {
            throw new Error(_t("SN ") + barcode + " already scanned");
        }

        item.sn_list.push(barcode);
        // SN 扫一个，数量自动 +1
        item.qty_done = (item.qty_done || 0) + 1;
        this._refreshTotals();

        this.showMessage(
            _t("SN: ") + barcode + " -> " + item.product_name + " (" + item.sn_list.length + "/" + item.quantity + ")",
            "success"
        );
        this.flashScreen();

        // SN模式下，检查是否完成该产品
        await this._tryFinishCurrentItem(pallet, item);
    }

    /**
     * 判断扫码内容是否像 SN（而非纯计数数字）
     */
    _isLikelySN(barcode) {
        const trimmed = barcode.trim();
        // 纯数字且较短（≤4位）→ 认为是计数扫码
        if (/^\d{1,4}$/.test(trimmed)) return false;
        // 包含字母、或长度>4的数字串 → 认为是 SN/批次码
        return true;
    }

    /**
     * 尝试完成当前产品
     */
    async _tryFinishCurrentItem(pallet, item) {
        const isFull = (item.qty_done || 0) >= item.quantity;
        if (!isFull) return;

        // 产品数量已满，检查是否还有其他产品需要扫
        const remainingItems = pallet.products.filter(
            p => (p.qty_done || 0) < p.quantity
        );
        if (remainingItems.length === 0) {
            // 该托盘所有产品都完成
            pallet.is_complete = true;
            this.showMessage(
                _t("Pallet [") + pallet.pallet_no + "] complete!",
                "success"
            );
            this.flashScreen([100, 200, 100], true);
            this._advanceToNextPallet();
        } else {
            // 切到下一个产品
            const nextItem = remainingItems[0];
            this.state.currentItemIndex = pallet.products.indexOf(nextItem);
            this.state.scanMode = "product";
            this.showMessage(
                _t("Next product: ") + nextItem.product_name + " (" + remainingItems.length + "/" + pallet.products.length + " remaining)",
                "info"
            );
        }
    }

    // ════════════════════════════════════════════
    // 辅助方法
    // ════════════════════════════════════════════

    _refreshTotals() {
        this.state.totalScanned = this.state.pallets.reduce(
            (s, p) => s + p.products.reduce((ps, it) => ps + (it.qty_done || 0), 0), 0
        );
    }

    _advanceToNextPallet() {
        const nextIndex = this.state.pallets.findIndex(
            (p, i) => i > this.state.currentPalletIndex && !p.is_complete
        );
        if (nextIndex !== -1) {
            this.state.currentPalletIndex = nextIndex;
            this.state.currentItemIndex = -1;
            this.state.scanMode = "pallet";
            this.showMessage(
                _t("Next pallet [") + this.state.pallets[nextIndex].pallet_no + "] — scan barcode",
                "info"
            );
        } else {
            this.state.currentPalletIndex = -1;
            this.state.currentItemIndex = -1;
            this.state.scanMode = "step";
            this.state._lastStepCode = null;
            if (this.isAllComplete) {
                this.showMessage(_t("All pallets complete! Confirm outbound."), "success");
            }
        }
    }

    // ── 手动操作按钮 ─────────────────────────────

    /**
     * 标记当前托盘为整托（跳过产品扫码）
     */
    markCurrentPalletWhole() {
        const pallet = this.state.pallets[this.state.currentPalletIndex];
        if (!pallet || pallet.is_complete) return;
        pallet.mode = "whole";
        for (const item of pallet.products) {
            item.qty_done = item.quantity;
        }
        pallet.is_complete = true;
        this._refreshTotals();
        this.showMessage(_t("Pallet [") + pallet.pallet_no + "] marked whole (auto-filled)", "success");
        this.flashScreen();
        this._advanceToNextPallet();
    }

    /**
     * 跳过当前产品
     */
    skipCurrentItem() {
        const pallet = this.state.pallets[this.state.currentPalletIndex];
        if (!pallet) return;
        const remaining = pallet.products.filter(p => (p.qty_done || 0) < p.quantity);
        if (remaining.length === 0) {
            pallet.is_complete = true;
            this._refreshTotals();
            this.showMessage(_t("Pallet [") + pallet.pallet_no + "] complete!", "success");
            this.flashScreen();
            this._advanceToNextPallet();
            return;
        }
        const nextItem = remaining[0];
        this.state.currentItemIndex = pallet.products.indexOf(nextItem);
        this.state.scanMode = "product";
        this.showMessage(_t("Skipped — next: ") + nextItem.product_name, "warning");
    }

    /**
     * 跳过当前托盘
     */
    skipCurrentPallet() {
        this._advanceToNextPallet();
    }

    /**
     * 确认出库
     */
    async confirmOutbound() {
        if (!this.state.order) {
            this.showMessage(_t("No outbound order loaded"), "danger");
            return;
        }
        if (!this.isAllComplete) {
            const remaining = this.state.pallets
                .filter(p => !p.is_complete)
                .map(p => p.pallet_no)
                .join(", ");
            throw new Error(
                this.state.pallets.filter(p => !p.is_complete).length + " " +
                _t("pallet(s) incomplete: ") + (remaining || "—")
            );
        }
        this.state.loading = true;
        try {
            // 同步 SN 到后端 serial_numbers 字段
            for (const pallet of this.state.pallets) {
                for (const item of pallet.products) {
                    const snText = item.sn_list.join(", ");
                    await this.orm.write(
                        "world.depot.outbound.order.product",
                        [item.id],
                        { serial_numbers: snText }
                    );
                }
            }
            await this.orm.call(
                "world.depot.outbound.order",
                [this.state.order.id],
                "action_confirm"
            );
            this.showMessage(_t("Outbound confirmed!"), "success");
            this.flashScreen([100, 300, 100], true);
            setTimeout(() => this.resetScan(), 2000);
        } catch (error) {
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    resetScan() {
        this.state.order = null;
        this.state.pallets = [];
        this.state.currentPalletIndex = -1;
        this.state.currentItemIndex = -1;
        this.state.scanMode = "order";
        this.state.message = "";
        this.state.totalScanned = 0;
        this.state.totalRequired = 0;
        this.state._lastStepCode = null;
    }

    exit() {
        this.action.doAction("stock_barcode_lite_homepage");
    }

    showMessage(text, type = "info") {
        this.state.message = text;
        this.state.messageType = type;
        setTimeout(() => {
            if (this.state.message === text) {
                this.state.message = "";
            }
        }, 3500);
    }

    flashScreen(pattern, repeat) {
        if ("vibrate" in navigator) {
            navigator.vibrate(repeat ? pattern : 100);
        }
    }

    formatError(err) {
        return (
            err?.data?.arguments?.[0] ||
            (err?.data?.message
                ? err.data.message.replace(/^odoo\.exceptions\.[^:]+:\s*/, "")
                : "") ||
            err?.message ||
            _t("Unknown error")
        );
    }

    // ── 计算属性 ─────────────────────────────────

    get progressPercent() {
        if (!this.state.totalRequired) return 0;
        return Math.min(100, Math.round((this.state.totalScanned / this.state.totalRequired) * 100));
    }

    get isAllComplete() {
        return (
            this.state.pallets.length > 0 &&
            this.state.pallets.every(p => p.is_complete)
        );
    }

    get currentPallet() {
        if (this.state.currentPalletIndex < 0) return null;
        return this.state.pallets[this.state.currentPalletIndex] || null;
    }

    get currentItem() {
        const pallet = this.currentPallet;
        if (!pallet || this.state.currentItemIndex < 0) return null;
        return pallet.products[this.state.currentItemIndex] || null;
    }

    get scanModeLabel() {
        const map = {
            order:   "Scan Outbound Order",
            step:    "Scan Step Code (P / D)",
            pallet:  "Scan Pallet Barcode",
            product: "Scan Product Barcode",
            qty:     "Scan SN or Count (+1)",
            sn:      "Scan Serial Number",
        };
        return map[this.state.scanMode] || this.state.scanMode;
    }

    get stepHint() {
        if (this.state.scanMode === "step") {
            return "P = Whole Pallet (auto-fill)  |  D = Disassembly (scan product + SN/qty)";
        }
        return "";
    }
}
