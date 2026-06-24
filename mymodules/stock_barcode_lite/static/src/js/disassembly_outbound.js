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
        });

        // 扫码输入缓冲
        this._scanBuffer = "";
        this._scanTimer = null;
        this._isProcessing = false;
        this._isPDA = this._detectPDA();

        this.barcodeInputRef = useRef("barcodeInput");

        onMounted(async () => {
            console.log("[DisassemblyOutbound] mounted");
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
        if (!this._isProcessing && !this._isPDA && !this.isScanQuantityStep) {
            setTimeout(() => this._focusBarcodeInput(), 0);
        }
    }

    _focusBarcodeInput() {
        // 在输入数量步骤时，不要抢夺焦点到隐藏的barcode input
        if (this.isScanQuantityStep) {
            return;
        }
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
        console.log("║ [DisassemblyOutbound] BARCODE SCANNED");
        console.log("║ ──────────────────────────────────────────────────────");
        console.log("║ Barcode:", barcode);
        console.log("║ Current Step:", this.state.nextStep);
        console.log("║ Is Processing:", this._isProcessing);
        console.log("║ ──────────────────────────────────────────────────────");
        console.log("║ currentOrder.id:", this.state.order?.id);
        console.log("║ currentLocation.id:", this.state.currentLocation?.id);
        console.log("║ currentPallet.id:", this.state.currentPallet?.id);
        console.log("║ currentPallet.name:", this.state.currentPallet?.name);
        console.log("║ currentProduct.id:", this.state.currentProduct?.id);
        console.log("║ currentProduct.name:", this.state.currentProduct?.name);
        console.log("║ currentLot.id:", this.state.currentLot?.id);
        console.log("║ pallets count:", this.state.pallets?.length || 0);
        console.log("╚═══════════════════════════════════════════════════════");

        if (!barcode || this._isProcessing) {
            console.log("[DisassemblyOutbound] Skipped - no barcode or still processing");
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;

        try {
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

            console.log("[DisassemblyOutbound] Sending to backend:");
            console.log("  - barcode:", barcode);
            console.log("  - pickingId:", pickingId);
            console.log("  - locationId:", locationId);
            console.log("  - packageId:", packageId);
            console.log("  - productId:", productId);
            console.log("  - lotId:", lotId);

            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_outgoing_scan_barcode",
                [barcode, pickingId, locationId, packageId, productId, lotId, false, false]
            );

            console.log("[DisassemblyOutbound] Received from backend:");
            console.log("  - result.success:", result.success);
            console.log("  - result.type:", result.type);
            console.log("  - result.message:", result.message);
            console.log("  - result.next_step:", result.next_step);
            console.log("  - result.scan_state.picking:", result.scan_state?.picking?.id, result.scan_state?.picking?.name);
            console.log("  - result.scan_state.current_pallet:", result.scan_state?.current_pallet);
            console.log("  - result.scan_state.current_product:", result.scan_state?.current_product);
            console.log("  - result.scan_state.pallets count:", result.scan_state?.pallets?.length || 0);

            await this._applyScanResult(result, true);

            // 检查 picking 的出库扫描模式，如果不是 partial_pallet 则中断流程
            if (result.next_step !== "scan_picking") {
                const scanMode = this.state.order?.outbound_scan_mode;
                if (scanMode && scanMode !== "partial_pallet") {
                    this.showMessage(
                        _t("This picking requires scan mode: ") + scanMode + _t(", but this page only supports partial_pallet mode. Please use the correct scanning page."),
                        "danger"
                    );
                    this._flashScreen([200, 100, 100], true);

                    // 重置数据
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
            }

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
     *     pallets: [ { package_id, package_name, package_barcode, location_id, location_name, 
     *                  is_complete, can_ship_whole, products: [...] } ],
     *     last_scan
     *   }
     * }
     */
    async _applyScanResult(result, notify = true) {
        if (!result) return;

        console.log("[_applyScanResult] === START ===");
        console.log("[_applyScanResult] result.success:", result.success);
        console.log("[_applyScanResult] result.type:", result.type);
        console.log("[_applyScanResult] result.next_step:", result.next_step);
        console.log("[_applyScanResult] result.message:", result.message);

        const scanState = result.scan_state || {};
        console.log("[_applyScanResult] scanState.picking:", scanState.picking?.id, scanState.picking?.name);
        console.log("[_applyScanResult] scanState.current_location:", scanState.current_location);
        console.log("[_applyScanResult] scanState.current_pallet:", scanState.current_pallet);
        console.log("[_applyScanResult] scanState.current_product:", scanState.current_product);
        console.log("[_applyScanResult] scanState.current_lot:", scanState.current_lot);
        console.log("[_applyScanResult] scanState.pallets:", scanState.pallets);
        console.log("[_applyScanResult] scanState.summary:", scanState.summary);

        // 更新出库单信息
        this.state.order = scanState.picking ? { ...scanState.picking } : null;

        // 更新当前上下文
        this.state.currentLocation = scanState.current_location ? { ...scanState.current_location } : {};
        this.state.currentPallet = scanState.current_pallet ? { ...scanState.current_pallet } : {};
        this.state.currentProduct = scanState.current_product ? { ...scanState.current_product } : {};
        this.state.currentLot = scanState.current_lot ? { ...scanState.current_lot } : {};

        console.log("[_applyScanResult] AFTER basic update:");
        console.log("[_applyScanResult]   this.state.currentPallet:", JSON.stringify(this.state.currentPallet));
        console.log("[_applyScanResult]   this.state.currentProduct:", JSON.stringify(this.state.currentProduct));

        // 更新 summary
        this.state.summary = scanState.summary ? { ...scanState.summary } : this._getEmptySummary();

        // 深度映射 pallets 数组
        if (scanState.pallets && scanState.pallets.length > 0) {
            console.log("[_applyScanResult] Mapping pallets:", scanState.pallets.length);
            this.state.pallets = scanState.pallets.map(pallet => {
                console.log("[_applyScanResult]   pallet:", pallet.package_id, pallet.package_name, "products:", pallet.products?.length);
                return {
                    ...pallet,
                    products: (pallet.products || []).map(product => ({ ...product })),
                };
            });
        } else {
            console.log("[_applyScanResult] No pallets in scanState");
            this.state.pallets = [];
        }

        // 更新 lastScan
        this.state.lastScan = scanState.last_scan ? { ...scanState.last_scan } : {};

        // 更新下一步
        this.state.nextStep = result.next_step || "scan_picking";
        console.log("[_applyScanResult] Set nextStep to:", this.state.nextStep);

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
            console.log("[_applyScanResult] input_quantity: currentProductId:", currentProductId);
            console.log("[_applyScanResult] input_quantity: currentPalletId:", currentPalletId);

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

        console.log("[_applyScanResult] === END ===");
        console.log("[_applyScanResult] final nextStep:", this.state.nextStep);
        console.log("[_applyScanResult] final currentPallet:", this.state.currentPallet);
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

        console.log("[submitQuantity] === START ===");
        console.log("[submitQuantity] currentProduct:", JSON.stringify(this.state.currentProduct));
        console.log("[submitQuantity] currentPallet11111:", JSON.stringify(this.state.currentPallet));
        console.log("[submitQuantity] quantityInput:", this.state.quantityInput);

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
            // 保存当前产品的 move_line_id，用于后续查找最新数据
            const currentMoveLineId = this.state.currentProduct?.move_line_id;
            const totalQty = this.state.currentProduct?.quantity || 0;

            console.log("[submitQuantity] Calling backend:");
            console.log("  - qty:", qty);
            console.log("  - order.id:", this.state.order?.id);
            console.log("  - location.id:", this.state.currentLocation?.id);
            console.log("  - pallet.id:", this.state.currentPallet?.id);
            console.log("  - product.id:", this.state.currentProduct?.id);
            console.log("  - lot.id:", this.state.currentLot?.id);
            console.log("  - currentMoveLineId:", currentMoveLineId);
            console.log("  - totalQty:", totalQty);

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

            console.log("[submitQuantity] Received result:");
            console.log("  - success:", result.success);
            console.log("  - message:", result.message);
            console.log("  - next_step:", result.next_step);

            // 错误处理
            if (result.success === false) {
                this.showMessage(result.message || _t("Quantity error"), "danger");
                this._flashScreen([200, 100, 100], true);
                this.state.quantityInput = "";
                this.state.nextStep = "input_quantity";
                return;
            }

            // 更新界面
            await this._applyScanResult(result, false);

            // 从更新后的 pallets 获取最新的 scanned_quantity
            let scannedQty = 0;
            if (currentMoveLineId) {
                console.log("[submitQuantity] Searching pallets for move_line_id:", currentMoveLineId);
                for (const pallet of this.state.pallets) {
                    console.log("[submitQuantity]   Checking pallet:", pallet.package_id, pallet.package_name);
                    const product = pallet.products?.find(p => p.move_line_id === currentMoveLineId);
                    if (product) {
                        console.log("[submitQuantity]   FOUND! scanned_quantity:", product.scanned_quantity);
                        scannedQty = product.scanned_quantity || 0;
                        break;
                    }
                }
            } else {
                console.log("[submitQuantity] No currentMoveLineId, cannot find scanned quantity");
            }

            const remainingQty = Math.max(totalQty - scannedQty, 0);
            console.log("[submitQuantity] totalQty:", totalQty, "scannedQty:", scannedQty, "remainingQty:", remainingQty);

            if (scannedQty >= totalQty && totalQty > 0) {
                this.showMessage(_t("Quantity matched! Product completed successfully."), "success");
                this._flashScreen([100, 200, 100], false);
                this.state.currentProduct = {};
                this.state.currentLot = {};
                this.state.quantityInput = "";
            } else {
                this.showMessage(
                    _t("Added: ") + qty + _t(". Remaining: ") + remainingQty + _t(" unit(s)."),
                    "danger"
                );
                this._flashScreen([200, 200, 100], false);
                this.state.quantityInput = "";
            }
        } catch (error) {
            console.error("[DisassemblyOutbound] quantity error:", error);
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._isProcessing = false;
            setTimeout(() => {
                const qtyInput = document.querySelector('.o_sbl_quantity_panel input[type="number"]');
                if (qtyInput) qtyInput.focus();
            }, 50);
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