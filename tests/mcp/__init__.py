import sys
from pathlib import Path

# When pytest discovers tests/mcp in importlib mode without a tests/__init__.py,
# it assigns __name__ = "mcp" to this package, which shadows the third-party
# "mcp" library required by fastmcp.
# If shadowed, we extend __path__ with the real installed package directory and
# execute its __init__.py into this module's globals so both test modules and
# third-party mcp submodules/exports work seamlessly.
if __name__ == "mcp":
    this_dir = Path(__file__).resolve().parent
    for path_str in sys.path:
        candidate = Path(path_str) / "mcp"
        if candidate.is_dir() and candidate.resolve() != this_dir:
            cand_str = str(candidate.resolve())
            if cand_str not in __path__:
                __path__.append(cand_str)
            init_file = candidate / "__init__.py"
            if init_file.is_file():
                with open(init_file) as f:
                    code = compile(f.read(), str(init_file), "exec")
                exec(code, globals())
            break
