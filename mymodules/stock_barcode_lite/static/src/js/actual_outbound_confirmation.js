/** @odoo-module **/

import { BaseBarcodePage } from "@wd_barcode_lite_core/js/base_barcode_page";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class ActualOutboundConfirmation extends BaseBarcodePage {
    static template = "stock_barcode_lite.ActualOutboundConfirmationPage";
    static props = { ...standardActionServiceProps };

    setup() {
        super.setup();
        this.dialogService = useService("dialog");
        this._dialogOpen = false;
        this._dialogNextAction = null;
        this.state.outboundCode = "";
        this.state.outboundOrderId = false;
        this.state.confirmationId = false;
        this.state.confirmationMode = "";
        this.state.destinationPallets = [];
        this.state.summary = this._emptySummary();
        this.state.nextStep = "scan_outbound";
    }

    get stepHint() {
        const hints = {
            scan_outbound: _t("Scan the outbound order barcode to open its active confirmation"),
            scan_destination_pallet: _t("Scan destination pallets, then validate this confirmation batch"),
            confirm_unpacked: _t("Only unpackaged goods remain in the current confirmation"),
        };
        return hints[this.state.nextStep] || hints.scan_outbound;
    }

    get stepLabel() {
        const labels = {
            scan_outbound: _t("Scan Order"),
            scan_destination_pallet: _t("Scan Pallets"),
            confirm_unpacked: _t("Confirm Loose Goods"),
        };
        return labels[this.state.nextStep] || labels.scan_outbound;
    }

    get remainingDestinationPallets() {
        return Math.max(
            0,
            (this.state.summary.total_destination_pallets || 0) -
                (this.state.summary.scanned_destination_pallets || 0)
        );
    }

    async onBarcodeScanned(barcode) {
        if (!barcode || this.state.loading || this._isProcessing || this._dialogOpen) {
            return;
        }

        if (this.state.nextStep === "confirm_unpacked") {
            this.showMessage(
                _t("Only unpackaged goods remain. Use the confirmation button to continue."),
                "warning"
            );
            this._focusBarcodeInput();
            return;
        }

        const isPalletScan =
            this.state.nextStep === "scan_destination_pallet" && Boolean(this.state.confirmationId);
        if (this.state.nextStep === "complete") {
            this._resetConfirmationState();
        }

        this._isProcessing = true;
        this.state.loading = true;
        this.showMessage(_t("Processing..."), "info");
        try {
            const args = isPalletScan
                ? [barcode, this.state.confirmationId]
                : [barcode];
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "process_outbound_confirmation_scan",
                args
            );
            if (this._isDestroyed) {
                return;
            }

            if (!isPalletScan) {
                this.state.outboundCode = barcode;
            }
            this._applyScanResult(result);
            if (this.state.nextStep === "confirm_unpacked") {
                this._showUnpackedOnlyDialog();
            }
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
                this._flashScreen([200, 100, 100], true);
            }
        } finally {
            this._isProcessing = false;
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
        }
    }

    _applyScanResult(result) {
        if (!result) {
            return;
        }
        if (result.next_step === "complete") {
            this._resetConfirmationState();
            this.showMessage(_t("This outbound order is already complete. Scan the next order."), "success");
            return;
        }
        const current = result.current || {};
        const confirmation = result.confirmation || {};
        this.state.outboundOrderId = current.outbound_order_id || this.state.outboundOrderId || false;
        this.state.confirmationId =
            current.confirmation_id || confirmation.id || this.state.confirmationId || false;
        this.state.confirmationMode = confirmation.mode || this.state.confirmationMode || "";
        this.state.destinationPallets = Array.isArray(result.destination_pallets)
            ? result.destination_pallets.map((pallet) => ({ ...pallet }))
            : [];
        this.state.summary = { ...this._emptySummary(), ...(result.summary || {}) };
        this.state.nextStep = result.next_step || "scan_outbound";

        if (result.message) {
            this.showMessage(result.message, result.success === false ? "danger" : "success");
        }
    }

    validateConfirmation() {
        if (this.state.loading || !this.state.confirmationId) {
            return;
        }
        if (!(this.state.summary.scanned_destination_pallets || 0)) {
            this.showMessage(_t("Scan at least one destination pallet before validating."), "warning");
            this._focusBarcodeInput();
            return;
        }

        if (this.remainingDestinationPallets > 0) {
            this._showUnscannedPalletDialog();
            return;
        }
        this._continueOutboundAfterPalletCheck();
    }

    _continueOutboundAfterPalletCheck() {
        if ((this.state.summary.unpackaged_move_lines || 0) > 0) {
            this._showIncludeUnpackedDialog();
        } else {
            this._confirmBatch(false);
        }
    }

    _showUnscannedPalletDialog() {
        if (this._dialogOpen) {
            return;
        }
        this._dialogOpen = true;
        this._dialogNextAction = null;
        this.dialogService.add(
            ConfirmationDialog,
            {
                title: _t("Destination pallets remain"),
                body:
                    _t("There are ") +
                    this.remainingDestinationPallets +
                    _t(" destination pallet(s) that have not been scanned."),
                confirmLabel: _t("Continue outbound"),
                cancelLabel: _t("Continue scanning"),
                confirmClass: "btn-primary",
                confirm: () => {
                    this._dialogNextAction = () => this._continueOutboundAfterPalletCheck();
                },
                cancel: () => {},
            },
            {
                onClose: () => {
                    const nextAction = this._dialogNextAction;
                    this._dialogNextAction = null;
                    this._dialogOpen = false;
                    if (this._isDestroyed) {
                        return;
                    }
                    if (nextAction) {
                        nextAction();
                    } else {
                        this._focusBarcodeInput();
                    }
                },
            }
        );
    }

    _showIncludeUnpackedDialog() {
        if (this._dialogOpen) {
            return;
        }
        this._showDecisionDialog({
            title: _t("Confirm outbound"),
            body: _t("Ship unpackaged goods together with the scanned destination pallets?"),
            confirmLabel: _t("Pallets and loose goods"),
            cancelLabel: _t("Pallets only"),
            confirm: () => this._confirmBatch(true),
            cancel: () => this._confirmBatch(false),
        });
    }

    _showUnpackedOnlyDialog() {
        if (this._dialogOpen || this.state.nextStep !== "confirm_unpacked") {
            return;
        }
        this._showDecisionDialog({
            title: _t("Confirm outbound"),
            body: _t("Only unpackaged goods remain. Confirm outbound in one step?"),
            confirmLabel: _t("Confirm outbound"),
            cancelLabel: _t("Cancel"),
            confirm: () => this._confirmBatch(true),
            cancel: () => {},
        });
    }

    _showDecisionDialog({ title, body, confirmLabel, cancelLabel, confirm, cancel }) {
        this._dialogOpen = true;
        this._dialogNextAction = null;
        this.dialogService.add(
            ConfirmationDialog,
            {
                title,
                body,
                confirmLabel,
                cancelLabel,
                confirmClass: "btn-primary",
                confirm,
                cancel,
            },
            {
                onClose: () => {
                    const nextAction = this._dialogNextAction;
                    this._dialogNextAction = null;
                    this._dialogOpen = false;
                    if (this._isDestroyed) {
                        return;
                    }
                    if (nextAction) {
                        nextAction();
                    } else if (!this.state.loading) {
                        this._focusBarcodeInput();
                    }
                },
            }
        );
    }

    confirmUnpacked() {
        console.log(this.state)
        if (this.state.nextStep === "confirm_unpacked") {
            this._showUnpackedOnlyDialog();
        }
    }

    async _confirmBatch(includeUnpackedLines) {
        console.log(this.state,'11h')
        const confirmationId = this.state.confirmationId;
        if (!confirmationId || this.state.loading || this._isProcessing) {
            return;
        }

        this._isProcessing = true;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "stock.barcode.lite.scan.service",
                "action_confirm_outbound_confirmation",
                [confirmationId, includeUnpackedLines]
            );
            if (this._isDestroyed) {
                return;
            }

            const confirmationResult = Array.isArray(result) ? result[0] : result;
            if (!confirmationResult) {
                throw new Error(_t("The outbound confirmation returned no result."));
            }

            if (confirmationResult.next_step === "complete") {
                this._resetConfirmationState();
                this.showMessage(_t("Outbound order fully confirmed. Scan the next order."), "success");
                this._flashScreen([100, 250, 100], true);
                return;
            }

            if (this.state.outboundCode) {
                const nextResult = await this.orm.call(
                    "stock.barcode.lite.scan.service",
                    "process_outbound_confirmation_scan",
                    [this.state.outboundCode]
                );
                if (this._isDestroyed) {
                    return;
                }
                this._applyScanResult(nextResult);
                if (this.state.nextStep === "confirm_unpacked") {
                    if (this._dialogOpen) {
                        this._dialogNextAction = () => this._showUnpackedOnlyDialog();
                    } else {
                        this._showUnpackedOnlyDialog();
                    }
                }
            } else {
                this.state.confirmationId = confirmationResult.next_confirmation_id || false;
                this.state.nextStep = confirmationResult.next_step || "complete";
                this.showMessage(_t("Batch confirmed. Scan the next step to continue."), "success");
                if (this.state.nextStep === "confirm_unpacked") {
                    this._showUnpackedOnlyDialog();
                }
            }
            this._flashScreen([100, 200, 100], false);
        } catch (error) {
            if (!this._isDestroyed) {
                this.showMessage(this.formatError(error), "danger");
                this._flashScreen([200, 100, 100], true);
            }
        } finally {
            this._isProcessing = false;
            if (!this._isDestroyed) {
                this.state.loading = false;
                this._focusBarcodeInput();
            }
        }
    }

    _resetConfirmationState() {
        this.state.outboundCode = "";
        this.state.outboundOrderId = false;
        this.state.confirmationId = false;
        this.state.confirmationMode = "";
        this.state.destinationPallets = [];
        this.state.summary = this._emptySummary();
        this.state.nextStep = "scan_outbound";
        this.state.message = "";
        this.state.messageType = "info";
    }

    _emptySummary() {
        return {
            total_destination_pallets: 0,
            scanned_destination_pallets: 0,
            unpackaged_move_lines: 0,
        };
    }
}
