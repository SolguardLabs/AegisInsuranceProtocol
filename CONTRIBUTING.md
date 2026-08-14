# Contribuir

## Preparación

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Validación

Antes de abrir una pull request:

```bash
bash scripts/ci.sh
```

En PowerShell:

```powershell
.\scripts\ci.ps1
```

## Criterios

- Código y comentarios de código en inglés.
- Documentación pública en español.
- Importes enteros y porcentajes en basis points.
- Tests deterministas para cualquier transición económica.
- Ningún cambio puede superar el límite EIP-170.
- Los cambios de exposure, claim o capital deben reconciliar pool y póliza.
- No incluyas secretos, datos reales ni outputs generados.

Las cuestiones de seguridad se comunican por el canal descrito en [SECURITY.md](./SECURITY.md),
no mediante issues públicas.
