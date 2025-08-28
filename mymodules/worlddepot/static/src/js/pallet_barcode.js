odoo.define('worlddepot.pallet_barcode', function(require) {
    "use strict";

    // Get required components and services
    const { Component } = owl;
    const { useRef, onMounted, onWillUpdate } = owl.hooks;
    const PackageLineComponent = require('stock_barcode.PackageLineComponent');
    const rpc = require('web.rpc');
    const core = require('web.core');
    const _t = core._t;

    // Patch the PackageLineComponent to add pallet scanning
    PackageLineComponent.patch('worlddepot.pallet_barcode.PatchedPackageLine', T =>
        class extends T {
            /**
             * Setup component with custom logic
             */
            setup() {
                super.setup();

                // Reference to the component's DOM element
                this.rootRef = useRef("root");

                // State for pallet scanning
                this.state = useState({
                    loading: false,
                    result: null
                });

                // Add our button when component mounts
                onMounted(() => this.addPalletScanButton());

                // Update button when component updates
                onWillUpdate(() => {
                    if (this.rootRef.el) {
                        this.addPalletScanButton();
                    }
                });
            }

            /**
             * Add the pallet scan button to the component
             */
            addPalletScanButton() {
                // Check if button already exists
                const existingButton = this.rootRef.el.querySelector('.o_pallet_scan_btn');
                if (existingButton) return;

                // Create button container
                const buttonContainer = document.createElement('div');
                buttonContainer.className = 'o_pallet_section';

                // Create scan button
                const scanButton = document.createElement('button');
                scanButton.className = 'btn btn-primary o_pallet_scan_btn';
                scanButton.innerHTML = '<i class="fa fa-barcode"></i> ' + _t('Scan Pallet');

                // Add click handler
                scanButton.addEventListener('click', ev => {
                    ev.stopPropagation();
                    this.handlePalletScan();
                });

                // Add to DOM
                buttonContainer.appendChild(scanButton);

                // Insert after package name element
                const packageNameEl = this.rootRef.el.querySelector('.o_package_name');
                if (packageNameEl) {
                    packageNameEl.after(buttonContainer);
                }
            }

            /**
             * Handle pallet scanning process
             */
            async handlePalletScan() {
                try {
                    // Get barcode from user
                    const barcode = prompt(_t("Scan Pallet Barcode"), "");
                    if (!barcode) return;

                    // Show loading state
                    this.state.loading = true;
                    this.state.result = null;

                    // Make RPC call to update pallet
                    const result = await rpc.route('/stock_barcode/update_pallet', {
                        pallet_barcode: barcode,
                        package_id: this.props.line.package_id.id
                    });

                    // Update state
                    this.state.loading = false;
                    this.state.result = result;

                    // Update package name if needed
                    if (result.success && result.package_name) {
                        this.props.line.package_id.name = result.package_name;
                        this.render();
                    }

                    // Remove result after delay
                    setTimeout(() => {
                        this.state.result = null;
                    }, 5000);
                } catch (error) {
                    this.state.loading = false;
                    this.state.result = {
                        success: false,
                        message: _t("Pallet scan failed")
                    };
                    console.error("Pallet scan error:", error);
                }
            }

            /**
             * Override to add our result display
             */
            _render() {
                super._render();

                // Add result display if needed
                if (this.state.result) {
                    const resultEl = document.createElement('div');
                    resultEl.className = `alert alert-${this.state.result.success ? 'success' : 'danger'}`;
                    resultEl.textContent = this.state.result.message;

                    // Find and add after pallet button
                    const button = this.rootRef.el.querySelector('.o_pallet_scan_btn');
                    if (button) {
                        button.parentNode.after(resultEl);
                    }
                }
            }
        }
    );
});