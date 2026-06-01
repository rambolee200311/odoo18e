/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";

/**
 * Inbound Flow Component
 *
 * 扫码流程：
 *  ─────────────────────────────────────────────────────────────────────
 *  入库: 扫库位号 → 扫托盘号(可多个) → 下一库位 → 确认入库
 *  ─────────────────────────────────────────────────────────────────────
 *
 * 核心逻辑：
 *  1. 扫库位号 → 激活该库位，加载该库位待绑定的托盘列表
 *  2. 扫托盘号 → 调用后端API，验证并绑定托盘到当前库位
 *  3. 库位内所有托盘绑定完成 → 自动跳转到下一库位
 *  4. 所有库位完成 → 可点击确认入库
 */
export class InboundFlow extends Component {
    static template = "stock_barcode_lite.InboundPage";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            /** 当前入库单ID（由后端传入或从上下文获取） */
            order: null,
            orderId: null,
            /** locations: [{ location_code, expected_pallets: [], bound_pallets: Set, is_complete: false }] */
            locations: [],
            currentLocationIndex: -1,
            scanMode: "location",  // "location" | "pallet"
            message: "",
            messageType: "info",
            loading: false,
        });

        this.barcodeInputRef = useRef("barcodeInput");

        onMounted(async () => {
            this._bindVisibilityChange();
            await this._initOrder();
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

    // 加载
    async _initOrder() {
        // 从上下文或props获取当前入库单ID！！！！！！！！！！！
        // 暂时通过搜索最新待处理的入库单来演示
        // 实际使用时应该从URL参数或context传入
        const activeId = await this._getActiveOrderId();
        if (activeId) {
            await this.loadOrder(activeId);
        }
    }

    async _getActiveOrderId() {
        // 实现从上下文获取当前入库单ID！！！！！！！！！！！！！！
        // 例如从 actionMenager 或 context 获取
        // 目前返回 null，等待后端配合传参
        return null;
    }

    // 加载库位对应订单
    async loadOrder(orderId) {
        this.state.loading = true;
        try {
            const orders = await this.orm.searchRead(
                "world.depot.inbound.order",
                [["id", "=", orderId]],
                ["id", "reference", "state"],
                { limit: 1 }
            );
            if (orders.length === 0) {
                throw new Error("Inbound order not found");
            }
            const order = orders[0];
            if (order.state === "done" || order.state === "cancel") {
                throw new Error("Inbound order state is " + order.state);
            }
            this.state.order = order;
            this.state.orderId = orderId;
            await this.loadLocations(orderId);
            this.showMessage(
                "Loaded " + order.reference + " — " + this.state.locations.length + " location(s)",
                "success"
            );
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
        } finally {
            this.state.loading = false;
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

    _focusBarcodeInput() {
        const input = this.barcodeInputRef.el;
        if (input) {
            input.focus();
            input.value = "";
        }
    }

    // 触发 识别码信息
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

    // 触发 识别码信息
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

    // 扫描
    async onBarcodeScanned(barcode) {
        if (!barcode || this.state.loading) return;
        this.state.loading = true;
        try {
            switch (this.state.scanMode) {
                // 扫库位
                case "location": await this.scanLocation(barcode); break;
                // 扫托盘
                case "pallet":  await this.scanPallet(barcode);  break;
            }
        } catch (error) {
            this.showMessage(this.formatError(error), "danger");
        } finally {
            this.state.loading = false;
        }
    }

    // ════════════════════════════════════════════
    // 阶段1: 扫库位号
    // ════════════════════════════════════════════
    async scanLocation(barcode) {
        if (!this.state.orderId) {
            throw new Error("No inbound order loaded. Please load an order first.");
        }

        // 验证库位是否存在于当前订单中
        const loc = this.state.locations.find(l => l.location_code === barcode);
        if (!loc) {
            throw new Error("Location " + barcode + " not found in this order");
        }
        if (loc.is_complete) {
            throw new Error("Location " + barcode + " already complete");
        }

        const index = this.state.locations.indexOf(loc);
        this.state.currentLocationIndex = index;
        this.state.scanMode = "pallet";
        const remaining = loc.expected_pallets.filter(p => !loc.bound_pallets.has(p)).length;
        this.showMessage(
            "Location [" + loc.location_code + "] — " + remaining + " pallet(s) to bind",
            "success"
        );
        this.flashScreen();
    }

    // ════════════════════════════════════════════
    // 阶段2: 扫托盘号（调用后端API绑定）
    // ════════════════════════════════════════════
    async scanPallet(barcode) {
        const loc = this.state.locations[this.state.currentLocationIndex];
        if (!loc) {
            throw new Error("No location selected");
        }

        // 检查是否已经绑定过
        if (loc.bound_pallets.has(barcode)) {
            throw new Error("Pallet " + barcode + " already scanned in this location");
        }

        // 检查托盘是否在该库位的预期列表中
        if (!loc.expected_pallets.includes(barcode)) {
            throw new Error("Pallet " + barcode + " not expected in location [" + loc.location_code + "]");
        }

        // 调用后端API进行绑定
        try {
            await this.orm.call(
                "world.depot.inbound.order",
                "action_bind_pallet_to_location",
                [this.state.orderId],
                {
                    location_code: loc.location_code,
                    pallet_no: barcode,
                }
            );

            // 绑定成功，更新前端状态
            loc.bound_pallets.add(barcode);

            // 检查该库位是否全部完成
            const remaining = loc.expected_pallets.filter(p => !loc.bound_pallets.has(p)).length;
            if (remaining === 0) {
                loc.is_complete = true;
                this.showMessage(
                    "Location [" + loc.location_code + "] complete!",
                    "success"
                );
                this.flashScreen([100, 200, 100], true);
                this._advanceToNextLocation();
                return;
            }

            this.showMessage(
                "Pallet [" + barcode + "] bound — " + remaining + " pallet(s) remaining",
                "success"
            );
            this.flashScreen();

        } catch (error) {
            // 后端返回的错误
            throw error;
        }
    }

    // ════════════════════════════════════════════
    // 加载库位和托盘数据
    // ════════════════════════════════════════════
    async loadLocations(orderId) {
        const lines = await this.orm.searchRead(
            "world.depot.inbound.order.product",
            [["inbound_order_id", "=", orderId]],
            ["id", "pallet_no", "location_code"],
            { limit: 2000 }
        );

        // 按库位号分组，记录每个库位预期绑定的托盘
        const locMap = new Map();
        for (const line of lines) {
            const lc = line.location_code || "";
            if (!locMap.has(lc)) {
                locMap.set(lc, {
                    location_code: lc,
                    expected_pallets: [],   // 该库位预期要绑定的托盘列表
                    bound_pallets: new Set(), // 已扫描绑定成功的托盘
                    is_complete: false,
                });
            }
            const palletNo = line.pallet_no || "";
            if (palletNo && !locMap.get(lc).expected_pallets.includes(palletNo)) {
                locMap.get(lc).expected_pallets.push(palletNo);
            }
        }

        this.state.locations = Array.from(locMap.values());
        this.state.currentLocationIndex = -1;
    }

    // ════════════════════════════════════════════
    // 辅助方法
    // ════════════════════════════════════════════

    _advanceToNextLocation() {
        const nextIndex = this.state.locations.findIndex(
            (l, i) => i > this.state.currentLocationIndex && !l.is_complete
        );
        if (nextIndex !== -1) {
            this.state.currentLocationIndex = nextIndex;
            this.state.scanMode = "pallet";
            const loc = this.state.locations[nextIndex];
            const remaining = loc.expected_pallets.filter(p => !loc.bound_pallets.has(p)).length;
            this.showMessage(
                "Next location [" + loc.location_code + "] — " + remaining + " pallet(s)",
                "info"
            );
        } else {
            this.state.currentLocationIndex = -1;
            this.state.scanMode = "location";
            if (this.isAllComplete) {
                this.showMessage("All locations complete! Confirm inbound.", "success");
            }
        }
    }

    /**
     * 跳过当前库位
     */
    skipCurrentLocation() {
        const loc = this.state.locations[this.state.currentLocationIndex];
        if (loc) {
            loc.is_complete = true;
        }
        this._advanceToNextLocation();
    }

    /**
     * 确认入库 - 调用后端方法完成入库
     */
    async confirmInbound() {
        if (!this.state.orderId) {
            this.showMessage("No inbound order loaded", "danger");
            return;
        }
        if (!this.isAllComplete) {
            const remaining = this.state.locations
                .filter(l => !l.is_complete)
                .map(l => l.location_code)
                .join(", ");
            throw new Error(
                this.state.locations.filter(l => !l.is_complete).length +
                " location(s) incomplete: " + remaining
            );
        }
        this.state.loading = true;
        try {
            // 后端需要实现确认入库的方法！！！！！！！！！！！！
            // await this.orm.call(
            //     "world.depot.inbound.order",
            //     "action_confirm_inbound",
            //     [this.state.orderId],
            //     {}
            // );

            this.showMessage("Inbound confirmed! Binding saved.", "success");
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
        this.state.orderId = null;
        this.state.locations = [];
        this.state.currentLocationIndex = -1;
        this.state.scanMode = "location";
        this.state.message = "";
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
            "Unknown error"
        );
    }

    // ── 计算属性 ─────────────────────────────────

    get progressPercent() {
        if (!this.state.locations.length) return 0;
        const done = this.state.locations.filter(l => l.is_complete).length;
        return Math.round((done / this.state.locations.length) * 100);
    }

    get isAllComplete() {
        return (
            this.state.locations.length > 0 &&
            this.state.locations.every(l => l.is_complete)
        );
    }

    get currentLocation() {
        if (this.state.currentLocationIndex < 0) return null;
        return this.state.locations[this.state.currentLocationIndex] || null;
    }

    get scanModeLabel() {
        const map = {
            location: "Scan Location Code",
            pallet:   "Scan Pallet Barcode",
        };
        return map[this.state.scanMode] || this.state.scanMode;
    }

    /**
     * 获取当前库位剩余待绑定的托盘数量
     */
    get remainingPalletsCount() {
        const loc = this.currentLocation;
        if (!loc) return 0;
        return loc.expected_pallets.filter(p => !loc.bound_pallets.has(p)).length;
    }
}
