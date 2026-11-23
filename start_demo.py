"""Start the isolated portfolio demo. Requires Python 3.11+ and Docker Compose."""
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def main():
    if not shutil.which("docker"):
        print("Instalá Docker con Docker Compose y volvé a ejecutar este comando.")
        return 1
    if subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        print("Abrí Docker Desktop y esperá a que termine de iniciar.")
        return 1
    env_file = ROOT / ".demo.env"
    if not env_file.exists():
        with env_file.open("x", encoding="utf-8") as stream:
            stream.write("DEMO_DB_PASSWORD=" + secrets.token_hex(24) + "\nDEMO_JWT_SECRET=" + secrets.token_hex(32) + "\nDEMO_AI_PROVIDER=simulated\n")
        if sys.platform != "win32":
            env_file.chmod(0o600)
    command = ["docker", "compose", "--env-file", str(env_file), "-f", str(ROOT / "compose.demo.yml"), "up", "--build", "-d", "--wait", "--wait-timeout", "240"]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        print("No se pudo iniciar la demo. Revisá el mensaje anterior de Docker.")
        return result.returncode
    print("Demo lista: http://127.0.0.1:8020/panel/ · Sin WhatsApp ni pagos reales.")
    print("Para detenerla: docker compose --env-file .demo.env -f compose.demo.yml down")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
