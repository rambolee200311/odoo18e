/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class InboundFlow extends Component {
    static template = "stock_barcode_lite.InboundPage";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.barcodeInputRef = useRef("barcodeInput");

        this.state = useState({
            loading: false,
            message: "",
            messageType: "info",
            nextStep: "scan_picking",
            pallets: [],
            picking: null,
            currentLocation: {},
            summary: {
                total_pallets: 0,
                updated_pallets: 0,
                pending_pallets: 0,
                total_move_lines: 0,
                updated_move_lines: 0,
                pending_move_lines: 0,
            },
            lastScan: {},
            updatedMoveLineIds: [],
        });

        // 扫码输入缓冲
        this._scanBuffer = "";
        this._scanTimer = null;
        this._isProcessing = false;
        this._isPDA = this._detectPDA();

        onMounted(async () => {
            this._bindVisibilityChange();
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.addEventListener("input", this._onBarcodeInput.bind(this));
                barcodeInput.addEventListener("keydown", this._onBarcodeKeydown.bind(this));
                barcodeInput.addEventListener("keypress", this._onBarcodeKeypress.bind(this));
                barcodeInput.addEventListener("blur", this._onBarcodeBlur.bind(this));
                // 初始化时聚焦输入框
                this._focusBarcodeInput();
            }
            await this._initScanState();

        });

        onWillUnmount(() => {
            this._unbindVisibilityChange();
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.removeEventListener("input", this._onBarcodeInput.bind(this));
                barcodeInput.removeEventListener("keydown", this._onBarcodeKeydown.bind(this));
                barcodeInput.removeEventListener("keypress", this._onBarcodeKeypress.bind(this));
                barcodeInput.removeEventListener("blur", this._onBarcodeBlur.bind(this));
            }
            this._clearScanTimer();
        });
    }

    /**
     * 检测是否为PDA设备
     */
