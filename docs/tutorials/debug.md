# Debugging contracts

Titanoboa provides several tools for debugging contracts during development and testing.

## Using print statements

The simplest debugging tool is Vyper's built-in `print` function:

```vyper
# debug_example.vy
@external
def calculate(x: uint256, y: uint256) -> uint256:
    print("Starting calculation with x=", x, "y=", y)
    
    result: uint256 = x * y + 100
    print("Intermediate result:", result)
    
    if result > 1000:
        print("Result is large, applying adjustment")
        result = result // 2
    
    print("Final result:", result)
    return result
```

```python
import boa

contract = boa.load("debug_example.vy")
result = contract.calculate(50, 30)
```

Output:
```
Starting calculation with x= 50 y= 30
Intermediate result: 1600
Result is large, applying adjustment
Final result: 800
```

## Understanding stack traces

When errors occur, Titanoboa provides detailed stack traces that include the Vyper source context:

```python
import boa

contract = boa.loads("""
owner: address

@deploy
def __init__():
    self.owner = msg.sender

@external
def withdraw(amount: uint256):
    assert msg.sender == self.owner, "Only owner can withdraw"
    assert amount <= self.balance, "Insufficient balance"
    send(msg.sender, amount)
""")

# This will fail with a detailed stack trace
user = boa.env.generate_address()
with boa.env.prank(user):
    contract.withdraw(100)  # BoaError: Only owner can withdraw
```

## Testing expected errors

Use `boa.reverts` to test that contracts fail correctly:

```python
import boa

contract = boa.loads("""
balances: HashMap[address, uint256]

@external
def transfer(to: address, amount: uint256):
    assert self.balances[msg.sender] >= amount, "Insufficient balance"
    self.balances[msg.sender] -= amount
    self.balances[to] += amount
""")

# Test that transfer fails with insufficient balance
with boa.reverts("Insufficient balance"):
    contract.transfer(boa.env.generate_address(), 1000)
```

## Inspecting contract state with eval

The `eval` method allows you to execute Vyper expressions in the contract's context:

```python
contract = boa.loads("""
struct Position:
    amount: uint256
    entry_time: uint256
    is_active: bool

positions: HashMap[address, Position]
total_positions: uint256

@external
def open_position(amount: uint256):
    self.positions[msg.sender] = Position(
        amount=amount,
        entry_time=block.timestamp,
        is_active=True
    )
    self.total_positions += 1
""")

# Open a position
contract.open_position(1000)

# Inspect the position using eval
print("Total positions:", contract.eval("self.total_positions"))
print("My position:", contract.eval("self.positions[msg.sender]"))
print("Position amount:", contract.eval("self.positions[msg.sender].amount"))
```

## Storage introspection

For deeper debugging, access storage variables directly:

```python
contract = boa.loads("""
owner: address
paused: bool
fee_rate: uint256
balances: HashMap[address, uint256]

@deploy
def __init__():
    self.owner = msg.sender
    self.fee_rate = 300  # 3%
""")

# Inspect all storage variables
print("Storage dump:", contract._storage.dump())

# Access specific variables
print("Owner:", contract._storage.owner)
print("Fee rate:", contract._storage.fee_rate)
```

## Debugging multi-step processes

Use anchoring to create checkpoints in complex transactions:

```python
contract = boa.loads("""
stages_completed: uint256
data: DynArray[uint256, 100]

@external
def process_stage_1(input: uint256):
    self.data.append(input * 2)
    self.stages_completed = 1

@external
def process_stage_2(input: uint256):
    assert self.stages_completed >= 1, "Stage 1 not completed"
    self.data.append(input * 3)
    self.stages_completed = 2
""")

# Debug with checkpoints
with boa.env.anchor():
    contract.process_stage_1(10)
    print("After stage 1:", contract.eval("self.data"))
    
    with boa.env.anchor():
        contract.process_stage_2(20)
        print("After stage 2:", contract.eval("self.data"))
    # Inner anchor reverts
    
    print("Back to stage 1:", contract.eval("self.data"))
```

## Time-dependent debugging

Test time-based logic using `time_travel`:

```python
contract = boa.loads("""
start_time: uint256
end_time: uint256

@deploy
def __init__(duration: uint256):
    self.start_time = block.timestamp
    self.end_time = block.timestamp + duration

@external
@view
def is_active() -> bool:
    return block.timestamp >= self.start_time and block.timestamp < self.end_time
""", 3600)  # 1 hour duration

print("Active:", contract.is_active())  # True

# Advance time
boa.env.time_travel(seconds=3700)
print("Active after expiry:", contract.is_active())  # False
```

## Event debugging

Use events for debugging complex operations:

```python
contract = boa.loads("""
event Debug:
    message: String[100]
    value: uint256

@external
def process(input: uint256):
    log Debug("Starting process", input)
    
    result: uint256 = input * 2
    
    log Debug("Process complete", result)
""")

contract.process(50)

# Check logs
logs = contract.get_logs()
for log in logs:
    if log.event_type.name == "Debug":
        print(f"{log.args.message}: {log.args.value}")
```

## Finding exact failure points

Binary search to find where a contract starts failing:

```python
def find_breaking_point(contract, min_val, max_val):
    """Find exact value where contract fails"""
    while min_val < max_val - 1:
        mid = (min_val + max_val) // 2
        try:
            with boa.env.anchor():
                contract.process(mid)
                min_val = mid
        except:
            max_val = mid
    return max_val

# Find overflow point
breaking_point = find_breaking_point(contract, 0, 2**256)
print(f"Contract fails at: {breaking_point}")
```

## Best practices

1. **Use descriptive assertion messages**
   ```vyper
   assert balance >= amount, "Insufficient balance"
   ```

2. **Create debug versions with conditional prints**
   ```python
   DEBUG = True
   
   code = """
   @external
   def process(x: uint256) -> uint256:
       %s
       result: uint256 = x * 2
       return result
   """ % ('print("Input:", x)' if DEBUG else "")
   ```

3. **Test edge cases systematically**
   ```python
   test_values = [0, 1, 2**256-1]
   for val in test_values:
       try:
           result = contract.process(val)
           print(f"process({val}) = {result}")
       except Exception as e:
           print(f"process({val}) failed: {e}")
   ```