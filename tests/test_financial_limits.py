from dataclasses import replace
from unittest.mock import Mock
import pytest

from shopify_mcp.financial import money, parse_limits, check
from shopify_mcp.operations import ShopifyOperations
from shopify_mcp.confirmations import ConfirmationError
from test_refund_mutations import SequenceClient, order_response, payload


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '1.001', True, None, '1,00', '1e9999'])
def test_invalid_money_is_rejected(value):
    with pytest.raises(ValueError): money(value)


@pytest.mark.parametrize('raw', ['{"refund":1,"refund":2}', '{"unknown":1}', '[]', '{"refund":-1}'])
def test_invalid_limits_fail_closed(raw):
    with pytest.raises(ValueError): parse_limits(raw)


def test_exact_boundary_and_foreign_currency():
    limits = parse_limits('{"refund":"50.00"}')
    assert check(limits, 'refund', '50', 'BRL')['amount'] == '50.00'
    for amount,currency in [('50.01','BRL'),('1','USD')]:
        with pytest.raises(ValueError): check(limits, 'refund', amount, currency)


@pytest.mark.asyncio
@pytest.mark.parametrize('limits', [(), (('refund', '49.99'),)])
async def test_refund_refused_before_token_and_mutation(limits):
    client = SequenceClient([order_response()])
    client.settings = replace(client.settings, financial_limits_brl=limits)
    manager = Mock()
    with pytest.raises(ValueError):
        await ShopifyOperations(client, manager).prepare_refund_create(payload())
    manager.issue.assert_not_called()
    assert len(client.calls) == 1 and client.calls[0][0].startswith('query')


@pytest.mark.asyncio
async def test_split_refund_transactions_are_summed():
    response = order_response()
    transactions = response['data']['order']['suggestedRefund']['suggestedTransactions']
    transactions.append(transactions[0].copy())
    client = SequenceClient([response])
    client.settings = replace(client.settings, financial_limits_brl=(('refund', '99.99'),))
    with pytest.raises(ValueError, match='excede'):
        await ShopifyOperations(client).prepare_refund_create(payload())


@pytest.mark.asyncio
async def test_cancel_rechecks_total_and_consumes_token_on_failure():
    from test_order_customer_operations import cancellable_order
    order = cancellable_order()
    changed = cancellable_order()
    changed['currentTotalPriceSet']['shopMoney']['amount'] = '90.00'
    client = SequenceClient([{'data': {'order': order}}, {'data': {'order': changed}}])
    client.settings = replace(client.settings, financial_limits_brl=(('cancel_order', '100'),))
    args = {'orderId': order['id'], 'reason': 'CUSTOMER', 'refundOriginalPaymentMethods': True,
            'restock': False, 'notifyCustomer': False, 'staffNote': 'test'}
    ops = ShopifyOperations(client)
    proposal = await ops.prepare_order_cancel(args)
    apply = {**args, 'confirmationToken': proposal['confirmationToken']}
    with pytest.raises(ValueError, match='Total mudou'):
        await ops.cancel_order(apply)
    with pytest.raises(ConfirmationError):
        await ops.cancel_order(apply)
    assert all(q.startswith('query') for q,_ in client.calls)


def test_context_is_not_mutable_through_preview():
    from shopify_mcp.confirmations import ConfirmationManager
    manager = ConfirmationManager()
    context = {'amount': '10'}
    token = manager.issue('operation', {}, context=context)['confirmationToken']
    context['amount'] = '100'
    assert manager.consume(token, 'operation', {})['amount'] == '10'


def test_limits_are_loaded_once_in_settings(monkeypatch):
    from shopify_mcp.config import Settings
    monkeypatch.setenv('SHOPIFY_SHOP_DOMAIN', 'example.myshopify.com')
    monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'test')
    monkeypatch.setenv('SHOPIFY_ENABLE_WRITES', 'false')
    monkeypatch.setenv('SHOPIFY_TOOL_PROFILE', 'readonly')
    monkeypatch.setenv('SHOPIFY_FINANCIAL_LIMITS_BRL', '{"refund":"10"}')
    settings = Settings.from_env()
    monkeypatch.setenv('SHOPIFY_FINANCIAL_LIMITS_BRL', '{"refund":"100"}')
    assert dict(settings.financial_limits_brl)['refund'] == '10'


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['cancel_order','complete_draft'])
@pytest.mark.parametrize('value', ['100.01', None])
async def test_other_financial_operations_refuse_bad_total_before_token(operation,value):
    manager = Mock()
    amount = {'shopMoney': {'amount': value, 'currencyCode': 'BRL'}}
    if operation == 'cancel_order':
        from test_order_customer_operations import cancellable_order
        order = cancellable_order()
        order['currentTotalPriceSet'] = amount
        response = {'data': {'order': order}}
        args = {'orderId': order['id'], 'reason': 'CUSTOMER', 'refundOriginalPaymentMethods': False,
                'restock': False, 'notifyCustomer': False, 'staffNote': 'test'}
        method = 'prepare_order_cancel'
    else:
        response = {'data': {'draftOrder': {'id': 'gid://shopify/DraftOrder/1', 'status': 'OPEN',
                    'order': None, 'lineItems': {'nodes': []}, 'totalPriceSet': amount}}}
        args = {'id': 'gid://shopify/DraftOrder/1'}
        method = 'prepare_draft_order_complete'
    client = SequenceClient([response])
    client.settings = replace(client.settings, financial_limits_brl=((operation,'100.00'),))
    with pytest.raises(ValueError):
        await getattr(ShopifyOperations(client,manager),method)(args)
    manager.issue.assert_not_called()
    assert len(client.calls)==1


@pytest.mark.asyncio
async def test_draft_apply_rechecks_total_and_mutates_only_once():
    draft = {'id':'gid://shopify/DraftOrder/1','status':'OPEN','order':None,'lineItems':{'nodes':[]},
             'totalPriceSet':{'shopMoney':{'amount':'100.00','currencyCode':'BRL'}}}
    client = SequenceClient([{'data':{'draftOrder':draft}}, {'data':{'draftOrder':draft}},
            {'data':{'draftOrderComplete':{'draftOrder':{'id':draft['id']},'userErrors':[]}}}])
    client.settings = replace(client.settings, financial_limits_brl=(('complete_draft','100.00'),))
    ops=ShopifyOperations(client)
    args={'id':draft['id']}
    proposal=await ops.prepare_draft_order_complete(args)
    apply={**args,'confirmationToken':proposal['confirmationToken']}
    await ops.complete_draft_order(apply)
    with pytest.raises(ConfirmationError):await ops.complete_draft_order(apply)
    assert len(client.calls)==3
    assert sum(q.startswith('mutation') for q,_ in client.calls)==1
