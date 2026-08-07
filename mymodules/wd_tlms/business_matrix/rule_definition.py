RESULT_PASS = 'pass'
RESULT_WARNING = 'warning'
RESULT_BLOCK = 'block'

SCENE_S_CODES = {
    'terminal_to_warehouse': 'S1',
    'terminal_to_customer': 'S2',
    'warehouse_to_customer': 'S3',
    'customer_to_customer': 'S4',
    'warehouse_transfer': 'S5',
    'customer_to_warehouse': 'S6',
    'container_swap': 'S7',
    'empty_depot': 'S8',
}

BUSINESS_DRIVER = {'plan_driven': 'B1', 'commercial': 'B2'}
CARGO_CATEGORY = {'container': 'C1', 'pallet': 'C2', 'piece': 'C3'}
CARRIER_TYPE = {'own_fleet': 'D1', 'truck': 'D2', 'courier': 'D3'}
T1_ATTRIBUTE = {'t1': 'E1', 'normal': 'E2'}
DG_ATTRIBUTE = {'dg': 'F1', 'normal': 'F2'}
