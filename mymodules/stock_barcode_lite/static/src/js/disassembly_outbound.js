/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * Disassembly Outbound Flow (Backend-driven)
 *
 * 拆托出库：
 * 扫码流程：
 *  ─────────────────────────────────────────────────────────────────────
 *  1. Order   : 扫出库单 picking name
 *  2. Location: 扫货位条码
 *  3. Pallet  : 扫托盘条码 → 判断是整托还是拆托
 *     - 整托: 系统自动填充 → 完成
 *     - 拆托: 继续扫产品条码 → 扫SN/批次 → 完成
 *  ─────────────────────────────────────────────────────────────────────
 *  完成所有托盘后，可确认出库
 *
 * 本页面完全依赖后端接口 process_outgoing_scan_barcode 驱动流程，
 * 后端返回统一的 scan_state 结构，前端负责渲染和交互。
 */
export class DisassemblyOutboundPage extends Component {
    static template = "stock_barcode_lite.DisassemblyOutboundPage";
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
            currentProductIndex: -1,  // 当前正在处理的产品索引
            isDisassemblyMode: false, // 是否处于拆托模式
            quantityInput: "",        // 数量输入缓冲
            currentScannedPalletId: null, // 当前扫描的托盘ID（用于高亮标识）
            expandedPalletIds: [], // 自动展开的托盘ID列表
        });

        // 扫码输入缓冲
        this._scanBuffer = "";
        this._scanTimer = null;
        this._isProcessing = false;
        this._isPDA = this._detectPDA();

        this.barcodeInputRef = useRef("barcodeInput");

        onMounted(async () => {
            this._bindKeyListener();
            this._bindFocusGuard();
            this._bindVisibilityChange();
            this._bindGlobalKeyListener();
            this._focusBarcodeInput();
            // 初始化 Bootstrap 折叠效果
            this._initCollapse();
        });

        onWillUnmount(() => {
            this._unbindKeyListener();
            this._unbindFocusGuard();
            this._unbindVisibilityChange();
            this._unbindGlobalKeyListener();
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
        if (!this._isProcessing && !this.isScanQuantityStep) {
            setTimeout(() => this._focusBarcodeInput(), 0);
        }
    }

    _bindFocusGuard() {
        const container = this.el;
        if (!container) return;

        this._onFocusOut = (ev) => {
            const related = ev.relatedTarget;
            const isInputElement = related && (
                related.tagName === "INPUT" ||
                related.tagName === "TEXTAREA" ||
                related.isContentEditable
            );
            const shouldRefocus = !isInputElement && !this.isScanQuantityStep && !this._isProcessing;

            if (shouldRefocus) {
                requestAnimationFrame(() => {
                    this._focusBarcodeInput();
                });
            }
        };

        this._onDocumentPointerDown = (ev) => {
            const toggle = ev.target.closest?.('[data-bs-toggle="collapse"]') || ev.target.closest?.('.o_pallet_header');
            if (!toggle) return;
            if (this.isScanQuantityStep || this._isProcessing) return;
        };

        this._onDocumentPointerUp = (ev) => {
            const toggle = ev.target.closest?.('[data-bs-toggle="collapse"]') || ev.target.closest?.('.o_pallet_header');
            if (!toggle) return;
            if (this.isScanQuantityStep || this._isProcessing) return;

            setTimeout(() => {
                this._focusBarcodeInput();
            }, 100);
        };

        container.addEventListener("focusout", this._onFocusOut);
        document.addEventListener("pointerdown", this._onDocumentPointerDown);
        document.addEventListener("pointerup", this._onDocumentPointerUp);
    }

    _unbindFocusGuard() {
        if (this._onFocusOut) {
            this.el?.removeEventListener("focusout", this._onFocusOut);
            this._onFocusOut = null;
        }
        if (this._onDocumentPointerDown) {
            document.removeEventListener("pointerdown", this._onDocumentPointerDown);
            this._onDocumentPointerDown = null;
        }
        if (this._onDocumentPointerUp) {
            document.removeEventListener("pointerup", this._onDocumentPointerUp);
            this._onDocumentPointerUp = null;
        }
    }

   _focusBarcodeInput() {
       if (this.isScanQuantityStep) {
           return;
       }
       const input = this.barcodeInputRef.el;
       if (input) {
           input.focus();
           input.value = "";
       } else {
           console.warn("[BarcodeMonitor] _focusBarcodeInput input missing");
       }
   }

    _reconcileFocus() {
        requestAnimationFrame(() => {
            if (this.isScanQuantityStep) {
                const qtyInput = this.el?.querySelector('.o_sbl_quantity_panel input[type="number"]');
                if (qtyInput) qtyInput.focus();
            } else {
                const input = this.barcodeInputRef.el;
                if (input) {
                    input.focus();
                    input.value = "";
                }
            }
        });
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
        } else {
            console.log("[BarcodeMonitor] _bindKeyListener PDA mode - deferred focus");
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

    _bindGlobalKeyListener() {
        this._onGlobalKeyDown = (ev) => {
            const target = ev.target;
            if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
                return;
            }

            if (ev.key.length > 1 && ev.key !== "Enter") {
                return;
            }

            const input = this.barcodeInputRef.el;
            if (!input) return;

            if (ev.key === "Enter") {
                ev.preventDefault();
                const barcode = input.value.trim();
                if (barcode) {
                    input.value = "";
                    this.onBarcodeScanned(barcode);
                }
            } else {
                input.value += ev.key;
                if (input.value.includes("\n") || input.value.includes("\r")) {
                    const barcode = input.value.replace(/\n/g, "").replace(/\r/g, "").trim();
                    if (barcode) {
                        input.value = "";
                        this.onBarcodeScanned(barcode);
                    }
                }
            }
        };

        document.addEventListener("keydown", this._onGlobalKeyDown);
    }

    _unbindGlobalKeyListener() {
        if (this._onGlobalKeyDown) {
            document.removeEventListener("keydown", this._onGlobalKeyDown);
            this._onGlobalKeyDown = null;
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
            console.log("[DisassemblyOutbound] Skipped - no barcode or still processing");
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;

        try {
            if (this.state.nextStep === "validate") {
                this.showMessage(
                    _t("All products scanned. Click Confirm Outbound to complete."),
                    "info"
                );
                this._focusBarcodeInput();
                return;
            }

            if (this.state.nextStep === "input_quantity") {
                this.showMessage(
                    _t("Please use the quantity input to confirm the scanned quantity."),
                    "danger"
                );
                this._focusBarcodeInput();
                return;
            }

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
            const scanMode = result.scan_state?.picking?.outbound_scan_mode;
            if (nextStep !== "scan_picking" && scanMode && scanMode !== "partial_pallet") {
                this.showMessage(
                    _t("This picking requires scan mode: ") + scanMode + _t(", but this page only supports partial_pallet mode. Please use the correct scanning page."),
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
                this.state.currentProductIndex = -1;
                this.state.isDisassemblyMode = false;
                this._focusBarcodeInput();
                return;
            }

            await this._applyScanResult(result, true);

            if (result.action?.updated_move_line_ids?.length) {
                this.state.updatedMoveLineIds = result.action.updated_move_line_ids;
            }
        } catch (error) {
            console.error("[DisassemblyOutbound] scan error:", error);
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
       } finally {
           this.state.loading = false;
           this._isProcessing = false;
            this._reconcileFocus();
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
     *     pallets: [ { package_id, package_name, package_barcode, location_id, location_name, 
     *                  is_complete, can_ship_whole, products: [...] } ],
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
            this.state.pallets = scanState.pallets.map(pallet => {
                return {
                    ...pallet,
                    products: (pallet.products || []).map(product => ({ ...product })),
                };
            });
        } else {
            this.state.pallets = [];
        }

        // 更新 lastScan
        this.state.lastScan = scanState.last_scan ? { ...scanState.last_scan } : {};

        // 更新下一步
        this.state.nextStep = result.next_step || "scan_picking";

        // 记录当前扫描的托盘ID（用于UI高亮标识）
        if (this.state.currentPallet?.id) {
            this.state.currentScannedPalletId = this.state.currentPallet.id;
            // 自动展开当前扫描的托盘
            if (!this.state.expandedPalletIds.includes(this.state.currentPallet.id)) {
                this.state.expandedPalletIds = [...this.state.expandedPalletIds, this.state.currentPallet.id];
            }
        }

        // 渲染完成后展开托盘卡片
        this._expandCurrentPalletAfterRender();

        // 判断是否进入拆托模式（需要扫产品）
        this.state.isDisassemblyMode = this.state.nextStep === "scan_product";

        // 数量输入模式需要保留当前 product/lot 上下文，避免前端误清空
        if (result.next_step === "input_quantity") {
            this.state.currentProduct = scanState.current_product
                ? { ...scanState.current_product }
                : this.state.currentProduct;
            this.state.currentLot = scanState.current_lot
                ? { ...scanState.current_lot }
                : this.state.currentLot;
            this.state.quantityInput = "";

            // 后端 current_product 缺少 move_line_id，需要从 pallets 中补全
            // 优先使用当前托盘的数据，避免跨托盘错误匹配
            const currentProductId = this.state.currentProduct?.id;
            const currentPalletId = this.state.currentPallet?.id;

            if (currentProductId && scanState.pallets) {
                let fullProduct = null;

                // 优先从当前托盘查找
                if (currentPalletId) {
                    const currentPalletData = scanState.pallets.find(p => p.package_id === currentPalletId);
                    if (currentPalletData) {
                        fullProduct = currentPalletData.products?.find(p => p.product_id === currentProductId);
                        if (fullProduct) {
                            console.log("[_applyScanResult] FOUND in current pallet:", fullProduct);
                        }
                    }
                }

                // 如果当前托盘没有，尝试其他托盘
                if (!fullProduct) {
                    for (const pallet of scanState.pallets) {
                        if (pallet.package_id === currentPalletId) continue;
                        fullProduct = pallet.products?.find(p => p.product_id === currentProductId);
                        if (fullProduct) {
                            console.log("[_applyScanResult] FOUND in other pallet:", fullProduct);
                            break;
                        }
                    }
                }

                if (fullProduct) {
                    // 用 pallets 中的完整数据补充 currentProduct
                    this.state.currentProduct = {
                        ...this.state.currentProduct,
                        ...fullProduct,
                    };
                    console.log("[_applyScanResult] AFTER补充 - currentProduct:", this.state.currentProduct);
                }
            }
        }

        // 离开数量输入模式时，清理当前产品/批次
        // 但保留 move_line_id 供后续使用（后端会清空 product_id）
        if (this.state.nextStep !== "input_quantity") {
            // 保存当前 move_line_id，清理后需要恢复
            const preservedMoveLineId = this.state.currentProduct?.move_line_id;

            this.state.currentProduct = scanState.current_product
                ? { ...scanState.current_product }
                : {};
            this.state.currentLot = scanState.current_lot
                ? { ...scanState.current_lot }
                : {};
            this.state.quantityInput = "";

            // 后端返回的 current_product 没有 move_line_id，需要恢复
            if (!this.state.currentProduct?.move_line_id && preservedMoveLineId) {
                this.state.currentProduct.move_line_id = preservedMoveLineId;
            }
        }

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
    // 数量输入处理
    // ═══════════════════════════════════════════════════════════════

    onQuantityInput(ev) {
        this.state.quantityInput = ev.target.value;
    }

    // ═══════════════════════════════════════════════════════════════
    // 数量提交
    // ═══════════════════════════════════════════════════════════════

    async submitQuantity(ev) {
        if (ev && ev.type === "keydown" && ev.key !== "Enter") {
            return;
        }
        if (ev) {
            ev.preventDefault();
        }

        if (!this.state.currentProduct?.id) {
            this.showMessage(_t("Please scan product first"), "danger");
            return;
        }
        const qty = parseFloat(this.state.quantityInput || "0");
        if (!qty || qty <= 0) {
            this.showMessage(_t("Please input a valid positive quantity."), "danger");
            this._flashScreen([200, 100, 100], true);
            this._focusBarcodeInput();
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_outgoing_quantity_scan",
                [
                    "",
                    qty,
                    this.state.order?.id || false,
                    this.state.currentLocation?.id || false,
                    this.state.currentPallet?.id || false,
                    this.state.currentProduct?.id || false,
                    this.state.currentLot?.id || false,
                    false,
                ]
            );

            // 后端返回错误
            if (result.success === false) {
                this.showMessage(result.message || _t("Quantity error"), "danger");
                this._flashScreen([200, 100, 100], true);
                this.state.quantityInput = "";
                return;
            }

            // 正常处理：后端已经清掉了 product_id/lot_id，
            // 并返回了正确的 next_step，前端直接沿用
           await this._applyScanResult(result, true);
           this.state.quantityInput = "";

        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._isProcessing = false;
            this._reconcileFocus();
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
        this.state.currentProductIndex = -1;
        this.state.isDisassemblyMode = false;
        this.state.quantityInput = "";
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

    /**
     * 初始化 Bootstrap 折叠效果
     */
    _initCollapse() {
        if (typeof window.bootstrap !== 'undefined') {
            const collapseElements = this.el?.querySelectorAll('.collapse');
            if (collapseElements) {
                collapseElements.forEach(el => {
                    // 确保已展开的托盘正确显示
                    const targetId = el.id;
                    if (targetId && targetId.startsWith('pallet_products_')) {
                        const palletId = parseInt(targetId.split('_').pop());
                        if (this.isPalletExpanded(palletId)) {
                            el.classList.add('show');
                            // 更新对应的 header aria-expanded
                            const header = this.el?.querySelector(`[data-bs-target="#${targetId}"]`);
                            if (header) {
                                header.setAttribute('aria-expanded', 'true');
                            }
                        }
                    }
                });
            }
        }
    }

    /**
     * 渲染后展开当前托盘
     * Owl 渲染完成后调用，确保 collapse 面板正确展开
     */
    _expandCurrentPalletAfterRender() {
        if (!this.state.currentScannedPalletId) return;

        const currentPalletId = this.state.currentScannedPalletId;
        const targetId = `pallet_products_${currentPalletId}`;
        const collapseEl = this.el?.querySelector(`#${targetId}`);
        const headerEl = this.el?.querySelector(`[data-bs-target="#${targetId}"]`);

        // 尝试使用 Owl 的渲染后钩子
        const tryExpand = (attempt) => {
            const el = this.el?.querySelector(`#${targetId}`);
            const hdr = this.el?.querySelector(`[data-bs-target="#${targetId}"]`);

            if (el && !el.classList.contains('show')) {
                el.classList.add('show');
                if (hdr) {
                    hdr.setAttribute('aria-expanded', 'true');
                }
                return true;
            }
            return false;
        };

        // 立即尝试
        if (!tryExpand(0)) {
            // 依次延迟重试，等待 Owl 完成 DOM 更新
            [50, 100, 200, 350, 500].forEach(delay => {
                setTimeout(() => tryExpand(delay), delay);
            });
        }
    }

    /**
     * 展开指定的托盘卡片（手动控制 Bootstrap collapse）
     */
    _expandPallet(palletId) {
        const targetId = `pallet_products_${palletId}`;
        const collapseEl = this.el?.querySelector(`#${targetId}`);
        const headerEl = this.el?.querySelector(`[data-bs-target="#${targetId}"]`);

        if (collapseEl && headerEl) {
            collapseEl.classList.add('show');
            headerEl.setAttribute('aria-expanded', 'true');
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

    get isScanProductStep() {
        return this.state.nextStep === "scan_product";
    }

    get isScanLotStep() {
        return this.state.nextStep === "scan_lot";
    }

    get isScanQuantityStep() {
        return this.state.nextStep === "input_quantity";
    }

    get scanModeLabel() {
        const map = {
            scan_picking: _t("Scan Order"),
            scan_location: _t("Scan Location"),
            scan_pallet: _t("Scan Pallet"),
            scan_product: _t("Scan Product"),
            scan_lot: _t("Scan Lot/SN"),
            input_quantity: _t("Input Quantity"),
            validate: _t("All Done"),
        };
        return map[this.state.nextStep] || _t("Scan Barcode");
    }

    get stepHint() {
        const hints = {
            scan_picking: _t("Scan outbound order barcode to start"),
            scan_location: _t("Scan storage location barcode"),
            scan_pallet: _t("Scan pallet barcode - system will detect whole or disassembly"),
            scan_product: _t("Scan product barcode from the current pallet"),
            scan_lot: _t("Scan serial number or lot number"),
            input_quantity: _t("Input quantity for the current product/lot"),
            validate: _t("All pallets scanned. Click Confirm Outbound to complete."),
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

    /**
     * 检查指定托盘是否为当前扫描的高亮托盘
     */
    isCurrentHighlightedPallet(palletId) {
        return this.state.currentScannedPalletId === palletId;
    }

    /**
     * 检查指定托盘是否应该展开
     */
    isPalletExpanded(palletId) {
        return this.state.expandedPalletIds.includes(palletId);
    }

    /**
     * 返回托盘产品折叠容器的 class
     */
    getPalletProductsClass(palletId) {
        return this.isPalletExpanded(palletId)
            ? "o_pallet_products collapse show"
            : "o_pallet_products collapse";
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
