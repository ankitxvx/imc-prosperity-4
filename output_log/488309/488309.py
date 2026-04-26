import json
import math
from typing import Dict, List, Any
from datamodel import OrderDepth, TradingState, Order, Trade


class MathUtils:
    @staticmethod
    def cdf(x: float) -> float:
        return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

    @staticmethod
    def pdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    @staticmethod
    def bs_call(S: float, K: float, T: float, sigma: float, r: float = 0.0):
        if T <= 0 or sigma <= 0:
            return max(S - K, 0), (1.0 if S > K else 0.0), 0.0
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * MathUtils.cdf(d1) - K * math.exp(-r * T) * MathUtils.cdf(d2)
        delta = MathUtils.cdf(d1)
        vega = S * MathUtils.pdf(d1) * math.sqrt(T)
        return price, delta, vega

    @staticmethod
    def implied_vol(market_price: float, S: float, K: float, T: float,
                    r: float = 0.0, initial_guess: float = 0.3) -> float:
        if T <= 0:
            return initial_guess
        intrinsic = max(S - K, 0)
        if market_price <= intrinsic + 0.01:
            return initial_guess
        sigma = initial_guess
        for _ in range(20):
            price, _, vega = MathUtils.bs_call(S, K, T, sigma, r)
            if vega < 1e-8:
                break
            diff = price - market_price
            if abs(diff) < 1e-4:
                break
            sigma -= diff / vega
            if sigma <= 0.001:
                sigma = 0.001
                break
        return min(max(sigma, 0.01), 3.0)


