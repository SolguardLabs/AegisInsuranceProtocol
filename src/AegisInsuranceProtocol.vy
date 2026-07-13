# pragma version 0.4.3

BPS_DENOMINATOR: constant(uint256) = 10_000
SECONDS_PER_DAY: constant(uint256) = 86_400
YEAR_DAYS: constant(uint256) = 365
MAX_CESSIONS: constant(uint256) = 4
MAX_PRODUCTS: constant(uint256) = 32
MAX_POOL_COUNT: constant(uint256) = 128
MIN_POLICY_DAYS: constant(uint256) = 1
MAX_POLICY_DAYS: constant(uint256) = 730

POOL_INACTIVE: constant(uint256) = 0
POOL_ACTIVE: constant(uint256) = 1
POOL_PAUSED: constant(uint256) = 2

POLICY_EMPTY: constant(uint256) = 0
POLICY_ACTIVE: constant(uint256) = 1
POLICY_EXPIRED: constant(uint256) = 2
POLICY_CLAIMED: constant(uint256) = 3
POLICY_CANCELLED: constant(uint256) = 4

CLAIM_EMPTY: constant(uint256) = 0
CLAIM_SUBMITTED: constant(uint256) = 1
CLAIM_REVIEWED: constant(uint256) = 2
CLAIM_APPROVED: constant(uint256) = 3
CLAIM_PAID: constant(uint256) = 4
CLAIM_REJECTED: constant(uint256) = 5

ROLE_NONE: constant(uint256) = 0
ROLE_REVIEWER: constant(uint256) = 1
ROLE_ROUTER: constant(uint256) = 2
ROLE_KEEPER: constant(uint256) = 3

struct Pool:
    sponsor: address
    label: bytes32
    jurisdiction: bytes32
    status: uint256
    total_capital: uint256
    locked_exposure: uint256
    pending_claims: uint256
    paid_claims: uint256
    earned_premiums: uint256
    protocol_fees: uint256
    min_capital: uint256
    max_utilization_bps: uint256
    retention_bps: uint256
    created_at: uint256
    updated_at: uint256

struct Product:
    label: bytes32
    base_rate_bps: uint256
    min_premium: uint256
    deductible_bps: uint256
    claim_window_days: uint256
    max_cover: uint256
    active: bool

struct Policy:
    holder: address
    beneficiary: address
    pool_id: uint256
    product_id: uint256
    subject: bytes32
    coverage: uint256
    premium: uint256
    start_time: uint256
    expiration_time: uint256
    claim_window_end: uint256
    retained_exposure: uint256
    ceded_exposure: uint256
    paid_amount: uint256
    status: uint256
    cession_count: uint256
    created_at: uint256
    updated_at: uint256

struct Claim:
    policy_id: uint256
    claimant: address
    beneficiary: address
    amount_requested: uint256
    amount_approved: uint256
    amount_paid: uint256
    evidence_hash: bytes32
    incident_hash: bytes32
    submitted_at: uint256
    reviewed_at: uint256
    paid_at: uint256
    status: uint256

struct EpochSnapshot:
    timestamp: uint256
    pool_id: uint256
    total_capital: uint256
    locked_exposure: uint256
    pending_claims: uint256
    paid_claims: uint256
    utilization_bps: uint256
    solvency_bps: uint256

event PoolCreated:
    pool_id: indexed(uint256)
    sponsor: indexed(address)
    label: bytes32

event PoolLimitsUpdated:
    pool_id: indexed(uint256)
    min_capital: uint256
    max_utilization_bps: uint256
    retention_bps: uint256

event CapitalDeposited:
    pool_id: indexed(uint256)
    provider: indexed(address)
    amount: uint256
    shares: uint256

event CapitalWithdrawn:
    pool_id: indexed(uint256)
    provider: indexed(address)
    receiver: indexed(address)
    amount: uint256

event ProductConfigured:
    product_id: indexed(uint256)
    label: bytes32
    base_rate_bps: uint256

event PolicyIssued:
    policy_id: indexed(uint256)
    pool_id: indexed(uint256)
    holder: indexed(address)
    coverage: uint256
    premium: uint256

event PolicyExposureTransferred:
    policy_id: indexed(uint256)
    from_pool: indexed(uint256)
    to_pool: indexed(uint256)
    amount: uint256

event PolicyExpired:
    policy_id: indexed(uint256)
    pool_id: indexed(uint256)
    coverage: uint256

