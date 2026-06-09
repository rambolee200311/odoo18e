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

        this.barcodeInputRef = useRef("barcodeInput");
        this._isProcessing = false;

        // 预先绑定事件处理器，避免 removeEventListener 无法正确移除
        this._boundBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundBarcodeKeypress = this._onBarcodeKeypress.bind(this);
        this._boundBarcodeBlur = this._onBarcodeBlur.bind(this);

        onMounted(async () => {
            console.log('[InboundFlow] onMounted called');
            this._bindVisibilityChange();

            const barcodeInput = this.barcodeInputRef.el;
            console.log('[InboundFlow] barcodeInput element:', barcodeInput);
            if (barcodeInput) {
                // 直接在 input 元素上绑定事件
                barcodeInput.addEventListener("input", this._boundBarcodeInput);
                barcodeInput.addEventListener("keydown", this._boundBarcodeKeydown);
                barcodeInput.addEventListener("keypress", this._boundBarcodeKeypress);
                barcodeInput.addEventListener("blur", this._boundBarcodeBlur);
                barcodeInput.style.imeMode = "disabled";
                barcodeInput.focus();
                console.log('[InboundFlow] barcodeInput focused, value:', barcodeInput.value);
            } else {
                console.error('[InboundFlow] barcodeInput NOT found!');
            }

            await this._initScanState();
            console.log('[InboundFlow] onMounted complete, state:', JSON.stringify(this.state));
        });

        onWillUnmount(() => {
            this._unbindVisibilityChange();
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                // 使用预绑定的函数引用，确保能正确移除
                barcodeInput.removeEventListener("input", this._boundBarcodeInput);
                barcodeInput.removeEventListener("keydown", this._boundBarcodeKeydown);
                barcodeInput.removeEventListener("keypress", this._boundBarcodeKeypress);
                barcodeInput.removeEventListener("blur", this._boundBarcodeBlur);
            }
        });
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
        console.log('[InboundFlow] _onBarcodeInput triggered, value:', value, 'inputType:', ev.inputType);
        if (ev.inputType === "insertLineFeed" || value.includes("\n") || value.includes("\r")) {
            const barcode = value.replace(/\n/g, "").replace(/\r/g, "").trim();
            console.log('[InboundFlow] Barcode detected (input event):', barcode);
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
        console.log('[InboundFlow] _onBarcodeKeydown, key:', ev.key);
        if (ev.key === "Enter") {
            ev.preventDefault();
            const input = ev.target;
            const barcode = input.value.trim();
            console.log('[InboundFlow] Enter pressed, barcode:', barcode);
            if (barcode) {
                input.value = "";
                input.focus();
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
                input.focus();
                this.onBarcodeScanned(barcode);
            }
        }
    }

    _onBarcodeBlur(ev) {
        console.log('[InboundFlow] _onBarcodeBlur, _isProcessing:', this._isProcessing);
        if (!this._isProcessing) {
            console.log('[InboundFlow] Setting timeout to refocus');
            setTimeout(() => this._focusBarcodeInput(), 0);
        }
    }

    _focusBarcodeInput() {
        console.log('[InboundFlow] _focusBarcodeInput called');
        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
            console.log('[InboundFlow] Input focused and cleared');
        } else {
            console.error('[InboundFlow] Cannot focus - input not found');
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
        console.log('[InboundFlow] onBarcodeScanned called, barcode:', barcode, '_isProcessing:', this._isProcessing);
        if (!barcode || this._isProcessing) {
            console.log('[InboundFlow] Skipped - no barcode or still processing');
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;

        try {
            const pickingId = this.state.picking?.id || false;
            const locationId = this.state.currentLocation?.id || false;
            console.log('[InboundFlow] Calling backend, pickingId:', pickingId, 'locationId:', locationId);

            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_incoming_scan_barcode",
                [barcode, pickingId, locationId]
            );

            console.log('[InboundFlow] Backend result:', result);

            await this._applyScanResult(result, true);

            if (result.action?.updated_move_line_ids?.length) {
                this.state.updatedMoveLineIds = result.action.updated_move_line_ids;
            }
        } catch (error) {
            console.error('[InboundFlow] Error:', error);
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._isProcessing = false;
            this._focusBarcodeInput();
        }
    }

    async _applyScanResult(result, notify = true) {
        console.log('[InboundFlow] _applyScanResult called, result:', JSON.stringify(result));
        if (!result) return;

        const scanState = result.scan_state || {};
        console.log('[InboundFlow] scanState:', JSON.stringify(scanState));

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

        console.log('[InboundFlow] State updated - pallets:', this.state.pallets.length, 'picking:', !!this.state.picking);

        this.state.nextStep = result.next_step || "scan_picking";
        console.log('[InboundFlow] nextStep set to:', this.state.nextStep);

        if (notify && result.message) {
            const msgType = result.success === false ? "danger" : "success";
            console.log('[InboundFlow] Showing message:', result.message, 'type:', msgType);
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
    // 操作按钮
    // ═══════════════════════════════════════════════════════════════

    async confirmInbound() {
        if (!this.state.picking) {
            this.showMessage(_t("No picking loaded"), "warning");
            return;
        }
        if (this.state.summary.pending_pallets > 0) {
            this.showMessage(
                _t("There are still ") + this.state.summary.pending_pallets + _t(" pallet(s) not updated"),
                "warning"
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

    // ═══════════════════════════════════════════════════════════════
    // 模板使用的 getter（与 QWeb 模板对应）
    // ═══════════════════════════════════════════════════════════════

    get hasPicking() {
        return !!this.state.picking;
    }

    get pickingLabel() {
        return this.state.picking?.name || "Inbound";
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

    get hasLocation() {
        return !!this.state.currentLocation?.id;
    }

    get currentLocationName() {
        return this.state.currentLocation?.name || "";
    }

    get currentLocationBarcode() {
        return this.state.currentLocation?.barcode || "";
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
