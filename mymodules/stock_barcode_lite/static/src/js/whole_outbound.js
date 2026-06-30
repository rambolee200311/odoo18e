/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * Whole Pallet Outbound Flow (Backend-driven)
 *
 * 整托出库：
 * 扫码流程：
 *  ─────────────────────────────────────────────────────────────────────
 *  1. Order   : 扫出库单 picking name
 *  2. Location: 扫货位条码
 *  3. Pallet  : 逐个扫托盘条码 (stock.quant.package)
 *  ─────────────────────────────────────────────────────────────────────
 *  完成所有托盘后，可确认出库
 *
 * 本页面完全依赖后端接口 process_outgoing_scan_barcode 驱动流程，
 * 后端返回统一的 scan_state 结构，前端负责渲染和交互。
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
            currentPallet: {},
            currentProduct: {},
            currentLot: {},
            nextStep: "scan_picking",
            message: "",
            messageType: "info",
            loading: false,
            summary: {
                total_pallets: 0,
                completed_pallets: 0,
                pending_pallets: 0,
                total_quantity: 0.0,
                scanned_quantity: 0.0,
                remaining_quantity: 0.0,
                related_pending_picking_names: [],
                related_pending_picking_count: 0,
                related_picking_message: "",
            },
            lastScan: {},
            updatedMoveLineIds: [],
        });

        // 扫码输入缓冲
        this._scanBuffer = "";
        this._scanTimer = null;
        this._isProcessing = false;
        this._isPDA = this._detectPDA();

        this.barcodeInputRef = useRef("barcodeInput");

        onMounted(async () => {
            console.log("[WholePalletOutbound] mounted");
            this._bindKeyListener();
            this._bindVisibilityChange();
            this._focusBarcodeInput();
        });

        onWillUnmount(() => {
            this._unbindKeyListener();
            this._unbindVisibilityChange();
            this._clearScanTimer();
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // 设备检测
    // ═══════════════════════════════════════════════════════════════

    _detectPDA() {
        const hasTouchScreen = (
            "ontouchstart" in window ||
            navigator.maxTouchPoints > 0 ||
            window.matchMedia("(pointer: coarse)").matches
        );
        const isDesktop = window.matchMedia("(min-width: 1024px)").matches && !hasTouchScreen;
        return !isDesktop;
    }

    // ═══════════════════════════════════════════════════════════════
    // 扫码监听
    // ═══════════════════════════════════════════════════════════════

    _onBarcodeInput(ev) {
        const input = ev.target;
        if (!input) return;

        const value = input.value;
        if (ev.inputType === "insertLineFeed" || value.includes("\n") || value.includes("\r")) {
            const barcode = value.replace(/\n/g, "").replace(/\r/g, "").trim();
            if (barcode) {
                input.value = "";
                this.onBarcodeScanned(barcode);
            }
        }
    }

    _onBarcodeKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const input = ev.target;
            const barcode = input.value.trim();
            if (barcode) {
                input.value = "";
                this.onBarcodeScanned(barcode);
            }
        }
    }

    _onBarcodeBlur(ev) {
        if (!this._isProcessing && !this._isPDA) {
            setTimeout(() => this._focusBarcodeInput(), 0);
        }
    }

    _focusBarcodeInput() {
        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
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

    _clearScanTimer() {
        if (this._scanTimer) {
            clearTimeout(this._scanTimer);
            this._scanTimer = null;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 扫码核心 - 调用后端统一接口
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
            const pickingId = this.state.order?.id || false;
            const locationId = this.state.currentLocation?.id || false;
            const packageId = this.state.currentPallet?.id || false;
            const productId = this.state.currentProduct?.id || false;
            const lotId = this.state.currentLot?.id || false;

            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_outgoing_scan_barcode",
                [barcode, pickingId, locationId, packageId, productId, lotId, false, false]
            );

            await this._applyScanResult(result, true);

            if (result.action?.updated_move_line_ids?.length) {
                this.state.updatedMoveLineIds = result.action.updated_move_line_ids;
            }
        } catch (error) {
            console.error("[WholePalletOutbound] scan error:", error);
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._isProcessing = false;
            this._focusBarcodeInput();
        }
    }

    /**
     * 映射后端 scan_state 到前端 state
     * 后端返回结构：
     * {
     *   success, type, barcode, barcode_type, message, next_step,
     *   current: { picking_id, location_id, package_id, product_id, lot_id, pending_operation },
     *   action: { name, updated_move_line_ids },
     *   scan_state: {
     *     picking: { id, name, origin, reference, partner, state, picking_type_code, outbound_scan_mode },
     *     current_location, current_pallet, current_product, current_lot,
     *     summary: { total_pallets, completed_pallets, pending_pallets, total_quantity, ... },
     *     pallets: [ { package_id, package_name, package_barcode, location_id, location_name, ... } ],
     *     last_scan
     *   }
     * }
     */
    async _applyScanResult(result, notify = true) {
        if (!result) return;

        const scanState = result.scan_state || {};

        // 更新出库单信息
        this.state.order = scanState.picking ? { ...scanState.picking } : null;

        // 更新当前上下文
        this.state.currentLocation = scanState.current_location ? { ...scanState.current_location } : {};
        this.state.currentPallet = scanState.current_pallet ? { ...scanState.current_pallet } : {};
        this.state.currentProduct = scanState.current_product ? { ...scanState.current_product } : {};
        this.state.currentLot = scanState.current_lot ? { ...scanState.current_lot } : {};

        // 更新 summary
        this.state.summary = scanState.summary ? { ...scanState.summary } : this._getEmptySummary();

        // 深度映射 pallets 数组
        if (scanState.pallets && scanState.pallets.length > 0) {
            this.state.pallets = scanState.pallets.map(pallet => ({
                ...pallet,
                products: (pallet.products || []).map(product => ({ ...product })),
            }));
        } else {
            this.state.pallets = [];
        }

        // 更新 lastScan
        this.state.lastScan = scanState.last_scan ? { ...scanState.last_scan } : {};

        // 更新下一步
        this.state.nextStep = result.next_step || "scan_picking";

        // 提示用户
        if (notify && result.message) {
            const msgType = result.success === false ? "danger" : "success";
            this.showMessage(result.message, msgType);

            if (result.success !== false) {
                this._flashScreen([100, 200, 100], false);
            }
        }
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
            await this.orm.call("stock.picking", "button_validate", [this.state.order.id]);
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
        this.state.currentPallet = {};
        this.state.currentProduct = {};
        this.state.currentLot = {};
        this.state.nextStep = "scan_picking";
        this.state.message = "";
        this.state.messageType = "info";
        this.state.loading = false;
        this.state.summary = this._getEmptySummary();
        this.state.lastScan = {};
        this.state.updatedMoveLineIds = [];
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

    formatError(err) {
        return (
            err?.data?.arguments?.[0] ||
            (err?.data?.message
                ? err.data.message.replace(/^odoo\.exceptions\.[^:]+\:\s*/, "")
                : "") ||
            err?.message ||
            _t("Unknown error")
        );
    }

    _getEmptySummary() {
        return {
            total_pallets: 0,
            completed_pallets: 0,
            pending_pallets: 0,
            total_quantity: 0.0,
            scanned_quantity: 0.0,
            remaining_quantity: 0.0,
            related_pending_picking_names: [],
            related_pending_picking_count: 0,
            related_picking_message: "",
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // 计算属性（与模板对应）
    // ═══════════════════════════════════════════════════════════════

    get hasOrder() {
        return !!this.state.order?.id;
    }

    get hasLocation() {
        return !!this.state.currentLocation?.id;
    }

    get currentLocationName() {
        return this.state.currentLocation?.name || this.state.currentLocation?.display_name || "";
    }

    get currentLocationBarcode() {
        return this.state.currentLocation?.barcode || "";
    }

    get isScanOrderStep() {
        return this.state.nextStep === "scan_picking";
    }

    get isScanLocationStep() {
        return this.state.nextStep === "scan_location";
    }

    get isScanPalletStep() {
        return this.state.nextStep === "scan_pallet";
    }

    get scanModeLabel() {
        const map = {
            scan_picking: _t("Scan Order"),
            scan_location: _t("Scan Location"),
            scan_pallet: _t("Scan Pallet"),
        };
        return map[this.state.nextStep] || _t("Scan Barcode");
    }

    get stepHint() {
        const hints = {
            scan_picking: _t("Scan outbound order barcode to start"),
            scan_location: _t("Scan storage location barcode"),
            scan_pallet: _t("Scan pallet barcode to confirm"),
        };
        return hints[this.state.nextStep] || "";
    }

    get progressPercent() {
        const s = this.state.summary || {};
        const total = s.total_pallets || 0;
        const done = s.completed_pallets || 0;
        if (!total) return 0;
        return Math.round((done / total) * 100);
    }

    get isAllComplete() {
        const s = this.state.summary || {};
        return (s.pending_pallets || 0) === 0 && (s.total_pallets || 0) > 0;
    }

    get palletList() {
        return Array.isArray(this.state.pallets) ? this.state.pallets : [];
    }

    get orderReference() {
        return this.state.order?.reference || this.state.order?.name || "";
    }

    get orderOrigin() {
        return this.state.order?.origin || "";
    }

    get orderPartner() {
        return this.state.order?.partner || "";
    }

    get outboundScanMode() {
        return this.state.order?.outbound_scan_mode || "";
    }

    get relatedPickingMessage() {
        return this.state.summary?.related_picking_message || "";
    }

    get relatedPendingPickingCount() {
        return this.state.summary?.related_pending_picking_count || 0;
    }
}
