"""Limites financeiros por operação. Sem limite ou valor confiável, falha fechado."""
from decimal import Decimal, InvalidOperation
import json


OPERATIONS = frozenset({'refund', 'cancel_order', 'complete_draft'})


def money(value) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError('Valor financeiro ausente ou inválido')
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Valor financeiro inválido') from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal('999999999999.99'):
        raise ValueError('Valor financeiro fora da faixa permitida')
    if amount != amount.quantize(Decimal('.01')):
        raise ValueError('Valor financeiro deve ter no máximo duas casas decimais')
    return amount


def parse_limits(raw: str) -> tuple[tuple[str, str], ...]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Limite financeiro duplicado')
            result[key] = value
        return result
    data = json.loads(raw or '{}', object_pairs_hook=unique)
    if not isinstance(data, dict) or set(data) - OPERATIONS:
        raise ValueError('SHOPIFY_FINANCIAL_LIMITS_BRL contém operação desconhecida')
    return tuple(sorted((key, str(money(value))) for key, value in data.items()))


def check(limits, operation: str, amount, currency: str) -> dict:
    cap = dict(limits).get(operation)
    if cap is None:
        raise ValueError(f'Operação {operation} bloqueada: configure SHOPIFY_FINANCIAL_LIMITS_BRL e reinicie; use o sistema de origem enquanto isso.')
    if currency != 'BRL':
        raise ValueError('Operação bloqueada: limite definido apenas em BRL; use o sistema de origem.')
    value, limit = money(amount), money(cap)
    if value > limit:
        raise ValueError(f'Operação {operation} recusada: total excede o limite; use o sistema de origem.')
    return {'operation': operation, 'amount': f'{value:.2f}', 'currency': currency, 'limit': f'{limit:.2f}'}