event ClaimSubmitted:
    claim_id: indexed(uint256)
    policy_id: indexed(uint256)
    claimant: indexed(address)
    amount: uint256

event ClaimReviewed:
    claim_id: indexed(uint256)
    reviewer: indexed(address)
    status: uint256
    approved_amount: uint256

event ClaimPaid:
    claim_id: indexed(uint256)
    policy_id: indexed(uint256)
    beneficiary: address
    amount: uint256

event RoleUpdated:
    account: indexed(address)
    role: indexed(uint256)
    enabled: bool

event EpochRecorded:
    epoch_id: indexed(uint256)
    pool_id: indexed(uint256)
    utilization_bps: uint256
    solvency_bps: uint256

owner: public(address)
treasury: public(address)
paused: public(bool)

pool_count: public(uint256)
product_count: public(uint256)
policy_count: public(uint256)
claim_count: public(uint256)
epoch_count: public(uint256)

pools: HashMap[uint256, Pool]
products: HashMap[uint256, Product]
policies: HashMap[uint256, Policy]
claims: HashMap[uint256, Claim]
epochs: HashMap[uint256, EpochSnapshot]

pool_shares: HashMap[uint256, HashMap[address, uint256]]
roles: HashMap[address, HashMap[uint256, bool]]
incident_signals: HashMap[bytes32, bool]

policy_cession_pool: HashMap[uint256, HashMap[uint256, uint256]]
policy_cession_amount: HashMap[uint256, HashMap[uint256, uint256]]
claim_pool_id: HashMap[uint256, HashMap[uint256, uint256]]
claim_pool_amount: HashMap[uint256, HashMap[uint256, uint256]]
claim_pool_count: HashMap[uint256, uint256]

@deploy
def __init__(_treasury: address):
    assert _treasury != empty(address), "treasury required"
    self.owner = msg.sender
    self.treasury = _treasury
    self.roles[msg.sender][ROLE_REVIEWER] = True
    self.roles[msg.sender][ROLE_ROUTER] = True
    self.roles[msg.sender][ROLE_KEEPER] = True

@internal
@view
def _is_owner(account: address) -> bool:
    return account == self.owner

@internal
@view
def _has_role(account: address, role: uint256) -> bool:
    if account == self.owner:
        return True
    return self.roles[account][role]

@internal
@view
def _pool_exists(pool_id: uint256) -> bool:
    return pool_id > 0 and pool_id <= self.pool_count

@internal
@view
def _policy_exists(policy_id: uint256) -> bool:
    return policy_id > 0 and policy_id <= self.policy_count

@internal
@view
def _claim_exists(claim_id: uint256) -> bool:
    return claim_id > 0 and claim_id <= self.claim_count

@internal
@view
def _active_pool(pool_id: uint256) -> bool:
    if not self._pool_exists(pool_id):
        return False
    return self.pools[pool_id].status == POOL_ACTIVE

@internal
@view
def _product_active(product_id: uint256) -> bool:
    if product_id == 0 or product_id > self.product_count:
        return False
    return self.products[product_id].active

@internal
@view
def _capacity_ceiling(pool_id: uint256) -> uint256:
    pool: Pool = self.pools[pool_id]
    return pool.total_capital * pool.max_utilization_bps // BPS_DENOMINATOR

@internal
@view
def _available_capacity(pool_id: uint256) -> uint256:
    ceiling: uint256 = self._capacity_ceiling(pool_id)
    locked: uint256 = self.pools[pool_id].locked_exposure
    if ceiling <= locked:
        return 0
    return ceiling - locked

@internal
@view
def _free_capital(pool_id: uint256) -> uint256:
    pool: Pool = self.pools[pool_id]
    if pool.total_capital <= pool.locked_exposure:
        return 0
    return pool.total_capital - pool.locked_exposure

@internal
@view
def _min(a: uint256, b: uint256) -> uint256:
    if a < b:
        return a
    return b

@internal
@view
def _utilization_bps(pool_id: uint256) -> uint256:
    pool: Pool = self.pools[pool_id]
    if pool.total_capital == 0:
        return 0
    return pool.locked_exposure * BPS_DENOMINATOR // pool.total_capital

@internal
@view
def _solvency_bps(pool_id: uint256) -> uint256:
    pool: Pool = self.pools[pool_id]
    obligations: uint256 = pool.locked_exposure + pool.pending_claims
    if obligations == 0:
        return BPS_DENOMINATOR
    return pool.total_capital * BPS_DENOMINATOR // obligations

