from enum import StrEnum


class NotificationStatus(StrEnum):
    """pending na reserva; sent e failed só por UPDATE condicional a partir de pending"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
