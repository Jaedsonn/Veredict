"""Código transversal compartilhado pelos serviços Python do monorepo.

Regra de ouro: aqui entra apenas *infraestrutura* (config, conexão, health, logging).
Regras de negócio pertencem a cada serviço — compartilhá-las criaria acoplamento
entre serviços que deveriam evoluir de forma independente.
"""