@internal
def _lock_pool_exposure(pool_id: uint256, amount: uint256):
    assert self._active_pool(pool_id), "pool inactive"
    assert self._available_capacity(pool_id) >= amount, "capacity exceeded"
    self.pools[pool_id].locked_exposure += amount
    self.pools[pool_id].updated_at = block.timestamp

@internal
def _release_pool_exposure(pool_id: uint256, amount: uint256) -> uint256:
    locked: uint256 = self.pools[pool_id].locked_exposure
    released: uint256 = self._min(amount, locked)
    self.pools[pool_id].locked_exposure = locked - released
    self.pools[pool_id].updated_at = block.timestamp
    return released

@internal
@view
def _quote_product_premium(
    product_id: uint256, coverage: uint256, duration_days: uint256, utilization_bps: uint256
) -> uint256:
    product: Product = self.products[product_id]
    time_premium: uint256 = coverage * product.base_rate_bps * duration_days // YEAR_DAYS // BPS_DENOMINATOR
    utilization_premium: uint256 = coverage * utilization_bps // BPS_DENOMINATOR // 25
    premium: uint256 = time_premium + utilization_premium
    if premium < product.min_premium:
        return product.min_premium
    return premium

@internal
def _add_cession(policy_id: uint256, pool_id: uint256, amount: uint256):
    count: uint256 = self.policies[policy_id].cession_count
    for i: uint256 in range(MAX_CESSIONS):
        if i < count:
            if self.policy_cession_pool[policy_id][i] == pool_id:
                self.policy_cession_amount[policy_id][i] += amount
                return
    assert count < MAX_CESSIONS, "cession limit"
    self.policy_cession_pool[policy_id][count] = pool_id
    self.policy_cession_amount[policy_id][count] = amount
    self.policies[policy_id].cession_count = count + 1

@internal
def _clear_cession_slot(policy_id: uint256, slot: uint256):
    self.policy_cession_pool[policy_id][slot] = 0
    self.policy_cession_amount[policy_id][slot] = 0

@internal
@view
def _policy_total_exposure(policy_id: uint256) -> uint256:
    policy: Policy = self.policies[policy_id]
    return policy.retained_exposure + policy.ceded_exposure

@internal
@view
def _policy_pool_allocation(policy_id: uint256, pool_id: uint256) -> uint256:
    policy: Policy = self.policies[policy_id]
    if pool_id == policy.pool_id:
        return policy.retained_exposure
    for i: uint256 in range(MAX_CESSIONS):
        if i < policy.cession_count:
            if self.policy_cession_pool[policy_id][i] == pool_id:
                return self.policy_cession_amount[policy_id][i]
    return 0

@internal
def _register_claim_allocations(claim_id: uint256, policy_id: uint256, requested: uint256):
    policy: Policy = self.policies[policy_id]
    total_exposure: uint256 = self._policy_total_exposure(policy_id)
    assert total_exposure > 0, "no exposure"

    count: uint256 = 0
    remaining: uint256 = requested

    origin_part: uint256 = requested * policy.retained_exposure // total_exposure
    if origin_part > policy.retained_exposure:
        origin_part = policy.retained_exposure
    if origin_part > 0:
        self.claim_pool_id[claim_id][count] = policy.pool_id
        self.claim_pool_amount[claim_id][count] = origin_part
        self.pools[policy.pool_id].pending_claims += origin_part
        count += 1
        if remaining >= origin_part:
            remaining -= origin_part
        else:
            remaining = 0

    for i: uint256 in range(MAX_CESSIONS):
        if i < policy.cession_count:
            cession_pool: uint256 = self.policy_cession_pool[policy_id][i]
            cession_amount: uint256 = self.policy_cession_amount[policy_id][i]
            if cession_pool != 0 and cession_amount > 0 and count < MAX_CESSIONS + 1:
                part: uint256 = requested * cession_amount // total_exposure
                if part > cession_amount:
                    part = cession_amount
                if i == policy.cession_count - 1:
                    if remaining > 0:
                        part = self._min(remaining, cession_amount)
                if part > 0:
                    self.claim_pool_id[claim_id][count] = cession_pool
                    self.claim_pool_amount[claim_id][count] = part
                    self.pools[cession_pool].pending_claims += part
                    count += 1
                    if remaining >= part:
                        remaining -= part
                    else:
                        remaining = 0
    self.claim_pool_count[claim_id] = count

