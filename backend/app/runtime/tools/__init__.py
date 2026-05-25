from app.runtime.tools.payment_tools import (
    get_transaction,
    get_psp_status,
    check_routing_logs,
    suggest_alternate_psp,
)
from app.runtime.tools.telegram_tool import send_telegram_message
from app.runtime.tools.calculator import calculator

ALL_TOOLS = [
    get_transaction,
    get_psp_status,
    check_routing_logs,
    suggest_alternate_psp,
    send_telegram_message,
    calculator,
]

TOOL_REGISTRY: dict = {t.name: t for t in ALL_TOOLS}
