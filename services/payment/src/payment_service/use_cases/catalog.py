"""Catálogo da D2 e carteira: consultas sem efeito colateral"""

from typing import Final

from payment_service.domain import CreditPackage, LedgerEntry
from payment_service.ports import PackageRepository, WalletRepository

STATEMENT_LIMIT: Final = 50


class ListPackages:
    def __init__(self, packages: PackageRepository) -> None:
        self._packages = packages

    async def execute(self) -> list[CreditPackage]:
        return await self._packages.list_active()


class GetBalance:
    def __init__(self, wallets: WalletRepository) -> None:
        self._wallets = wallets

    async def execute(self, user_id: int) -> int:
        return await self._wallets.balance(user_id)


class GetStatement:
    def __init__(self, wallets: WalletRepository) -> None:
        self._wallets = wallets

    async def execute(self, user_id: int) -> list[LedgerEntry]:
        return await self._wallets.statement(user_id, limit=STATEMENT_LIMIT)