@internal
def _release_claim_allocations(claim_id: uint256):
    count: uint256 = self.claim_pool_count[claim_id]
    for i: uint256 in range(MAX_CESSIONS + 1):
        if i < count:
            pool_id: uint256 = self.claim_pool_id[claim_id][i]
            amount: uint256 = self.claim_pool_amount[claim_id][i]
            if pool_id != 0 and amount > 0:
                pending: uint256 = self.pools[pool_id].pending_claims
                if pending >= amount:
                    self.pools[pool_id].pending_claims = pending - amount
                else:
                    self.pools[pool_id].pending_claims = 0

@internal
def _charge_pool_for_claim(pool_id: uint256, exposure_amount: uint256, payout_amount: uint256):
    self._release_pool_exposure(pool_id, exposure_amount)
    if payout_amount > 0:
        assert self.pools[pool_id].total_capital >= payout_amount, "pool capital low"
        self.pools[pool_id].total_capital -= payout_amount
        self.pools[pool_id].paid_claims += payout_amount
        self.pools[pool_id].updated_at = block.timestamp

@external
def transfer_ownership(new_owner: address):
    assert msg.sender == self.owner, "owner only"
    assert new_owner != empty(address), "owner required"
    self.owner = new_owner

@external
def set_treasury(new_treasury: address):
    assert msg.sender == self.owner, "owner only"
    assert new_treasury != empty(address), "treasury required"
    self.treasury = new_treasury

@external
def set_paused(is_paused: bool):
    assert msg.sender == self.owner, "owner only"
    self.paused = is_paused

@external
def set_role(account: address, role: uint256, enabled: bool):
    assert msg.sender == self.owner, "owner only"
    assert account != empty(address), "account required"
    assert role == ROLE_REVIEWER or role == ROLE_ROUTER or role == ROLE_KEEPER, "role invalid"
    self.roles[account][role] = enabled
    log RoleUpdated(account=account, role=role, enabled=enabled)

@external
def create_pool(
    label: bytes32,
    jurisdiction: bytes32,
    min_capital: uint256,
    max_utilization_bps: uint256,
    retention_bps: uint256,
) -> uint256:
    assert not self.paused, "paused"
    assert max_utilization_bps > 0 and max_utilization_bps <= BPS_DENOMINATOR, "utilization invalid"
    assert retention_bps <= BPS_DENOMINATOR, "retention invalid"
    assert self.pool_count < MAX_POOL_COUNT, "pool limit"

    self.pool_count += 1
    pool_id: uint256 = self.pool_count
    self.pools[pool_id] = Pool(
        sponsor=msg.sender,
        label=label,
        jurisdiction=jurisdiction,
        status=POOL_ACTIVE,
        total_capital=0,
        locked_exposure=0,
        pending_claims=0,
        paid_claims=0,
        earned_premiums=0,
        protocol_fees=0,
        min_capital=min_capital,
        max_utilization_bps=max_utilization_bps,
        retention_bps=retention_bps,
        created_at=block.timestamp,
        updated_at=block.timestamp,
    )
    log PoolCreated(pool_id=pool_id, sponsor=msg.sender, label=label)
    return pool_id

@external
def set_pool_status(pool_id: uint256, status: uint256):
    assert msg.sender == self.owner or msg.sender == self.pools[pool_id].sponsor, "pool authority"
    assert self._pool_exists(pool_id), "pool missing"
    assert status == POOL_ACTIVE or status == POOL_PAUSED or status == POOL_INACTIVE, "status invalid"
    self.pools[pool_id].status = status
    self.pools[pool_id].updated_at = block.timestamp

@external
def set_pool_limits(
    pool_id: uint256, min_capital: uint256, max_utilization_bps: uint256, retention_bps: uint256
):
    assert msg.sender == self.owner or msg.sender == self.pools[pool_id].sponsor, "pool authority"
    assert self._pool_exists(pool_id), "pool missing"
    assert max_utilization_bps > 0 and max_utilization_bps <= BPS_DENOMINATOR, "utilization invalid"
    assert retention_bps <= BPS_DENOMINATOR, "retention invalid"
    self.pools[pool_id].min_capital = min_capital
    self.pools[pool_id].max_utilization_bps = max_utilization_bps
    self.pools[pool_id].retention_bps = retention_bps
    self.pools[pool_id].updated_at = block.timestamp
    log PoolLimitsUpdated(
        pool_id=pool_id,
        min_capital=min_capital,
        max_utilization_bps=max_utilization_bps,
        retention_bps=retention_bps,
    )

