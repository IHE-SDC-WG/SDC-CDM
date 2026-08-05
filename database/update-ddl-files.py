#!/usr/bin/env python3
"""Guard against regenerating the retired combined OMOP-SDC DDL.

The active schema source is database/SCHEMA_ARCHITECTURE.md plus the files under
database/schemas/. OMOP DDL must come from stock OHDSI CDM 5.4 artifacts and SDC
or NAACCR tables must stay in their own schemas.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "The old OMOP-SDC DDL generator has been retired. "
        "Use database/schemas/{omop,naaccr,sdc}/ddl instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
