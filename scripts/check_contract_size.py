from pathlib import Path

from vyper import compile_code


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "src" / "AegisInsuranceProtocol.vy"
EIP170_RUNTIME_LIMIT = 24_576


def main() -> None:
    source = CONTRACT.read_text(encoding="utf-8")
    runtime = compile_code(source, output_formats=["bytecode_runtime"])["bytecode_runtime"]
    runtime_bytes = (len(runtime) - 2) // 2
    headroom = EIP170_RUNTIME_LIMIT - runtime_bytes
    print(f"runtime_bytes={runtime_bytes} eip170_headroom={headroom}")
    if runtime_bytes > EIP170_RUNTIME_LIMIT:
        raise SystemExit("contract runtime exceeds the EIP-170 limit")


if __name__ == "__main__":
    main()