class Trader:
    def __init__(self):
        self.limits = {
            'HYDROGEL_PACK': 200,
            'VELVETFRUIT_EXTRACT': 200,
            'VEV_4000': 300, 'VEV_4500': 300, 'VEV_5000': 300, 'VEV_5100': 300,
            'VEV_5200': 300, 'VEV_5300': 300, 'VEV_5400': 300, 'VEV_5500': 300,
            'VEV_6000': 300, 'VEV_6500': 300,
        }
        # Round 4: TTE starts at 4 days
        self.BASE_TTE_DAYS = 4.0
        self.DAYS_PER_YEAR = 365.0

        self.state_data = {
            'ema': {'HYDROGEL_PACK': None, 'VELVETFRUIT_EXTRACT': None},
            'iv_ema': 0.15,
            'days_elapsed': 0,
            'last_timestamp': -1,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_mid_price(self, od: OrderDepth) -> float:
        bb = max(od.buy_orders.keys()) if od.buy_orders else None
        ba = min(od.sell_orders.keys()) if od.sell_orders else None
        if bb and ba:
            return (bb + ba) / 2.0
        elif bb:
            return float(bb)
        elif ba:
            return float(ba)
        return 0.0

    def _get_vwap(self, od: OrderDepth) -> float:
        vp, tv = 0.0, 0.0
        for p, v in od.buy_orders.items():
            vp += p * v; tv += v
        for p, v in od.sell_orders.items():
            vp += p * abs(v); tv += abs(v)
        return vp / tv if tv > 0 else 0.0

    def _best_bid(self, od: OrderDepth, fallback: float) -> float:
        return max(od.buy_orders.keys()) if od.buy_orders else fallback

    def _best_ask(self, od: OrderDepth, fallback: float) -> float:
        return min(od.sell_orders.keys()) if od.sell_orders else fallback

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, state: TradingState):
        result = {}
        conversions = 0

        # ── 1. Restore persisted state ──────────────────────────────────
        if state.traderData:
            try:
                self.state_data = json.loads(state.traderData)
            except Exception:
                pass

        # ── 2. Day-rollover detection (fixes the R3 TTE bug) ────────────
        last_ts = self.state_data.get('last_timestamp', -1)
        if last_ts >= 0 and state.timestamp < last_ts - 50_000:
            # timestamp wrapped back to ~0: new day
            self.state_data['days_elapsed'] = self.state_data.get('days_elapsed', 0) + 1
        self.state_data['last_timestamp'] = state.timestamp

        days_elapsed = self.state_data.get('days_elapsed', 0)

        # Correct TTE: base days minus whole days elapsed minus intra-day fraction
        T_years = max(
            (self.BASE_TTE_DAYS - days_elapsed - state.timestamp / 1_000_000.0) / self.DAYS_PER_YEAR,
            1e-6
        )

        # ── 3. Market data: mids, vwaps, EMAs ───────────────────────────
        mids, vwaps = {}, {}
        for product, od in state.order_depths.items():
            mids[product] = self._get_mid_price(od)
            vwaps[product] = self._get_vwap(od)
            if product in ('HYDROGEL_PACK', 'VELVETFRUIT_EXTRACT'):
                prev_ema = self.state_data['ema'].get(product)
                if prev_ema is None:
                    self.state_data['ema'][product] = mids[product]
                else:
                    alpha = 0.25
                    self.state_data['ema'][product] = (
                        alpha * mids[product] + (1 - alpha) * prev_ema
                    )

        S = mids.get('VELVETFRUIT_EXTRACT', 5250.0)

        # ── 4. Update implied-vol EMA from ATM option ───────────────────
        atm_strike = min(
            [int(k.split('_')[1]) for k in self.limits if 'VEV' in k],
            key=lambda k: abs(k - S)
        )
        atm_product = f'VEV_{atm_strike}'
        current_iv = self.state_data['iv_ema']
        if atm_product in mids and mids[atm_product] > 0 and T_years > 1e-5:
            iv = MathUtils.implied_vol(
                mids[atm_product], S, atm_strike, T_years,
                initial_guess=self.state_data['iv_ema']
            )
            if 0.01 <= iv <= 3.0:
                self.state_data['iv_ema'] = 0.15 * iv + 0.85 * self.state_data['iv_ema']
                current_iv = self.state_data['iv_ema']

        # ── 5. Counterparty signal: detect Mark 67 buying ───────────────
        #
        # Mark 67 is a one-way VELVETFRUIT buyer.  After each of its buys,
        # the mid price rises ~+9 ticks on average.  We front-run by going
        # long immediately when we see it in market_trades.
        #
        mark67_signal = False
        vf_market_trades = state.market_trades.get('VELVETFRUIT_EXTRACT', [])
        for t in vf_market_trades:
            if getattr(t, 'buyer', '') == 'Mark 67':
                mark67_signal = True
                break

        # ── 6. Market-make options; accumulate net option delta ──────────
        net_option_delta = 0.0
        option_products = [p for p in state.order_depths if p.startswith('VEV_')]

        for product in option_products:
            strike = float(product.split('_')[1])
            pos = state.position.get(product, 0)
            limit = self.limits[product]
            od = state.order_depths[product]

            fair_price, delta, _ = MathUtils.bs_call(S, strike, T_years, current_iv)
            net_option_delta += delta * pos

            bb = self._best_bid(od, fair_price - 2)
            ba = self._best_ask(od, fair_price + 2)

            # Position skew: lean away from current position
            skew = (pos / limit) * 10.0

            # OTM options (strike > S+100): tighten asks to compete with
            # Mark 22 and capture systematic Mark 01 buying flow.
            is_otm = strike > S + 100
            half_spread = 0.75 if is_otm else 1.5

            our_bid = math.floor(fair_price - half_spread - skew)
            our_ask = math.ceil(fair_price + half_spread - skew)

            # Penny into the spread if it's wide enough
            if (ba - bb) > 2:
                our_bid = min(our_bid, bb + 1)
                our_ask = max(our_ask, ba - 1)

            # Never cross our own quotes
            if our_bid >= our_ask:
                our_bid = our_ask - 1

            orders = []
            if pos < limit:
                orders.append(Order(product, int(our_bid), limit - pos))
            if pos > -limit:
                orders.append(Order(product, int(our_ask), -(limit + pos)))
            result[product] = orders

        # ── 7. Market-make VELVETFRUIT_EXTRACT with Mark 67 front-run ───
        if 'VELVETFRUIT_EXTRACT' in state.order_depths:
            product = 'VELVETFRUIT_EXTRACT'
            pos = state.position.get(product, 0)
            limit = self.limits[product]
            od = state.order_depths[product]

            ema_val = self.state_data['ema'].get(product, S)
            fair = ema_val * 0.4 + vwaps[product] * 0.6

            # Delta-hedge target: offset net option delta
            target_pos = -net_option_delta

            # Mark 67 front-run: override target to go max long
            if mark67_signal:
                target_pos = limit  # buy as much as we can

            pos_offset = pos - target_pos
            skew = (pos_offset / limit) * 6.0

            bb = self._best_bid(od, fair - 1)
            ba = self._best_ask(od, fair + 1)

            our_bid = math.floor(fair - 0.5 - skew)
            our_ask = math.ceil(fair + 0.5 - skew)

            if (ba - bb) > 1:
                our_bid = min(our_bid, bb + 1)
                our_ask = max(our_ask, ba - 1)

            if our_bid >= our_ask:
                our_bid = our_ask - 1

            bid_qty = limit - pos
            ask_qty = -(limit + pos)

            orders = []
            if bid_qty > 0:
                orders.append(Order(product, int(our_bid), bid_qty))
            if ask_qty < 0:
                orders.append(Order(product, int(our_ask), ask_qty))
            result[product] = orders

        # ── 8. Market-make HYDROGEL_PACK ────────────────────────────────
        if 'HYDROGEL_PACK' in state.order_depths:
            product = 'HYDROGEL_PACK'
            pos = state.position.get(product, 0)
            limit = self.limits[product]
            od = state.order_depths[product]

            ema_val = self.state_data['ema'].get(product, mids.get(product, 10000.0))
            fair = ema_val * 0.4 + vwaps[product] * 0.6

            skew = (pos / limit) * 6.0

            bb = self._best_bid(od, fair - 1)
            ba = self._best_ask(od, fair + 1)

            our_bid = math.floor(fair - 0.5 - skew)
            our_ask = math.ceil(fair + 0.5 - skew)

            if (ba - bb) > 1:
                our_bid = min(our_bid, bb + 1)
                our_ask = max(our_ask, ba - 1)

            if our_bid >= our_ask:
                our_bid = our_ask - 1

            bid_qty = limit - pos
            ask_qty = -(limit + pos)

            orders = []
            if bid_qty > 0:
                orders.append(Order(product, int(our_bid), bid_qty))
            if ask_qty < 0:
                orders.append(Order(product, int(our_ask), ask_qty))
            result[product] = orders

        traderData = json.dumps(self.state_data)
        return result, conversions, traderData