@external
def configure_product(
    product_id: uint256,
    label: bytes32,
    base_rate_bps: uint256,
    min_premium: uint256,
    deductible_bps: uint256,
    claim_window_days: uint256,
    max_cover: uint256,
    active: bool,
):
    assert msg.sender == self.owner, "owner only"
    assert product_id > 0 and product_id <= MAX_PRODUCTS, "product invalid"
    assert base_rate_bps > 0 and base_rate_bps <= BPS_DENOMINATOR, "rate invalid"
    assert deductible_bps <= BPS_DENOMINATOR, "deductible invalid"
    assert claim_window_days <= MAX_POLICY_DAYS, "window invalid"
    if product_id > self.product_count:
        assert product_id == self.product_count + 1, "product sequence"
        self.product_count = product_id
    self.products[product_id] = Product(
        label=label,
        base_rate_bps=base_rate_bps,
        min_premium=min_premium,
        deductible_bps=deductible_bps,
        claim_window_days=claim_window_days,
        max_cover=max_cover,
        active=active,
    )
    log ProductConfigured(product_id=product_id, label=label, base_rate_bps=base_rate_bps)

@external
def set_incident_signal(incident_hash: bytes32, active: bool):
    assert self._has_role(msg.sender, ROLE_KEEPER), "keeper only"
    self.incident_signals[incident_hash] = active

@external
@payable
def deposit_capital(pool_id: uint256, receiver: address) -> uint256:
    assert not self.paused, "paused"
    assert self._active_pool(pool_id), "pool inactive"
    assert msg.value > 0, "value required"
    assert receiver != empty(address), "receiver required"

    self.pool_shares[pool_id][receiver] += msg.value
    self.pools[pool_id].total_capital += msg.value
    self.pools[pool_id].updated_at = block.timestamp

    log CapitalDeposited(pool_id=pool_id, provider=receiver, amount=msg.value, shares=msg.value)
    return msg.value

@external
def withdraw_capital(pool_id: uint256, amount: uint256, receiver: address):
    assert not self.paused, "paused"
    assert self._pool_exists(pool_id), "pool missing"
    assert amount > 0, "amount required"
    assert receiver != empty(address), "receiver required"
    assert self.pool_shares[pool_id][msg.sender] >= amount, "shares low"
    assert self._free_capital(pool_id) >= amount, "capital locked"

    self.pool_shares[pool_id][msg.sender] -= amount
    self.pools[pool_id].total_capital -= amount
    self.pools[pool_id].updated_at = block.timestamp

    send(receiver, amount)
    log CapitalWithdrawn(pool_id=pool_id, provider=msg.sender, receiver=receiver, amount=amount)

@external
@view
def quote_premium(pool_id: uint256, product_id: uint256, coverage: uint256, duration_days: uint256) -> uint256:
    assert self._active_pool(pool_id), "pool inactive"
    assert self._product_active(product_id), "product inactive"
    assert duration_days >= MIN_POLICY_DAYS and duration_days <= MAX_POLICY_DAYS, "duration invalid"
    product: Product = self.products[product_id]
    assert product.max_cover == 0 or coverage <= product.max_cover, "cover too large"
    return self._quote_product_premium(product_id, coverage, duration_days, self._utilization_bps(pool_id))

@external
@payable
def buy_policy(
    pool_id: uint256,
    product_id: uint256,
    subject: bytes32,
    coverage: uint256,
    duration_days: uint256,
    beneficiary: address,
) -> uint256:
    assert not self.paused, "paused"
    assert self._active_pool(pool_id), "pool inactive"
    assert self._product_active(product_id), "product inactive"
    assert beneficiary != empty(address), "beneficiary required"
    assert coverage > 0, "coverage required"
    assert duration_days >= MIN_POLICY_DAYS and duration_days <= MAX_POLICY_DAYS, "duration invalid"
    product: Product = self.products[product_id]
    assert product.max_cover == 0 or coverage <= product.max_cover, "cover too large"
    assert self._available_capacity(pool_id) >= coverage, "capacity exceeded"

    premium: uint256 = self._quote_product_premium(product_id, coverage, duration_days, self._utilization_bps(pool_id))
    assert msg.value >= premium, "premium low"

    protocol_fee: uint256 = premium // 10
    pool_premium: uint256 = premium - protocol_fee

    self.pools[pool_id].total_capital += pool_premium
    self.pools[pool_id].earned_premiums += pool_premium
    self.pools[pool_id].protocol_fees += protocol_fee
    self._lock_pool_exposure(pool_id, coverage)

    self.policy_count += 1
    policy_id: uint256 = self.policy_count
    expiration: uint256 = block.timestamp + duration_days * SECONDS_PER_DAY
    claim_window_end: uint256 = expiration + product.claim_window_days * SECONDS_PER_DAY

    self.policies[policy_id] = Policy(
        holder=msg.sender,
        beneficiary=beneficiary,
        pool_id=pool_id,
        product_id=product_id,
        subject=subject,
        coverage=coverage,
        premium=premium,
        start_time=block.timestamp,
        expiration_time=expiration,
        claim_window_end=claim_window_end,
        retained_exposure=coverage,
        ceded_exposure=0,
        paid_amount=0,
        status=POLICY_ACTIVE,
        cession_count=0,
        created_at=block.timestamp,
        updated_at=block.timestamp,
    )

    if msg.value > premium:
        send(msg.sender, msg.value - premium)

    log PolicyIssued(
        policy_id=policy_id,
        pool_id=pool_id,
        holder=msg.sender,
        coverage=coverage,
        premium=premium,
    )
    return policy_id