//    _detectPDA() {
//        const hasTouchScreen = (
//            'ontouchstart' in window ||
//            navigator.maxTouchPoints > 0 ||
//            window.matchMedia('(pointer: coarse)').matches
//        );
//        const isDesktop = window.matchMedia('(min-width: 1024px)').matches && !hasTouchScreen;
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

        // 处理包含换行符的情况
        if (ev.inputType === "insertLineFeed" || value.includes("\n") || value.includes("\r")) {
            const barcode = value.replace(/\n/g, "").replace(/\r/g, "").trim();
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

    _onBarcodeKeypress(ev) {
        if (ev.key === "Enter" || ev.charCode === 13) {
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
        // PDA模式下也自动聚焦，确保扫码枪输入能被捕获
        if (!this._isProcessing) {
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
    // 初始化
    // ═══════════════════════════════════════════════════════════════

    async _initScanState() {
        const context = this.props?.action?.context || {};
        const pickingId = context.pickingId || context.picking_id || false;
        const currentLocationId = context.currentLocationId || context.current_location_id || false;

        if (!pickingId) {
            this.state.nextStep = "scan_picking";
            return;
        }

        try {
            this.state.loading = true;
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "get_incoming_scan_state",
                [pickingId, currentLocationId || false, {}]
            );
            await this._applyScanResult(result, false);
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
        } finally {
            this.state.loading = false;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 扫码核心
    // ═══════════════════════════════════════════════════════════════

    async onBarcodeScanned(barcode) {
        if (!barcode || this._isProcessing) {
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;

        try {
            const pickingId = this.state.picking?.id || false;
            const locationId = this.state.currentLocation?.id || false;

            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_incoming_scan_barcode",
                [barcode, pickingId, locationId]
            );

            await this._applyScanResult(result, true);

            if (result.action?.updated_move_line_ids?.length) {
                this.state.updatedMoveLineIds = result.action.updated_move_line_ids;
            }
        } catch (error) {
            console.error('[InboundFlow] scan error:', error);
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._isProcessing = false;
            this._focusBarcodeInput();
        }
    }

    async _applyScanResult(result, notify = true) {
        if (!result) return;

        const scanState = result.scan_state || {};

        // 更新状态 - OWL 会自动响应
        // 使用展开运算符创建新对象/数组引用，确保响应性检测
        this.state.picking = scanState.picking ? { ...scanState.picking } : null;
        this.state.currentLocation = scanState.current_location ? { ...scanState.current_location } : {};
        this.state.summary = scanState.summary ? { ...scanState.summary } : this._getEmptySummary();
        
        // 深度复制 pallets 数组及其内部对象
        if (scanState.pallets && scanState.pallets.length > 0) {
            this.state.pallets = scanState.pallets.map(pallet => ({ ...pallet }));
        } else {
            this.state.pallets = [];
        }

        this.state.lastScan = scanState.last_scan ? { ...scanState.last_scan } : {};
        this.state.nextStep = result.next_step || "scan_picking";

        if (notify && result.message) {
            const msgType = result.success === false ? "danger" : "success";
            this.showMessage(result.message, msgType);

            if (result.success !== false) {
                this._flashScreen([100, 200, 100], false);
            }
        }
    }

    _getEmptySummary() {
        return {
            total_pallets: 0,
            updated_pallets: 0,
            pending_pallets: 0,
            total_move_lines: 0,
            updated_move_lines: 0,
            pending_move_lines: 0,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // 确认操作按钮
    // ═══════════════════════════════════════════════════════════════

    async confirmInbound() {
        if (!this.state.picking) {
            // 没扫入库单
            this.showMessage(_t("No picking loaded"), "danger");
            return;
        }
        if (this.state.summary.pending_pallets > 0) {
            // 托盘有漏扫
            this.showMessage(
                _t("There are still ") + this.state.summary.pending_pallets + _t(" pallet(s) not updated"),
                "danger"
            );
            return;
        }

        this.state.loading = true;
        try {
            await this.orm.call(
                "stock.picking",
                "button_validate",
                [[this.state.picking.id]]
            );
            // 上架成功
            this.showMessage(_t("Inbound confirmed successfully!"), "success");
            this._flashScreen([100, 300, 100], true);
            setTimeout(() => this.resetScan(), 2000);
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
        } finally {
            this.state.loading = false;
        }
    }

    resetScan() {
        this.state.picking = null;
        this.state.currentLocation = {};
        this.state.summary = this._getEmptySummary();
        this.state.pallets = [];
        this.state.lastScan = {};
        this.state.updatedMoveLineIds = [];
        this.state.nextStep = "scan_picking";
        this.showMessage(_t("Scan reset - ready for new picking"), "info");
        this._focusBarcodeInput();
    }

    exit() {
        this.action.doAction("stock_barcode_lite_homepage");
    }

    // ═══════════════════════════════════════════════════════════════
    // 辅助方法
    // ═══════════════════════════════════════════════════════════════

    _clearScanTimer() {
        if (this._scanTimer) {
            clearTimeout(this._scanTimer);
            this._scanTimer = null;
        }
    }

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
                ? err.data.message.replace(/^odoo\.exceptions\.[^:]+:\s*/, "")
                : "") ||
            err?.message ||
            _t("Unknown error")
        );
    }

    // ═══════════════════════════════════════════════════════════════
    // 计算属性
    // ═══════════════════════════════════════════════════════════════

    get hasPicking() {
        return !!this.state.picking;
    }

    get hasLocation() {
        return !!this.state.currentLocation?.id;
    }

    get pickingLabel() {
        return this.state.picking?.name || "";
    }

    get pickingOrigin() {
        return this.state.picking?.origin || "";
    }

    get pickingReference() {
        return this.state.picking?.reference || "";
    }

    get pickingPartner() {
        return this.state.picking?.partner || "";
    }

    get pickingState() {
        return this.state.picking?.state || "";
    }

    get currentLocationName() {
        return this.state.currentLocation?.display_name ||
               this.state.currentLocation?.name ||
               "";
    }

    get currentLocationBarcode() {
        return this.state.currentLocation?.barcode || "";
    }

    get isScanPickingStep() {
        return this.state.nextStep === "scan_picking";
    }

    get isScanLocationStep() {
        return this.state.nextStep === "scan_location";
    }

    get isScanPackageStep() {
        return this.state.nextStep === "scan_package";
    }

    get scanModeLabel() {
        const map = {
            scan_picking: _t("Scan incoming picking"),
            scan_location: _t("Scan location"),
            scan_package: _t("Scan pallet"),
        };
        return map[this.state.nextStep] || _t("Scan barcode");
    }

    get stepHint() {
        const hints = {
            scan_picking: _t("Scan the incoming picking barcode to start"),
            scan_location: _t("Scan a storage location barcode"),
            scan_package: _t("Scan a pallet barcode to update its location"),
        };
        return hints[this.state.nextStep] || "";
    }

    get summaryCards() {
        const s = this.state.summary || {};
        return [
            { key: "total_pallets", label: _t("Total Pallets"), value: s.total_pallets || 0, icon: "fa-cubes" },
            { key: "updated_pallets", label: _t("Updated"), value: s.updated_pallets || 0, icon: "fa-check-circle", class: "text-success" },
            { key: "pending_pallets", label: _t("Pending"), value: s.pending_pallets || 0, icon: "fa-clock", class: "text-warning" },
            { key: "total_move_lines", label: _t("Move Lines"), value: s.total_move_lines || 0, icon: "fa-arrows-alt-v" },
            { key: "updated_move_lines", label: _t("Processed"), value: s.updated_move_lines || 0, icon: "fa-check", class: "text-success" },
            { key: "pending_move_lines", label: _t("Remaining"), value: s.pending_move_lines || 0, icon: "fa-hourglass-half", class: "text-warning" },
        ];
    }

    get progressPercent() {
        const s = this.state.summary || {};
        const total = s.total_move_lines || 0;
        const done = s.updated_move_lines || 0;
        if (!total) return 0;
        return Math.round((done / total) * 100);
    }

    get isAllComplete() {
        return (this.state.summary?.pending_pallets || 0) === 0 &&
               (this.state.summary?.total_pallets || 0) > 0;
    }

    get palletList() {
        return Array.isArray(this.state.pallets) ? this.state.pallets : [];
    }

    getStateBadgeClass(state) {
        const map = {
            draft: "bg-secondary",
            waiting: "bg-warning text-dark",
            confirmed: "bg-info",
            assigned: "bg-primary",
            done: "bg-success",
            cancel: "bg-danger",
        };
        return map[state] || "bg-secondary";
    }

    getStateLabel(state) {
        const map = {
            draft: _t("Draft"),
            waiting: _t("Waiting"),
            confirmed: _t("Confirmed"),
            assigned: _t("Ready"),
            done: _t("Done"),
            cancel: _t("Cancelled"),
        };
        return map[state] || state;
    }
}
