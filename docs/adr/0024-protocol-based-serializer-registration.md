# 24. Protocol-based Serializer Registration

Date: 2024-02-17

## Status

Accepted

## Context

`beautyspot` allows users to register custom types for serialization using the `@spot.register` decorator.
Initially, the implementation in `core.py` explicitly checked if the serializer was an instance of `MsgpackSerializer`.

```python
if isinstance(self.serializer, MsgpackSerializer):
    self.serializer.register(...)

```

This violated the Dependency Inversion Principle by coupling the high-level `Spot` class to a specific concrete implementation (`MsgpackSerializer`). It made it impossible to use other serializers that might support type registration (e.g., a future `JsonSerializer` or a custom wrapper).

## Decision

We introduced a new protocol, `TypeRegistryProtocol`, in `beautyspot.serializer`.

1. **Define Protocol**: The protocol defines a `register` method signature required for type registration.
2. ** decoupling**: The `Spot` class now checks against this protocol instead of the concrete `MsgpackSerializer` class.
3. **Interface Segregation**: We separated `TypeRegistryProtocol` from the basic `SerializerProtocol` (dump/load), acknowledging that not all serializers support custom type registration.

## Consequences

* **Positive**: The core logic is now decoupled from `msgpack`. Users can implement their own serializers with registration support by conforming to `TypeRegistryProtocol`.
* **Positive**: Testing is easier as we can mock the protocol without instantiating the full `MsgpackSerializer`.
* **Negative**: Serializer implementations must explicitly match the `register` signature defined in the protocol.

