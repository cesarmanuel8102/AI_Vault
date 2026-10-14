"""Host-only PAPER net economics, corroborated by cash and execution evidence."""

from datetime import datetime, timezone
from decimal import Decimal
import time

from .canonical import sha256_json
from .ibkr_readonly import expected_identity_hash


def _number(value):
    result = Decimal(str(value))
    if not result.is_finite() or abs(result) >= Decimal('1e100'):
        raise ValueError('CANARY_NET_ECONOMICS_VALUE_INVALID')
    return result


def verified_net_observation(request, before, after, facts):
    for item in (before, after):
        if (item.get('source') != 'IBKR_PAPER'
                or item.get('account_identity_sha256') != request.account_identity_sha256
                or item.get('contract_id') != request.canonical_contract.con_id
                or item.get('request_sha256') != request.sha256
                or _number(item['position_quantity']) != 0
                or item.get('open_order_count') != 0):
            raise ValueError('CANARY_NET_ECONOMICS_IDENTITY_INVALID')
    start = datetime.fromisoformat(before['observed_at_utc'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(after['observed_at_utc'].replace('Z', '+00:00'))
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError('CANARY_NET_ECONOMICS_TIME_INVALID')
    if (facts.get('request_sha256') != request.sha256 or facts.get('complete') is not True
            or facts.get('account_identity_sha256') != request.account_identity_sha256
            or facts.get('contract_identity_sha256') != request.canonical_contract.sha256
            or _number(facts['position_quantity']) != 0 or facts['open_order_count'] != 0):
        raise ValueError('CANARY_NET_ECONOMICS_FACTS_INVALID')
    fills = list(facts['fills'])
    ids = {f['execution_id_sha256'] for f in fills}
    previous = set(before['execution_ids'])
    current = set(after['execution_ids'])
    if (len(ids) != len(fills) or ids & previous or current - previous != ids
            or not previous.issubset(current)
            or len(current) != len(after['execution_ids'])):
        raise ValueError('CANARY_NET_ECONOMICS_EXECUTION_MISMATCH')
    totals = {'BUY': Decimal(0), 'SELL': Decimal(0)}
    gross = Decimal(0)
    for fill in fills:
        action = fill['action']
        if action not in totals:
            raise ValueError('CANARY_NET_ECONOMICS_FILL_INVALID')
        quantity, price = _number(fill['quantity']), _number(fill['price'])
        if quantity <= 0 or price <= 0:
            raise ValueError('CANARY_NET_ECONOMICS_FILL_INVALID')
        totals[action] += quantity
        gross += quantity * price * (1 if action == 'SELL' else -1)
    if not Decimal(0) < totals['BUY'] == totals['SELL'] <= request.quantity:
        raise ValueError('CANARY_NET_ECONOMICS_QUANTITY_MISMATCH')
    prior_pnl = before.get('realized_pnl_usd')
    net = _number(after['realized_pnl_usd']) - (Decimal(0) if prior_pnl is None else _number(prior_pnl))
    before_cash, after_cash = _number(before['cash_usd']), _number(after['cash_usd'])
    # Reported balances are rounded observations, not exact subcent cash.
    # Require at least four reported decimals and overlapping rounding intervals.
    quanta = [Decimal(1).scaleb(v.as_tuple().exponent) for v in (before_cash, after_cash)]
    if any(q > Decimal('.0001') for q in quanta):
        raise ValueError('CANARY_NET_ECONOMICS_CASH_PRECISION_REQUIRED')
    if abs(after_cash - before_cash - net) >= sum(quanta) / 2:
        raise ValueError('CANARY_NET_ECONOMICS_CASH_MISMATCH')
    evidence = {'baseline': before, 'terminal': after, 'facts_sha256': sha256_json(facts)}
    return {'account_identity_sha256': request.account_identity_sha256,
            'candidate_sha256': request.candidate_sha256,
            'contract_id': request.canonical_contract.con_id,
            'original_request_sha256': request.sha256,
            'broker_realized_pnl_usd': str(net), 'gross_execution_pnl_usd': str(gross),
            'cost_difference_usd': str(gross-net), 'cost_difference_is_inference': True,
            'individual_commission_reports_missing': True,
            'candidate_fee_allowance_usd': str(request.fee_allowance_usd),
            'evidence_sha256': sha256_json(evidence), 'evidence': evidence,
            'executions': [{'id_sha256': f['execution_id_sha256'], 'side': f['action'],
                            'quantity': f['quantity'], 'price': f['price']} for f in fills]}


def collect_net_snapshot(request, broker, *, timeout_seconds=8):
    """Uses the caller's authenticated PAPER session; no order API is called."""
    prior_timeout = broker.RequestTimeout
    broker.RequestTimeout = timeout_seconds
    try:
        return _collect_net_snapshot(request, broker, timeout_seconds=timeout_seconds)
    finally:
        broker.RequestTimeout = prior_timeout


def _collect_net_snapshot(request, broker, *, timeout_seconds):
    from ib_insync import ExecutionFilter

    accounts = broker.managedAccounts()
    if (len(accounts) != 1 or not accounts[0].startswith('DU')
            or expected_identity_hash(accounts[0]) != request.account_identity_sha256):
        raise ValueError('CANARY_NET_ECONOMICS_PAPER_ACCOUNT_REQUIRED')
    account = accounts[0]
    request_id = broker.client.getReqId()
    future = broker.wrapper.startReq(request_id)
    try:
        broker.client.reqAccountSummary(request_id, 'All', '$LEDGER:USD')
        broker._run(future)
    finally:
        broker.client.cancelAccountSummary(request_id)
    cash_rows = [v for v in broker.accountSummary()
                 if v.account == account and v.tag == '$LEDGER-CashBalance' and v.currency == 'USD']
    if len(cash_rows) != 1:
        raise ValueError('CANARY_NET_ECONOMICS_CASH_REQUIRED')
    fills = broker.reqExecutions(ExecutionFilter(acctCode=account))
    positions = broker.reqPositions()
    orders = broker.reqAllOpenOrders()
    con_id = request.canonical_contract.con_id
    pnl = broker.reqPnLSingle(account, '', con_id)
    try:
        deadline = time.monotonic() + timeout_seconds
        realized = None
        while time.monotonic() < deadline:
            try:
                realized = str(_number(pnl.realizedPnL))
                break
            except (ValueError, ArithmeticError):
                broker.sleep(.05)
    finally:
        broker.cancelPnLSingle(account, '', con_id)
    return {'source': 'IBKR_PAPER', 'account_identity_sha256': request.account_identity_sha256,
            'contract_id': con_id, 'request_sha256': request.sha256,
            'observed_at_utc': broker.reqCurrentTime().astimezone(timezone.utc).isoformat(),
            'cash_usd': str(_number(cash_rows[0].value)), 'realized_pnl_usd': realized,
            'execution_ids': [sha256_json(f.execution.execId) for f in fills],
            'position_quantity': str(sum((_number(p.position) for p in positions
                                          if p.account == account and p.contract.conId == con_id), Decimal(0))),
            'open_order_count': len(orders)}
