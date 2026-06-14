import sys
import types

from boa.contracts.vyper import compiler_utils


def test_direct_venom_debug_module_adds_wrapper_function(monkeypatch):
    module_t = types.SimpleNamespace(exposed_functions=["existing"])
    settings = types.SimpleNamespace(optimize="optimize")
    calls = {}

    def generate_venom_runtime(debug_module_t, actual_settings):
        calls["debug_module_t"] = debug_module_t
        calls["settings"] = actual_settings
        return "venom_runtime"

    def generate_assembly_experimental(venom_runtime, optimize):
        calls["venom_runtime"] = venom_runtime
        calls["optimize"] = optimize
        return ["assembly"]

    monkeypatch.setitem(
        sys.modules,
        "vyper.codegen_venom",
        types.SimpleNamespace(generate_venom_runtime=generate_venom_runtime),
    )
    monkeypatch.setattr(
        compiler_utils,
        "generate_assembly_experimental",
        generate_assembly_experimental,
    )

    assembly = compiler_utils._compile_assembly_with_direct_venom(
        module_t, "debug", settings
    )

    assert assembly == ["assembly"]
    assert calls["debug_module_t"].exposed_functions == ["existing", "debug"]
    assert calls["settings"] is settings
    assert calls["venom_runtime"] == "venom_runtime"
    assert calls["optimize"] == "optimize"
