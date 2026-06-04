/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * Inbound Flow Component - 整托入库流程
 *
 * 扫码流程:
 *  1. 扫入库单 (scan_picking)     → 显示入库单详情和托盘列表
 *  2. 扫货位 (scan_location)     → 选择目标货位
 *  3. 扫托盘 (scan_package)      → 更新托盘的目标货位
 *
 * 后端API:
 *  - process_incoming_scan_barcode(barcode, pickingId, locationId)
 *  - get_incoming_scan_state(pickingId, locationId, lastScan)
 */
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
        this._boundOnBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundOnBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundOnVisibilityChange = this._onVisibilityChange.bind(this);

        onMounted(async () => {
            document.addEventListener("visibilitychange", this._boundOnVisibilityChange);
            await this._initScanState();
            this._bindBarcodeInput();
            this._focusBarcodeInput();
        });

        onWillUnmount(() => {
            document.removeEventListener("visibilitychange", this._boundOnVisibilityChange);
            this._unbindBarcodeInput();
        });
    }

    // ═══════════════════════════════════════════════════════════════
    // 扫码输入绑定
    // ═══════════════════════════════════════════════════════════════

    _bindBarcodeInput() {
        const input = this.barcodeInputRef.el;
        if (input) {
            input.addEventListener("input", this._boundOnBarcodeInput);
            input.addEventListener("keydown", this._boundOnBarcodeKeydown);
        }
    }

    _unbindBarcodeInput() {
        const input = this.barcodeInputRef.el;
        if (input) {
            input.removeEventListener("input", this._boundOnBarcodeInput);
            input.removeEventListener("keydown", this._boundOnBarcodeKeydown);
        }
    }

    _onVisibilityChange() {
        if (document.visibilityState === "visible") {
            this._focusBarcodeInput();
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
        const input = this.barcodeInputRef.el;
        if (!input) return;

        const value = input.value;
        console.log("[SBL][input] value=", JSON.stringify(value), "inputType=", ev.inputType);

        // 扫码枪通常会在末尾添加 \n、\r 或 \r\n
        if (value.includes("\n") || value.includes("\r")) {
            const barcode = value.replace(/[\n\r]/g, "").trim();
            console.log("[SBL][input] newline detected, barcode=", barcode);
            if (barcode) {
                this.onBarcodeScanned(barcode);
            }
            input.value = "";
            return;
        }

        // 如果是 insertLineFeed 类型（某些扫码枪）
        if (ev.inputType === "insertLineFeed" || ev.inputType === "insertParagraph") {
            const barcode = value.replace(/[\n\r]/g, "").trim();
            console.log("[SBL][input] insertLineFeed, barcode=", barcode);
            if (barcode) {
                this.onBarcodeScanned(barcode);
            }
            input.value = "";
        }
    }

    _onBarcodeKeydown(ev) {
        console.log("[SBL][keydown] key=", ev.key, "inputType=", ev.inputType);
        // 大多数扫码枪会发送 Enter 键
        if (ev.key === "Enter") {
            ev.preventDefault();
            ev.stopPropagation();
        }

        // 使用 setTimeout 确保 input.value 已经更新
        setTimeout(() => {
            const input = this.barcodeInputRef.el;
            if (!input) return;

            const barcode = (input.value || "").replace(/[\n\r]/g, "").trim();
            console.log("[SBL][keydown] after timeout, value=", JSON.stringify(input.value), "barcode=", barcode);
            if (barcode && barcode.length >= 3) {
                this.onBarcodeScanned(barcode);
            }
            input.value = "";
            this._focusBarcodeInput();
        }, 10);
    }

    // ═══════════════════════════════════════════════════════════════
    // 初始化
    // ═══════════════════════════════════════════════════════════════

    async _initScanState() {
        const context = this.props?.action?.context || {};
        const pickingId = context.pickingId || context.picking_id || false;
        const currentLocationId = context.currentLocationId || context.current_location_id || false;

        if (!pickingId) {
            this._setWorkflowState("scan_picking");
            return;
        }

        try {
            this.state.loading = true;
            console.log("[SBL][loadPicking] calling get_incoming_scan_state, pickingId=", pickingId, "currentLocationId=", currentLocationId);
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "get_incoming_scan_state",
                [pickingId, currentLocationId || false, {}]
            );
            console.log("[SBL][loadPicking] get_incoming_scan_state result=", result);
            this._applyScanResult(result, false);
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
        console.log("[SBL][onBarcodeScanned] START barcode=", barcode);
        if (!barcode || this.state.loading) {
            console.log("[SBL][onBarcodeScanned] SKIP - barcode empty or loading");
            return;
        }

        this.state.loading = true;
        try {
            const pickingId = this.state.picking?.id || false;
            const locationId = this.state.currentLocation?.id || false;
            console.log("[SBL][onBarcodeScanned] calling backend, barcode=", barcode, "pickingId=", pickingId, "locationId=", locationId);

            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_incoming_scan_barcode",
                [barcode, pickingId, locationId]
            );
            console.log("[SBL][onBarcodeScanned] result=", result);

            this._applyScanResult(result, true);

            if (result.action?.updated_move_line_ids?.length) {
                this.state.updatedMoveLineIds = result.action.updated_move_line_ids;
            }

        } catch (error) {
            console.error("[SBL][onBarcodeScanned] ERROR", error);
            this.showMessage(this.formatError(error), "danger");
            this._flashScreen([200, 100, 100], true);
        } finally {
            this.state.loading = false;
            this._focusBarcodeInput();
        }
    }

    _applyScanResult(result, notify = true) {
        console.log("[SBL][_applyScanResult] result=", result);
        if (!result) return;

        const scanState = result.scan_state || {};

        this.state.picking = scanState.picking || null;
        this.state.currentLocation = scanState.current_location || {};
        this.state.summary = scanState.summary || this._getEmptySummary();
        this.state.pallets = scanState.pallets || [];
        this.state.lastScan = scanState.last_scan || {};

        this._setWorkflowState(result.next_step || "scan_picking");

        if (notify && result.message) {
            const msgType = result.success === false ? "danger" : "success";
            this.showMessage(result.message, msgType);

            if (result.success !== false) {
                this._flashScreen([100, 200, 100], false);
            }
        }
    }

    _setWorkflowState(nextStep) {
        console.log("[SBL][_setWorkflowState] nextStep=", nextStep);
        this.state.nextStep = nextStep || "scan_picking";
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
        this._setWorkflowState("scan_picking");
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
