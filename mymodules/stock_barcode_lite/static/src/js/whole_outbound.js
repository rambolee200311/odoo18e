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
        this.scrollContainerRef = useRef("palletsContainer");

        onMounted(async () => {
            this._bindKeyListener();
            this._bindVisibilityChange();
            this._bindGlobalInteractionListener();
            this._bindCollapseEvents();
            this._focusBarcodeInput();
        });

        onWillUnmount(() => {
            this._unbindKeyListener();
            this._unbindVisibilityChange();
            this._unbindGlobalInteractionListener();
            this._clearScanTimer();
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // 设备检测
    // ═══════════════════════════════════════════════════════════════

//    _detectPDA() {
//        const hasTouchScreen = (
//            "ontouchstart" in window ||
//            navigator.maxTouchPoints > 0 ||
//            window.matchMedia("(pointer: coarse)").matches
//        );
//        const isDesktop = window.matchMedia("(min-width: 1024px)").matches && !hasTouchScreen;
//        return !isDesktop;
//    }

    _detectPDA() {
        // 精确指向设备（鼠标、触控笔）→ 不可能是PDA扫码枪
        const hasFinePointer = window.matchMedia('(pointer: fine)').matches;
        // 支持hover（鼠标悬停）→ 不可能是PDA扫码枪
        const hasHover = window.matchMedia('(hover: hover)').matches;
        // 小屏幕（≤ 768px 宽）→ 可能是手持PDA
        const isSmallScreen = window.matchMedia('(max-width: 768px)').matches;
        // 触屏可用
        const hasTouchScreen = (
            'ontouchstart' in window ||
            navigator.maxTouchPoints > 0 ||
            window.matchMedia('(pointer: coarse)').matches
        );

        // PDA只有在小屏、触屏、无精确指针、无hover的设备上才判定为真
        // 从而排除桌面、大屏平板、触屏笔记本
        return isSmallScreen && hasTouchScreen && !hasFinePointer && !hasHover;
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

        this._boundOnBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundOnBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundOnBarcodeBlur = this._onBarcodeBlur.bind(this);

        input.addEventListener("input", this._boundOnBarcodeInput);
        input.addEventListener("keydown", this._boundOnBarcodeKeydown);
        input.addEventListener("blur", this._boundOnBarcodeBlur);

        if (!this._isPDA) {
            input.focus();
        }
    }

    _unbindKeyListener() {
        const input = this.barcodeInputRef.el;
        if (!input) return;

        if (this._boundOnBarcodeInput) {
            input.removeEventListener("input", this._boundOnBarcodeInput);
            this._boundOnBarcodeInput = null;
        }
        if (this._boundOnBarcodeKeydown) {
            input.removeEventListener("keydown", this._boundOnBarcodeKeydown);
            this._boundOnBarcodeKeydown = null;
        }
        if (this._boundOnBarcodeBlur) {
            input.removeEventListener("blur", this._boundOnBarcodeBlur);
            this._boundOnBarcodeBlur = null;
        }
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
    // 全局交互监听 - PDA模式修复焦点丢失问题
    // ═══════════════════════════════════════════════════════════════

    _bindGlobalInteractionListener() {
        // 点击页面任意位置时恢复输入框焦点 (PDA模式)
        this._onGlobalClick = () => {
            if (this._isPDA) {
                this._focusBarcodeInput();
            }
        };
        document.addEventListener("click", this._onGlobalClick);

        // 滚动停止后恢复焦点
        this._onScrollStop = () => {
            if (this._scrollTimer) {
                clearTimeout(this._scrollTimer);
            }
            this._scrollTimer = setTimeout(() => {
                if (this._isPDA) {
                    this._focusBarcodeInput();
                }
            }, 150);
        };

        const scrollContainer = this.scrollContainerRef?.el;
        if (scrollContainer) {
            scrollContainer.addEventListener("scroll", this._onScrollStop);
        }

        // 触摸开始时也尝试恢复焦点
        this._onTouchStart = () => {
            if (this._isPDA) {
                this._focusBarcodeInput();
            }
        };
        document.addEventListener("touchstart", this._onTouchStart, { passive: true });
    }

    _unbindGlobalInteractionListener() {
        if (this._onGlobalClick) {
            document.removeEventListener("click", this._onGlobalClick);
            this._onGlobalClick = null;
        }
        if (this._onScrollStop) {
            const scrollContainer = this.scrollContainerRef?.el;
            if (scrollContainer) {
                scrollContainer.removeEventListener("scroll", this._onScrollStop);
            }
            this._onScrollStop = null;
        }
        if (this._onTouchStart) {
            document.removeEventListener("touchstart", this._onTouchStart);
            this._onTouchStart = null;
        }
        if (this._scrollTimer) {
            clearTimeout(this._scrollTimer);
            this._scrollTimer = null;
        }
    }

    // 监听Bootstrap折叠展开事件
    _bindCollapseEvents() {
        // 等待DOM完全渲染后再绑定
        this._waitForPalletsReady();
    }

    _waitForPalletsReady() {
        const checkAndBind = () => {
            const collapseElements = document.querySelectorAll(".o_pallet_products");
            if (collapseElements.length > 0) {
                this._bindCollapseListeners(collapseElements);
            } else {
                // 最多重试10次，每次间隔100ms
                if (!this._collapseBindAttempts) {
                    this._collapseBindAttempts = 0;
                }
                this._collapseBindAttempts++;
                if (this._collapseBindAttempts < 10) {
                    setTimeout(checkAndBind, 100);
                }
            }
        };
        setTimeout(checkAndBind, 0);
    }

    _bindCollapseListeners(elements) {
        elements.forEach(el => {
            el.addEventListener("shown.bs.collapse", () => {
                if (this._isPDA) {
                    this._focusBarcodeInput();
                }
            });
            el.addEventListener("hidden.bs.collapse", () => {
                if (this._isPDA) {
                    this._focusBarcodeInput();
                }
            });
        });
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

        if (!barcode || this._isProcessing) {
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

            // 先校验当前 picking 的扫描模式，不匹配就直接提示并重置
            const nextStep = result.next_step || "scan_picking";
            const scanState = result.scan_state || {};
            const scanMode = scanState.picking?.outbound_scan_mode;
            if (nextStep !== "scan_picking" && scanMode && scanMode !== "whole_pallet") {
                this.showMessage(
                    _t("This picking requires scan mode: ") + scanMode + _t(", but this page only supports whole_pallet mode. Please use the correct scanning page."),
                    "danger"
                );
                this._flashScreen([200, 100, 100], true);

                // 保留错误提示，仅清空扫描数据
                this.state.order = null;
                this.state.pallets = [];
                this.state.currentLocation = {};
                this.state.currentPallet = {};
                this.state.currentProduct = {};
                this.state.currentLot = {};
                this.state.nextStep = "scan_picking";
                this.state.summary = this._getEmptySummary();
                this.state.lastScan = {};
                this.state.updatedMoveLineIds = [];
                this._focusBarcodeInput();
                return;
            }

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

        // 错误消息保持到下一次扫码，不自动消失
        if (type !== "danger") {
            this._messageTimer = setTimeout(() => {
                if (this.state.message === text) {
                    this.state.message = "";
                }
            }, 4000);
        }
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

    get pickingDisplayName() {
        return this.state.order?.name || this.state.order?.display_name || this.state.order?.reference || "";
    }

    get pickingStateLabel() {
        const stateMap = {
            draft: "Draft",
            waiting: "Waiting",
            confirmed: "Confirmed",
            assigned: "Ready",
            done: "Done",
            cancel: "Cancelled",
        };
        const state = this.state.order?.state || "";
        return stateMap[state] || state;
    }

    /**
     * 检查指定托盘是否为当前激活/高亮托盘
     */
    isPalletActive(palletId) {
        return this.state.currentPallet?.id === palletId;
    }

    get pickingStateBadgeClass() {
        const state = this.state.order?.state || "";
        const classMap = {
            draft: "secondary",
            waiting: "warning text-dark",
            confirmed: "info",
            assigned: "primary",
            done: "success",
            cancel: "danger",
        };
        return classMap[state] || "secondary";
    }
}
