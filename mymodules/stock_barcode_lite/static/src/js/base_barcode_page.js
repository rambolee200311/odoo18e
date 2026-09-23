/**
 * BaseBarcodePage - 扫码页面基类
 * 整合所有通用方法，避免代码重复
 */
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class BaseBarcodePage extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.barcodeInputRef = useRef("barcodeInput");

        this.state = useState({
            loading: false,
            message: "",
            messageType: "info",
        });

        this._isProcessing = false;
        this._messageTimer = null;
        this._isPDA = this._detectPDA();

        this._isDestroyed = false;
        this._pendingTimers = [];
        this._scanTimer = null;

        this._boundOnBarcodeInput = this._onBarcodeInput.bind(this);
        this._boundOnBarcodeKeydown = this._onBarcodeKeydown.bind(this);
        this._boundOnBarcodeBlur = this._onBarcodeBlur.bind(this);

        onMounted(() => {
            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.addEventListener("input", this._boundOnBarcodeInput);
                barcodeInput.addEventListener("keydown", this._boundOnBarcodeKeydown);
                barcodeInput.addEventListener("blur", this._boundOnBarcodeBlur);
                this._focusBarcodeInput();
            }
        });

        onWillUnmount(() => {
            this._isDestroyed = true;  // 添加这行

            const barcodeInput = this.barcodeInputRef.el;
            if (barcodeInput) {
                barcodeInput.removeEventListener("input", this._boundOnBarcodeInput);
                barcodeInput.removeEventListener("keydown", this._boundOnBarcodeKeydown);
                barcodeInput.removeEventListener("blur", this._boundOnBarcodeBlur);
            }

            // 清理所有安全定时器
            for (const id of this._pendingTimers) {
                clearTimeout(id);
            }
            this._pendingTimers = [];
            this._messageTimer = null;
        });

    }

    // ═══════════════════════════════════════════════════════════════
    // 设备检测
    // ═══════════════════════════════════════════════════════════════

    _detectPDA() {
        const hasFinePointer = window.matchMedia("(pointer: fine)").matches;
        const hasHover = window.matchMedia("(hover: hover)").matches;
        const isSmallScreen = window.matchMedia("(max-width: 768px)").matches;
        const hasTouchScreen =
            "ontouchstart" in window ||
            navigator.maxTouchPoints > 0 ||
            window.matchMedia("(pointer: coarse)").matches;

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

    _onBarcodeBlur() {
        setTimeout(() => this._focusBarcodeInput(), 0);
    }

    _focusBarcodeInput() {
        if (this._isDestroyed) {
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

    _clearScanTimer() {
        if (this._scanTimer) {
            clearTimeout(this._scanTimer);
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // 通知和提示
    // ═══════════════════════════════════════════════════════════════

    showMessage(text, type = "info") {
        if (this._isDestroyed) {
            return;
        }

        this.state.message = text;
        this.state.messageType = type;

        this._clearSafeTimeout(this._messageTimer);
        this._messageTimer = null;

        if (type !== "danger") {
            this._messageTimer = this._safeSetTimeout(() => {
                this._messageTimer = null;

                if (
                    !this._isDestroyed &&
                    this.state.message === text
                ) {
                    this.state.message = "";
                }
            }, 4000);
        }
    }

    _flashScreen(pattern, repeat) {
        if (!("vibrate" in navigator)) {
            return;
        }

        try {
            navigator.vibrate(repeat ? pattern : 100);
        } catch (error) {
            console.warn("[BaseBarcodePage] vibrate failed:", error);
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
    // 状态标签
    // ═══════════════════════════════════════════════════════════════

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

    // ═══════════════════════════════════════════════════════════════
    // 通用辅助
    // ═══════════════════════════════════════════════════════════════

    _safeSetTimeout(fn, delay) {
        if (this._isDestroyed) {
            return null;
        }

        const id = setTimeout(() => {
            const index = this._pendingTimers.indexOf(id);
            if (index !== -1) {
                this._pendingTimers.splice(index, 1);
            }

            if (!this._isDestroyed) {
                fn();
            }
        }, delay);

        this._pendingTimers.push(id);
        return id;
    }

    _clearSafeTimeout(id) {
        if (id === null || id === undefined) {
            return;
        }

        const index = this._pendingTimers.indexOf(id);
        if (index !== -1) {
            this._pendingTimers.splice(index, 1);
        }

        clearTimeout(id);
    }

    exit() {
        this.action.doAction("stock_barcode_lite_homepage");
    }
}