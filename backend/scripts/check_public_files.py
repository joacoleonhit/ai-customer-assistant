"""Report likely credentials without ever printing their values. No external upload."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {".git", ".agents", ".vscode", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", "dist"}
PATTERNS = [
    re.compile(r"EAA[A-Za-z0-9]{40,}"),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{25,}"),
    re.compile(r"APP_USR-[A-Za-z0-9_-]{25,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def eligible(path):
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED for part in relative.parts):
        return False
    if path.name in {".env", ".demo.env"} or (path.name.startswith(".env.") and path.name != ".env.example"):
        return False
    if path.suffix in {".log", ".db", ".sqlite", ".pyc"}:
        return False
    if path.parent == ROOT / "backend/scripts" and path.suffix == ".json" and ("results" in path.name or "summary" in path.name):
        return False
    return path.is_file()


def main():
    git = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    paths = [ROOT / name for name in git.stdout.decode().split("\0") if name] if git.returncode == 0 else [p for p in ROOT.rglob("*") if eligible(p)]
    findings = []
    for path in paths:
        if not path.is_file():
            continue
        if path.name in {".env", ".demo.env"} or (path.name.startswith(".env.") and path.name != ".env.example"):
            findings.append((path, "archivo de configuración privado versionado")); continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        if any(pattern.search(content) for pattern in PATTERNS):
            findings.append((path, "posible credencial"))
    for path, reason in findings:
        print(f"REVISAR {path.relative_to(ROOT).as_posix()}: {reason}")
    print(f"Archivos revisados: {len(paths)}. Hallazgos: {len(findings)}.")
    if git.returncode:
        print("Todavía no hay repositorio Git: se revisaron los archivos publicables, no un historial de commits.")
    else:
        print("Este control revisa archivos actuales. Revisá también el historial antes de publicar.")
    return bool(findings)

if __name__ == "__main__":
    raise SystemExit(main())
