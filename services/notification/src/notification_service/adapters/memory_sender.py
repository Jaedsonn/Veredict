from notification_service.domain import EmailDeliveryError, OutgoingEmail


class InMemoryEmailSender:
    """Fake do SMTP para os testes; fica no src para o import funcionar com importlib"""

    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.sent.append(email)


class FailingEmailSender(InMemoryEmailSender):
    """Falha nas fail_times primeiras chamadas e depois entrega"""

    def __init__(self, fail_times: int, error: Exception | None = None) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.error = error or EmailDeliveryError("SMTPServerDisconnected")
        self.calls: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.calls.append(email)
        if len(self.calls) <= self.fail_times:
            raise self.error
        await super().send(email)