@external
def transfer_policy_exposure(policy_id: uint256, to_pool_id: uint256, amount: uint256):
    assert not self.paused, "paused"
    assert self._has_role(msg.sender, ROLE_ROUTER), "router only"
    assert self._policy_exists(policy_id), "policy missing"
    assert self._active_pool(to_pool_id), "target inactive"
    assert amount > 0, "amount required"
    policy: Policy = self.policies[policy_id]
    assert policy.status == POLICY_ACTIVE, "policy inactive"
    assert policy.pool_id != to_pool_id, "same pool"
    assert block.timestamp < policy.expiration_time, "policy expired"
    assert policy.retained_exposure >= amount, "retention low"

    self._lock_pool_exposure(to_pool_id, amount)
    self._release_pool_exposure(policy.pool_id, amount)
    self._add_cession(policy_id, to_pool_id, amount)

    self.policies[policy_id].retained_exposure = policy.retained_exposure - amount
    self.policies[policy_id].ceded_exposure = policy.ceded_exposure + amount
    self.policies[policy_id].updated_at = block.timestamp

    log PolicyExposureTransferred(
        policy_id=policy_id,
        from_pool=policy.pool_id,
        to_pool=to_pool_id,
        amount=amount,
    )

@external
def submit_claim(policy_id: uint256, amount: uint256, incident_hash: bytes32, evidence_hash: bytes32) -> uint256:
    assert not self.paused, "paused"
    assert self._policy_exists(policy_id), "policy missing"
    assert amount > 0, "amount required"
    policy: Policy = self.policies[policy_id]
    assert policy.status == POLICY_ACTIVE, "policy inactive"
    assert msg.sender == policy.holder or msg.sender == policy.beneficiary, "claimant invalid"
    assert block.timestamp <= policy.claim_window_end, "claim window closed"
    assert amount <= policy.coverage - policy.paid_amount, "amount too high"
    assert self.incident_signals[incident_hash], "incident inactive"

    self.claim_count += 1
    claim_id: uint256 = self.claim_count
    self.claims[claim_id] = Claim(
        policy_id=policy_id,
        claimant=msg.sender,
        beneficiary=policy.beneficiary,
        amount_requested=amount,
        amount_approved=0,
        amount_paid=0,
        evidence_hash=evidence_hash,
        incident_hash=incident_hash,
        submitted_at=block.timestamp,
        reviewed_at=0,
        paid_at=0,
        status=CLAIM_SUBMITTED,
    )
    self._register_claim_allocations(claim_id, policy_id, amount)

    log ClaimSubmitted(claim_id=claim_id, policy_id=policy_id, claimant=msg.sender, amount=amount)
    return claim_id

@external
def mark_claim_reviewed(claim_id: uint256):
    assert self._has_role(msg.sender, ROLE_REVIEWER), "reviewer only"
    assert self._claim_exists(claim_id), "claim missing"
    assert self.claims[claim_id].status == CLAIM_SUBMITTED, "claim state"
    self.claims[claim_id].status = CLAIM_REVIEWED
    self.claims[claim_id].reviewed_at = block.timestamp
    log ClaimReviewed(
        claim_id=claim_id,
        reviewer=msg.sender,
        status=CLAIM_REVIEWED,
        approved_amount=0,
    )

