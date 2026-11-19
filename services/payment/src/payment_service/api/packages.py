"""Catálogo de pacotes (RF07, D2): público no gateway, mas só aceito vindo dele"""

from fastapi import APIRouter, Depends

from payment_service.dependencies import ListPackagesDep
from payment_service.schemas import PackageOut
from veriditi_common.security import require_internal_token

router = APIRouter(
    prefix="/packages", tags=["packages"], dependencies=[Depends(require_internal_token)]
)


@router.get("", response_model=list[PackageOut])
async def list_packages(use_case: ListPackagesDep) -> list[PackageOut]:
    return [PackageOut.of(p) for p in await use_case.execute()]
