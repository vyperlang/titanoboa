# Deployment Tracking in Titanoboa

Titanoboa provides a deployment tracking system that automatically logs contract deployments when working in network mode. This feature helps you keep track of deployed contracts, their addresses, transaction details, and source code for later verification and querying.

## Overview

The deployment tracking system uses SQLite to store deployment information including:
- Contract address and name
- Source filename
- RPC endpoint URL
- Deployer address
- Transaction hash and timestamp
- Full transaction and receipt data
- Contract source code and ABI
- Session ID for grouping related deployments

This data can be used later for contract verification on block explorers like Etherscan.

## Enabling Deployment Logging

To enable deployment logging, you must explicitly initialize a deployments database:

```python
import boa
from boa.deployments import DeploymentsDB, set_deployments_db

# Enable with default in-memory database (data lost when program exits)
set_deployments_db(DeploymentsDB())

# Enable with persistent database file
set_deployments_db(DeploymentsDB("./deployments.db"))
```

Note: The default database (when no path is provided) is `:memory:`, which creates an in-memory SQLite database.

## Usage Examples

### Basic Usage

```python
import boa
from boa.deployments import DeploymentsDB, set_deployments_db

# Set up deployment tracking with persistent storage
set_deployments_db(DeploymentsDB("./deployments.db"))

# Set up network connection
boa.set_network_env("http://localhost:8545")

# Deploy a contract - automatically logged
contract = boa.load("contracts/MyContract.vy", arg1, arg2)

# All deployments are tracked
another_contract = boa.loads("""
@external
def hello() -> String[32]:
    return "Hello, World!"
""")
```

### Context Manager Usage (Optional)

You can also use `set_deployments_db()` as a context manager to temporarily set the global deployments database:

```python
with set_deployments_db(DeploymentsDB("./temp_deployments.db")):
    # Deployments here are tracked to temp_deployments.db
    contract = boa.load("contracts/MyContract.vy")
# Global deployments db is restored to previous value after context
```

### Querying Deployments

```python
from boa.deployments import DeploymentsDB

# Open existing database
db = DeploymentsDB("./deployments.db")

# Get all deployments (most recent first)
for deployment in db.get_deployments():
    print(f"Contract: {deployment.contract_name}")
    print(f"Address: {deployment.contract_address}")
    print(f"Deployed by: {deployment.deployer}")
    print(f"TX Hash: {deployment.tx_hash}")
    print(f"Timestamp: {deployment.broadcast_ts}")
    print("---")

# Convert to list for easier manipulation
all_deployments = list(db.get_deployments())
```

### Working with Deployment Data

Each deployment object contains:

```python
deployment.contract_address  # The deployed contract address
deployment.contract_name     # Contract name (from source or auto-generated)
deployment.filename          # Source file path
deployment.rpc              # RPC endpoint used for deployment
deployment.deployer         # Address that deployed the contract
deployment.tx_hash          # Deployment transaction hash
deployment.broadcast_ts     # Unix timestamp of deployment
deployment.tx_dict          # Raw transaction data
deployment.receipt_dict     # Raw transaction receipt
deployment.source_code      # Contract source bundle (if available)
deployment.abi              # Contract ABI (if available)
deployment.session_id       # Unique session identifier
deployment.deployment_id    # Database primary key
```

### Exporting Deployment Data

```python
# Export single deployment to JSON
deployment_json = deployment.to_json(indent=2)

# Export to dict for custom processing
deployment_dict = deployment.to_dict()
```

### Using for Contract Verification

The stored deployment data includes everything needed for contract verification on block explorers:

```python
# Get deployment for verification
deployment = next(db.get_deployments())

# Access data needed for verification
contract_address = deployment.contract_address
source_code = deployment.source_code  # Full source bundle
abi = deployment.abi
constructor_args = deployment.tx_dict["data"]  # Contains constructor arguments
```

## Important Notes

1. **Manual Initialization Required**: Deployment logging is NOT enabled by default. You must explicitly call `set_deployments_db()`.

2. **Network Mode Only**: Deployment tracking only works when using network mode (`boa.set_network_env()`). Local deployments using the built-in EVM are not tracked.

3. **Database Location**: When using a file-based database, the parent directory will be created automatically if it doesn't exist.

4. **Session Tracking**: Each Python session gets a unique session ID, allowing you to group deployments from the same session.

5. **Default Database**: When `DeploymentsDB()` is called without arguments, it creates an in-memory database (`:memory:`).

## Database Schema

The deployments are stored in a SQLite database with the following schema:

```sql
CREATE TABLE deployments(
    deployment_id integer primary key autoincrement,
    session_id text,
    contract_address text,
    contract_name text,
    filename text,
    rpc text,
    deployer text,
    tx_hash text,
    broadcast_ts real,
    tx_dict text,
    receipt_dict text,
    source_code text,
    abi text
);
```