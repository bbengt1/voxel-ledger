"""Per-bounded-context migration modules.

Importing this package side-effects each module into the orchestrator
registry, in the order the contexts depend on each other.
"""

from scripts.v1_migration.contexts import (
    accounts,  # noqa: F401
    attachments,  # noqa: F401
    bills,  # noqa: F401
    customers,  # noqa: F401
    expenses,  # noqa: F401
    inventory_locations,  # noqa: F401
    inventory_transactions,  # noqa: F401
    invoices,  # noqa: F401
    materials,  # noqa: F401
    products,  # noqa: F401
    sales,  # noqa: F401
    settings,  # noqa: F401
    supplies,  # noqa: F401
    users,  # noqa: F401
    vendors,  # noqa: F401
)