@external
def approve_claim(claim_id: uint256, approved_amount: uint256):
    assert self._has_role(msg.sender, ROLE_REVIEWER), "reviewer only"
    assert self._claim_exists(claim_id), "claim missing"
    claim: Claim = self.claims[claim_id]
    assert claim.status == CLAIM_SUBMITTED or claim.status == CLAIM_REVIEWED, "claim state"
    assert approved_amount > 0 and approved_amount <= claim.amount_requested, "approval invalid"
    policy: Policy = self.policies[claim.policy_id]
    product: Product = self.products[policy.product_id]

    deductible: uint256 = approved_amount * product.deductible_bps // BPS_DENOMINATOR
    net_amount: uint256 = approved_amount - deductible
    assert net_amount <= policy.coverage - policy.paid_amount, "policy exhausted"

    self.claims[claim_id].amount_approved = net_amount
    self.claims[claim_id].status = CLAIM_APPROVED
    self.claims[claim_id].reviewed_at = block.timestamp

    log ClaimReviewed(
        claim_id=claim_id,
        reviewer=msg.sender,
        status=CLAIM_APPROVED,
        approved_amount=net_amount,
    )

@external
def reject_claim(claim_id: uint256):
    assert self._has_role(msg.sender, ROLE_REVIEWER), "reviewer only"
    assert self._claim_exists(claim_id), "claim missing"
    claim: Claim = self.claims[claim_id]
    assert claim.status == CLAIM_SUBMITTED or claim.status == CLAIM_REVIEWED, "claim state"

    self._release_claim_allocations(claim_id)
    self.claims[claim_id].status = CLAIM_REJECTED
    self.claims[claim_id].reviewed_at = block.timestamp
    log ClaimReviewed(
        claim_id=claim_id,
        reviewer=msg.sender,
        status=CLAIM_REJECTED,
        approved_amount=0,
    )

@external
def settle_claim(claim_id: uint256):
    assert not self.paused, "paused"
    assert self._has_role(msg.sender, ROLE_KEEPER), "keeper only"
    assert self._claim_exists(claim_id), "claim missing"
    claim: Claim = self.claims[claim_id]
    assert claim.status == CLAIM_APPROVED, "claim state"
    assert claim.amount_approved > 0, "no approval"

    policy: Policy = self.policies[claim.policy_id]
    payout: uint256 = claim.amount_approved
    requested: uint256 = claim.amount_requested
    count: uint256 = self.claim_pool_count[claim_id]
    paid_from_pools: uint256 = 0

    for i: uint256 in range(MAX_CESSIONS + 1):
        if i < count:
            pool_id: uint256 = self.claim_pool_id[claim_id][i]
            exposure_amount: uint256 = self.claim_pool_amount[claim_id][i]
            payout_part: uint256 = payout * exposure_amount // requested
            if i == count - 1:
                payout_part = payout - paid_from_pools
            if pool_id != 0 and exposure_amount > 0:
                pending: uint256 = self.pools[pool_id].pending_claims
                if pending >= exposure_amount:
                    self.pools[pool_id].pending_claims = pending - exposure_amount
                else:
                    self.pools[pool_id].pending_claims = 0
                self._charge_pool_for_claim(pool_id, exposure_amount, payout_part)
                paid_from_pools += payout_part

    self.claims[claim_id].amount_paid = payout
    self.claims[claim_id].paid_at = block.timestamp
    self.claims[claim_id].status = CLAIM_PAID
    self.policies[claim.policy_id].paid_amount = policy.paid_amount + payout
    self.policies[claim.policy_id].status = POLICY_CLAIMED
    self.policies[claim.policy_id].updated_at = block.timestamp

    send(claim.beneficiary, payout)
    log ClaimPaid(claim_id=claim_id, policy_id=claim.policy_id, beneficiary=claim.beneficiary, amount=payout)

@external
def expire_policy(policy_id: uint256):
    assert not self.paused, "paused"
    assert self._policy_exists(policy_id), "policy missing"
    policy: Policy = self.policies[policy_id]
    assert policy.status == POLICY_ACTIVE, "policy inactive"
    assert block.timestamp > policy.expiration_time, "not expired"

    self._release_pool_exposure(policy.pool_id, policy.coverage)

    for i: uint256 in range(MAX_CESSIONS):
        if i < policy.cession_count:
            cession_pool: uint256 = self.policy_cession_pool[policy_id][i]
            cession_amount: uint256 = self.policy_cession_amount[policy_id][i]
            if cession_pool != 0 and cession_amount > 0:
                self._release_pool_exposure(cession_pool, cession_amount)
                self._clear_cession_slot(policy_id, i)

    self.policies[policy_id].retained_exposure = 0
    self.policies[policy_id].ceded_exposure = 0
    self.policies[policy_id].cession_count = 0
    self.policies[policy_id].status = POLICY_EXPIRED
    self.policies[policy_id].updated_at = block.timestamp

    log PolicyExpired(policy_id=policy_id, pool_id=policy.pool_id, coverage=policy.coverage)

