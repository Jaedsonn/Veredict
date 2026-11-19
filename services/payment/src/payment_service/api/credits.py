"""Carteira de créditos (RF10 parcial, #73): saldo e extrato"""

from fastapi import APIRouter

from payment_service.dependencies import ActorDep, GetBalanceDep, GetStatementDep
from payment_service.schemas import BalanceOut, LedgerEntryOut, StatementOut

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/balance", response_model=BalanceOut)
async def balance(actor: ActorDep, use_case: GetBalanceDep) -> BalanceOut:
    return BalanceOut(balance=await use_case.execute(actor.user_id))


@router.get("/statement", response_model=StatementOut)
async def statement(
    actor: ActorDep, use_case: GetStatementDep, balance_use_case: GetBalanceDep
) -> StatementOut:
    entries = await use_case.execute(actor.user_id)
    return StatementOut(
        balance=await balance_use_case.execute(actor.user_id),
        entries=[LedgerEntryOut.of(e) for e in entries],
    )
