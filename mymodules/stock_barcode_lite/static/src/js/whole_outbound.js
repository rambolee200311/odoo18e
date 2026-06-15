/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * Whole Pallet Outbound Flow
 *
 * 整托出库：
 * 扫码流程：
 *  ─────────────────────────────────────────────────────────────────────
 *  1. Order   : 扫出库单 picking name
 *  2. Location: 扫货位条码
 *  3. Pallet  : 逐个扫托盘条码 (stock.quant.package)
 *  ─────────────────────────────────────────────────────────────────────
 *  完成所有托盘后，可确认出库
 */
export class WholePalletOutboundPage extends Component {
    static template = "stock_barcode_lite.WholePalletOutboundPage";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            order: null,
            pallets: [],
            currentLocation: {},
            nextStep: "scan_order",  // 使用 nextStep 替代 scanMode，与入库流程一致
            message: "",
            messageType: "info",
            loading: false,
            summary: {
                total_pallets: 0,
                updated_pallets: 0,
                pending_pallets: 0,
            },
        });

        // 扫码输入缓冲
        this._scanBuffer = "";
        this._scanTimer = null;
        this._isProcessing = false;
        this._isPDA = this._detectPDA();

        this.barcodeInputRef = useRef("barcodeInput");

        onMounted(async () => {
            console.log('[WholePalletOutbound] onMounted');
            this._bindKeyListener();
            console.log('[WholePalletOutbound] onMounted complete');
        });

        onWillUnmount(() => {
            this._unbindKeyListener();
            this._clearScanTimer();
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // 设备检测
    // ═══════════════════════════════════════════════════════════════

    /**
     * 检测是否为PDA设备
     */
    _detectPDA() {
        const hasTouchScreen = (
            'ontouchstart' in window ||
            navigator.maxTouchPoints > 0 ||
            window.matchMedia('(pointer: coarse)').matches
        );
        const isDesktop = window.matchMedia('(min-width: 1024px)').matches && !hasTouchScreen;
        return !isDesktop;
    }

    // ═══════════════════════════════════════════════════════════════
    // 扫码监听（直接在 input 元素上绑定）
    // ═══════════════════════════════════════════════════════════════

    /**
     * 处理扫码输入框的 input 事件
     * 扫码枪会快速输入字符并以 Enter 结尾
     */
    _onBarcodeInput(ev) {
        const input = ev.target;
        if (!input) return;

        const value = input.value;
        console.log('[WholePalletOutbound] _onBarcodeInput triggered, value:', value, 'inputType:', ev.inputType);
        if (ev.inputType === "insertLineFeed" || value.includes("\n") || value.includes("\r")) {
            const barcode = value.replace(/\n/g, "").replace(/\r/g, "").trim();
            console.log('[WholePalletOutbound] Barcode detected (input event):', barcode);
            if (barcode) {
                input.value = "";
                this.onBarcodeScanned(barcode);
            }
        }
    }

    /**
     * 处理扫码输入框的 keydown 事件
     * 检测 Enter 键作为扫码确认
     */
    _onBarcodeKeydown(ev) {
        console.log('[WholePalletOutbound] _onBarcodeKeydown, key:', ev.key);
        if (ev.key === "Enter") {
            ev.preventDefault();
            const input = ev.target;
            const barcode = input.value.trim();
            console.log('[WholePalletOutbound] Enter pressed, barcode:', barcode);
            if (barcode) {
                input.value = "";
                this.onBarcodeScanned(barcode);
            }
        }
    }

    _onBarcodeBlur(ev) {
        console.log('[WholePalletOutbound] _onBarcodeBlur, _isProcessing:', this._isProcessing);
        // PDA模式下不自动聚焦，避免软键盘弹出
        if (!this._isProcessing && !this._isPDA) {
            console.log('[WholePalletOutbound] Setting timeout to refocus');
            setTimeout(() => this._focusBarcodeInput(), 0);
        }
    }

    _focusBarcodeInput() {
        console.log('[WholePalletOutbound] _focusBarcodeInput called');
        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
            console.log('[WholePalletOutbound] Input focused and cleared');
        } else {
            console.error('[WholePalletOutbound] Cannot focus - input not found');
        }
    }

    _bindKeyListener() {
        const input = this.barcodeInputRef.el;
        if (!input) return;

        input.addEventListener("input", this._onBarcodeInput.bind(this));
        input.addEventListener("keydown", this._onBarcodeKeydown.bind(this));
        input.addEventListener("blur", this._onBarcodeBlur.bind(this));

        if (!this._isPDA) {
            input.focus();
        }
    }

    _unbindKeyListener() {
        const input = this.barcodeInputRef.el;
        if (!input) return;

        input.removeEventListener("input", this._onBarcodeInput.bind(this));
        input.removeEventListener("keydown", this._onBarcodeKeydown.bind(this));
        input.removeEventListener("blur", this._onBarcodeBlur.bind(this));
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

    // ═══════════════════════════════════════════════════════════════
    // 扫码核心
    // ═══════════════════════════════════════════════════════════════

    async onBarcodeScanned(barcode) {
        console.log("╔═══════════════════════════════════════════════════════");
        console.log("║ [WholePalletOutbound] BARCODE SCANNED");
        console.log("║ ──────────────────────────────────────────────────────");
        console.log("║ Barcode:", barcode);
        console.log("║ Current Step:", this.state.nextStep);
        console.log("║ Is Processing:", this._isProcessing);
        console.log("╚═══════════════════════════════════════════════════════");
        
        if (!barcode || this._isProcessing) {
            console.log("[WholePalletOutbound] Skipped - no barcode or still processing");
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;

        try {
            switch (this.state.nextStep) {
                case "scan_order":
                    console.log("[WholePalletOutbound] → Step 1: Scanning ORDER...");
                    await this.scanOrder(barcode);
                    break;
                case "scan_location":
                    console.log("[WholePalletOutbound] → Step 2: Scanning LOCATION...");
                    await this.scanLocation(barcode);
                    break;
                case "scan_pallet":
                    console.log("[WholePalletOutbound] → Step 3: Scanning PALLET...");
                    await this.scanPallet(barcode);
                    break;
                default:
                    console.warn("[WholePalletOutbound] Unknown nextStep:", this.state.nextStep);
            }
        } catch (error) {
            console.error("╔═══════════════════════════════════════════════════════");
            console.error("║ [WholePalletOutbound] ERROR");
            console.error("║ ──────────────────────────────────────────────────────");
            console.error("║ Barcode:", barcode);
            console.error("║ Error:", error.message || error);
            console.error("╚═══════════════════════════════════════════════════════");
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._isProcessing = false;
            this._focusBarcodeInput();
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 阶段1: 扫出库单
    // ═══════════════════════════════════════════════════════════════

    async scanOrder(barcode) {
        console.log(">>> [WholePalletOutbound] scanOrder 扫到条码:", barcode);
        const pickings = await this.orm.searchRead(
            "stock.picking",
            [["name", "=", barcode]],
            ["id", "name", "state", "picking_type_id", "location_id", "location_dest_id", "origin"],
            { limit: 1 }
        );

        console.log("[WholePalletOutbound] scanOrder - Found pickings:", pickings);

        if (pickings.length === 0) {
            throw new Error(_t("Outbound order not found: ") + barcode);
        }

        const picking = pickings[0];

        if (picking.state === "done" || picking.state === "cancel") {
            throw new Error(_t("Order state is ") + picking.state + ", cannot scan");
        }

        // 如果是草稿状态，先确认出库单
        if (picking.state === "draft") {
            this.showMessage(_t("Confirming order..."), "info");
            try {
                await this.orm.call("stock.picking", [picking.id], "action_confirm");
                const updated = await this.orm.searchRead(
                    "stock.picking",
                    [["id", "=", picking.id]],
                    ["id", "name", "state"],
                    { limit: 1 }
                );
                if (updated.length > 0) {
                    this.state.order = updated[0];
                } else {
                    this.state.order = picking;
                }
            } catch (e) {
                console.warn("[WholePalletOutbound] 确认出库单失败:", e);
                this.state.order = picking;
            }
        } else {
            this.state.order = picking;
        }

        await this.loadPallets(this.state.order.id);

        this.state.nextStep = "scan_location";
        this.showMessage(
            _t("Loaded ") + this.state.order.name + " — " + this.state.pallets.length + _t(" pallet(s)"),
            "success"
        );
        this._flashScreen();
    }

    // ═══════════════════════════════════════════════════════════════
    // 阶段2: 扫货位
    // ═══════════════════════════════════════════════════════════════

    async scanLocation(barcode) {
        console.log("┌─────────────────────────────────────────────────────────");
        console.log("│ scanLocation() - Location scanned");
        console.log("│ Barcode:", barcode);
        console.log("└─────────────────────────────────────────────────────────");
        
        // 货位扫码后记录
        this.state.currentLocation = {
            name: barcode,
            barcode: barcode,
        };

        this.state.nextStep = "scan_pallet";
        console.log("[WholePalletOutbound] → Step changed to: scan_pallet");
        
        this.showMessage(
            _t("Location [") + barcode + "] — " + _t("scan pallet barcode"),
            "info"
        );
        this._flashScreen();
    }

    // ═══════════════════════════════════════════════════════════════
    // 阶段3: 扫托盘
    // ═══════════════════════════════════════════════════════════════

    async scanPallet(barcode) {
        console.log("┌─────────────────────────────────────────────────────────");
        console.log("│ scanPallet() - Pallet scanning");
        console.log("│ Barcode:", barcode);
        console.log("│ Current location:", this.state.currentLocation.name);
        console.log("└─────────────────────────────────────────────────────────");
        
        // 通过 package name / barcode 查找托盘
        let packages = await this.orm.searchRead(
            "stock.quant.package",
            [["name", "=", barcode]],
            ["id", "name", "barcode", "quant_ids"],
            { limit: 1 }
        );

        console.log("[WholePalletOutbound] scanPallet - Search by name result:", packages);

        // 如果没找到，尝试按 package barcode 查找
        if (packages.length === 0) {
            console.log("[WholePalletOutbound] scanPallet - Not found by name, trying barcode...");
            packages = await this.orm.searchRead(
                "stock.quant.package",
                [["barcode", "=", barcode]],
                ["id", "name", "barcode", "quant_ids"],
                { limit: 1 }
            );
            console.log("[WholePalletOutbound] scanPallet - Search by barcode result:", packages);
        }

        if (packages.length === 0) {
            throw new Error(_t("Pallet not found: ") + barcode);
        }

        const pkg = packages[0];
        console.log("[WholePalletOutbound] scanPallet - Found package:", pkg);

        // 检查该托盘是否在当前出库单关联的托盘列表中
        const pallet = this.state.pallets.find(p => p.id === pkg.id);
        if (!pallet) {
            console.log("[WholePalletOutbound] scanPallet - Pallet not in order list");
            throw new Error(
                _t("Pallet ") + pkg.name + _t(" is not part of the current outbound order")
            );
        }

        if (pallet.is_complete) {
            console.log("[WholePalletOutbound] scanPallet - Pallet already completed:", pkg.name);
            this.showMessage(
                _t("Pallet ") + pkg.name + _t(" already scanned"),
                "warning"
            );
            this._flashScreen([200, 200, 100], true);
            return;
        }

        // 标记完成
        pallet.is_complete = true;
        pallet.location_name = this.state.currentLocation.name;
        console.log("[WholePalletOutbound] scanPallet - Pallet marked as complete:", pkg.name);

        this._refreshSummary();

        const completed = this.state.summary.updated_pallets;
        const total = this.state.summary.total_pallets;
        console.log("[WholePalletOutbound] scanPallet - Progress:", completed + "/" + total);
        
        this.showMessage(
            _t("Pallet ") + pkg.name + _t(" scanned (") + completed + "/" + total + ")",
            "success"
        );
        this._flashScreen();

        // 继续循环：保持在托盘扫描状态，允许连续扫多个托盘
        if (!this.isAllComplete) {
            this.showMessage(_t("Scan next pallet"), "info");
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 数据加载
    // ═══════════════════════════════════════════════════════════════

    async loadPallets(pickingId) {
        this.state.loading = true;
        try {
            // 读取出库单关联的 stock.move.line
            const lines = await this.orm.searchRead(
                "stock.move.line",
                [
                    ["picking_id", "=", pickingId],
                    ["state", "not in", ["done", "cancel"]],
                ],
                ["id", "product_id", "quantity", "qty_done", "package_id", "location_id"],
                { limit: 2000 }
            );

            // 按 package_id 汇总
            const packageMap = new Map();
            for (const line of lines) {
                const pkgId = line.package_id?.[0];
                if (!pkgId) continue;

                if (!packageMap.has(pkgId)) {
                    packageMap.set(pkgId, {
                        id: pkgId,
                        name: line.package_id?.[1] || _t("Package #") + pkgId,
                        barcode: "",
                        is_complete: false,
                        location_name: "",
                        products: [],
                        total_qty: 0,
                    });
                }

                const pallet = packageMap.get(pkgId);
                pallet.products.push({
                    id: line.id,
                    product_id: line.product_id,
                    product_name: line.product_id?.[1] || "",
                    quantity: line.quantity || 0,
                    qty_done: line.qty_done || 0,
                });
                pallet.total_qty += line.quantity || 0;
            }

            // 补充 package 详情（name / barcode）
            const packageIds = [...packageMap.keys()];
            if (packageIds.length > 0) {
                const packages = await this.orm.read(
                    "stock.quant.package",
                    packageIds,
                    ["id", "name", "barcode"]
                );
                for (const pkg of packages) {
                    const pallet = packageMap.get(pkg.id);
                    if (pallet) {
                        pallet.name = pkg.name || pallet.name;
                        pallet.barcode = pkg.barcode || "";
                    }
                }
            }

            // 转换为数组并按 name 排序
            this.state.pallets = Array.from(packageMap.values()).sort((a, b) =>
                (a.name || "").localeCompare(b.name || "")
            );

            this._refreshSummary();
        } catch (error) {
            console.error("[WholePalletOutbound] loadPallets error:", error);
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    _refreshSummary() {
        const total = this.state.pallets.length;
        const updated = this.state.pallets.filter(p => p.is_complete).length;
        this.state.summary = {
            total_pallets: total,
            updated_pallets: updated,
            pending_pallets: total - updated,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // 确认出库
    // ═══════════════════════════════════════════════════════════════

    async confirmOutbound() {
        if (!this.state.order) {
            this.showMessage(_t("No order loaded"), "danger");
            return;
        }
        if (!this.isAllComplete) {
            this.showMessage(
                _t("There are still ") + this.state.summary.pending_pallets + _t(" pallet(s) not scanned"),
                "danger"
            );
            return;
        }

        this.state.loading = true;
        try {
            await this.orm.call("stock.picking", [this.state.order.id], "button_validate");
            this.showMessage(_t("Outbound confirmed successfully!"), "success");
            this._flashScreen([100, 300, 100], true);
            setTimeout(() => this.resetScan(), 2000);
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
        } finally {
            this.state.loading = false;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 重置 / 退出
    // ═══════════════════════════════════════════════════════════════

    resetScan() {
        this.state.order = null;
        this.state.pallets = [];
        this.state.currentLocation = {};
        this.state.nextStep = "scan_order";
        this.state.message = "";
        this.state.messageType = "info";
        this.state.loading = false;
        this.state.summary = {
            total_pallets: 0,
            updated_pallets: 0,
            pending_pallets: 0,
        };
        this._focusBarcodeInput();
    }

    exit() {
        this.action.doAction("stock_barcode_lite_homepage");
    }

    // ═══════════════════════════════════════════════════════════════
    // 辅助方法
    // ═══════════════════════════════════════════════════════════════

    showMessage(text, type = "info") {
        this.state.message = text;
        this.state.messageType = type;
        clearTimeout(this._messageTimer);
        this._messageTimer = setTimeout(() => {
            if (this.state.message === text) {
                this.state.message = "";
            }
        }, 4000);
    }

    _flashScreen(pattern, repeat) {
        if ("vibrate" in navigator) {
            navigator.vibrate(repeat ? pattern : 100);
        }
    }

    _clearScanTimer() {
        if (this._scanTimer) {
            clearTimeout(this._scanTimer);
            this._scanTimer = null;
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

    // ═══════════════════════════════════════════════════════════════
    // 计算属性（与模板对应）
    // ═══════════════════════════════════════════════════════════════

    // 是否已加载出库单
    get hasOrder() {
        return !!this.state.order;
    }

    // 是否已扫描货位
    get hasLocation() {
        return !!this.state.currentLocation?.name;
    }

    // 当前货位名称
    get currentLocationName() {
        return this.state.currentLocation?.name || "";
    }

    // 当前货位条码
    get currentLocationBarcode() {
        return this.state.currentLocation?.barcode || "";
    }

    // 是否在扫描出库单步骤
    get isScanOrderStep() {
        return this.state.nextStep === "scan_order";
    }

    // 是否在扫描货位步骤
    get isScanLocationStep() {
        return this.state.nextStep === "scan_location";
    }

    // 是否在扫描托盘步骤
    get isScanPalletStep() {
        return this.state.nextStep === "scan_pallet";
    }

    // 扫描模式标签
    get scanModeLabel() {
        const map = {
            scan_order: _t("Scan Order"),
            scan_location: _t("Scan Location"),
            scan_pallet: _t("Scan Pallet"),
        };
        return map[this.state.nextStep] || _t("Scan Barcode");
    }

    // 步骤提示
    get stepHint() {
        const hints = {
            scan_order: _t("Scan outbound order barcode to start"),
            scan_location: _t("Scan storage location barcode"),
            scan_pallet: _t("Scan pallet barcode to confirm"),
        };
        return hints[this.state.nextStep] || "";
    }

    // 进度百分比
    get progressPercent() {
        const s = this.state.summary || {};
        const total = s.total_pallets || 0;
        const done = s.updated_pallets || 0;
        if (!total) return 0;
        return Math.round((done / total) * 100);
    }

    // 是否全部完成
    get isAllComplete() {
        return (
            (this.state.summary?.pending_pallets || 0) === 0 &&
            (this.state.summary?.total_pallets || 0) > 0
        );
    }

    // 托盘列表
    get palletList() {
        return Array.isArray(this.state.pallets) ? this.state.pallets : [];
    }
}