@external
def record_epoch_snapshot(pool_id: uint256) -> uint256:
    assert self._has_role(msg.sender, ROLE_KEEPER), "keeper only"
    assert self._pool_exists(pool_id), "pool missing"
    self.epoch_count += 1
    epoch_id: uint256 = self.epoch_count
    self.epochs[epoch_id] = EpochSnapshot(
        timestamp=block.timestamp,
        pool_id=pool_id,
        total_capital=self.pools[pool_id].total_capital,
        locked_exposure=self.pools[pool_id].locked_exposure,
        pending_claims=self.pools[pool_id].pending_claims,
        paid_claims=self.pools[pool_id].paid_claims,
        utilization_bps=self._utilization_bps(pool_id),
        solvency_bps=self._solvency_bps(pool_id),
    )
    log EpochRecorded(
        epoch_id=epoch_id,
        pool_id=pool_id,
        utilization_bps=self._utilization_bps(pool_id),
        solvency_bps=self._solvency_bps(pool_id),
    )
    return epoch_id

@external
def sweep_protocol_fees(pool_id: uint256):
    assert msg.sender == self.owner, "owner only"
    assert self._pool_exists(pool_id), "pool missing"
    amount: uint256 = self.pools[pool_id].protocol_fees
    assert amount > 0, "no fees"
    self.pools[pool_id].protocol_fees = 0
    send(self.treasury, amount)

@external
@view
def available_capacity(pool_id: uint256) -> uint256:
    assert self._pool_exists(pool_id), "pool missing"
    return self._available_capacity(pool_id)

@external
@view
def free_capital(pool_id: uint256) -> uint256:
    assert self._pool_exists(pool_id), "pool missing"
    return self._free_capital(pool_id)

@external
@view
def utilization_bps(pool_id: uint256) -> uint256:
    assert self._pool_exists(pool_id), "pool missing"
    return self._utilization_bps(pool_id)

@external
@view
def solvency_bps(pool_id: uint256) -> uint256:
    assert self._pool_exists(pool_id), "pool missing"
    return self._solvency_bps(pool_id)

@external
@view
def policy_total_exposure(policy_id: uint256) -> uint256:
    assert self._policy_exists(policy_id), "policy missing"
    return self._policy_total_exposure(policy_id)

@external
@view
def policy_pool_allocation(policy_id: uint256, pool_id: uint256) -> uint256:
    assert self._policy_exists(policy_id), "policy missing"
    assert self._pool_exists(pool_id), "pool missing"
    return self._policy_pool_allocation(policy_id, pool_id)

@external
@view
def policy_is_claimable(policy_id: uint256) -> bool:
    if not self._policy_exists(policy_id):
        return False
    policy: Policy = self.policies[policy_id]
    if policy.status != POLICY_ACTIVE:
        return False
    return block.timestamp <= policy.claim_window_end

@external
@view
def pool_can_withdraw(pool_id: uint256, provider: address, amount: uint256) -> bool:
    if not self._pool_exists(pool_id):
        return False
    if self.pool_shares[pool_id][provider] < amount:
        return False
    return self._free_capital(pool_id) >= amount

@external
@view
def pool_risk_summary(pool_id: uint256) -> (uint256, uint256, uint256, uint256, uint256):
    assert self._pool_exists(pool_id), "pool missing"
    return (
        self.pools[pool_id].total_capital,
        self.pools[pool_id].locked_exposure,
        self.pools[pool_id].pending_claims,
        self._utilization_bps(pool_id),
        self._solvency_bps(pool_id),
    )

@external
@view
def claim_allocation(claim_id: uint256, slot: uint256) -> (uint256, uint256):
    assert self._claim_exists(claim_id), "claim missing"
    assert slot < MAX_CESSIONS + 1, "slot invalid"
    return (self.claim_pool_id[claim_id][slot], self.claim_pool_amount[claim_id][slot])

@external
@view
def cession_allocation(policy_id: uint256, slot: uint256) -> (uint256, uint256):
    assert self._policy_exists(policy_id), "policy missing"
    assert slot < MAX_CESSIONS, "slot invalid"
    return (self.policy_cession_pool[policy_id][slot], self.policy_cession_amount[policy_id][slot])
