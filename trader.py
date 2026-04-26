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
            return max(S - K, 0), (1.0 if S > K else 0.0)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * MathUtils.cdf(d1) - K * math.exp(-r * T) * MathUtils.cdf(d2)
        delta = MathUtils.cdf(d1)
        vega = S * MathUtils.pdf(d1) * math.sqrt(T)
        return price, delta, vega

    @staticmethod
    def implied_vol(market_price: float, S: float, K: float, T: float, r: float = 0.0, initial_guess: float = 0.3) -> float:
        if T <= 0: return initial_guess
        intrinsic = max(S - K, 0)
        if market_price <= intrinsic + 0.01: return initial_guess
        sigma = initial_guess
        for _ in range(20):
            price, _, vega = MathUtils.bs_call(S, K, T, sigma, r)
            if vega < 1e-8: break
            diff = price - market_price
            if abs(diff) < 1e-4: break
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
            'VEV_4000': 300, 'VEV_4500': 300, 'VEV_5000': 300, 'VEV_5100': 300, 'VEV_5200': 300, 
            'VEV_5300': 300, 'VEV_5400': 300, 'VEV_5500': 300, 'VEV_6000': 300, 'VEV_6500': 300
        }
        self.DAYS_PER_YEAR = 365.0
        # Initialize default state
        self.state_data = {
            'ema': {'HYDROGEL_PACK': None, 'VELVETFRUIT_EXTRACT': None},
            'iv_ema': 0.15,
            'base_tte_days': 4.0, # Round 4 starts at TTE=4 days
            'bot_flow': {} # {product: {bot_name: flow}}
        }

    def _get_mid_price(self, order_depth: OrderDepth) -> float:
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
        if best_bid and best_ask:
            return (best_bid + best_ask) / 2.0
        elif best_bid: return float(best_bid)
        elif best_ask: return float(best_ask)
        return 0.0

    def _get_vwap(self, order_depth: OrderDepth) -> float:
        vol_price_sum = 0
        total_vol = 0
        for price, vol in order_depth.buy_orders.items():
            vol_price_sum += price * vol
            total_vol += vol
        for price, vol in order_depth.sell_orders.items():
            vol_price_sum += price * abs(vol)
            total_vol += abs(vol)
        return vol_price_sum / total_vol if total_vol > 0 else 0.0

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        
        # 1. Restore State
        if state.traderData:
            try:
                self.state_data = json.loads(state.traderData)
            except Exception:
                pass
        
        # 2. Track Bot Flow
        # Reset current iteration flow but keep a small decay for momentum
        if 'bot_flow' not in self.state_data:
            self.state_data['bot_flow'] = {}
            
        for product in state.order_depths:
            if product not in self.state_data['bot_flow']:
                self.state_data['bot_flow'][product] = {}
            
            # Decay old flow
            for bot in self.state_data['bot_flow'][product]:
                self.state_data['bot_flow'][product][bot] *= 0.5
                
            # Process Market Trades
            if product in state.market_trades:
                for trade in state.market_trades[product]:
                    # Update buyer flow
                    if trade.buyer not in self.state_data['bot_flow'][product]:
                        self.state_data['bot_flow'][product][trade.buyer] = 0
                    self.state_data['bot_flow'][product][trade.buyer] += trade.quantity
                    # Update seller flow
                    if trade.seller not in self.state_data['bot_flow'][product]:
                        self.state_data['bot_flow'][product][trade.seller] = 0
                    self.state_data['bot_flow'][product][trade.seller] -= trade.quantity

            # Process Own Trades (to see which bot we traded with)
            if product in state.own_trades:
                for trade in state.own_trades[product]:
                    counterparty = trade.seller if trade.buyer == "SUBMISSION" else trade.buyer
                    if counterparty and counterparty != "SUBMISSION":
                        if counterparty not in self.state_data['bot_flow'][product]:
                            self.state_data['bot_flow'][product][counterparty] = 0
                        # If we bought, they sold
                        flow_change = -trade.quantity if trade.buyer == "SUBMISSION" else trade.quantity
                        self.state_data['bot_flow'][product][counterparty] += flow_change

        # 3. Extract Data & Update EMAs
        mids = {}
        vwaps = {}
        for product in state.order_depths:
            mids[product] = self._get_mid_price(state.order_depths[product])
            vwaps[product] = self._get_vwap(state.order_depths[product])
            
            if product in ['HYDROGEL_PACK', 'VELVETFRUIT_EXTRACT']:
                if self.state_data['ema'][product] is None:
                    self.state_data['ema'][product] = mids[product]
                else:
                    alpha = 0.05
                    self.state_data['ema'][product] = alpha * mids[product] + (1 - alpha) * self.state_data['ema'][product]
        
        # Determine TTE
        T_years = (self.state_data['base_tte_days'] - (state.timestamp / 1_000_000.0)) / self.DAYS_PER_YEAR
        
        # Determine target delta for hedging options
        net_option_delta = 0.0
        S = mids.get('VELVETFRUIT_EXTRACT', 5000.0)
        
        # Find ATM Implied Volatility
        atm_strike = min([int(k.split('_')[1]) for k in self.limits.keys() if 'VEV' in k], key=lambda k: abs(k - S))
        atm_product = f'VEV_{atm_strike}'
        current_iv = self.state_data['iv_ema']
        if atm_product in mids and mids[atm_product] > 0 and T_years > 0:
            implied_v = MathUtils.implied_vol(mids[atm_product], S, atm_strike, T_years, r=0.0, initial_guess=self.state_data['iv_ema'])
            if implied_v is not None and 0.01 <= implied_v <= 3.0:
                self.state_data['iv_ema'] = 0.05 * implied_v + 0.95 * self.state_data['iv_ema']
                current_iv = self.state_data['iv_ema']

        # 4. Market Make Options (Vouchers) & Exploiting Mark 01/22
        for product in [p for p in state.order_depths.keys() if 'VEV_' in p]:
            strike = float(product.split('_')[1])
            pos = state.position.get(product, 0)
            limit = self.limits[product]
            
            fair_price, delta, _ = MathUtils.bs_call(S, strike, T_years, current_iv)
            net_option_delta += delta * pos
            
            order_depth = state.order_depths[product]
            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else fair_price - 2
            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else fair_price + 2
            
            # Bot Strategy: Mark 22 (dumps) and Mark 01 (buys)
            # If Mark 22 is active, we want to be at the front of the line to buy
            mark22_active = self.state_data['bot_flow'][product].get('Mark 22', 0) < -5
            mark01_active = self.state_data['bot_flow'][product].get('Mark 01', 0) > 5
            
            skew = (pos / limit) * 5.0
            our_bid = math.floor(fair_price - 1.5 - skew)
            our_ask = math.ceil(fair_price + 1.5 - skew)
            
            if mark22_active: our_bid = max(our_bid, best_bid) # Be aggressive to catch the dump
            if mark01_active: our_ask = min(our_ask, best_ask) # Be aggressive to catch the buy
            
            # Ensure we don't cross ourselves
            if our_bid >= our_ask:
                our_bid = our_ask - 1

            orders = []
            if pos < limit: orders.append(Order(product, int(our_bid), limit - pos))
            if pos > -limit: orders.append(Order(product, int(our_ask), -limit - pos))
            result[product] = orders

        # 5. Market Make Delta-1 Products & Exploiting Mark 67/49
        for product in ['HYDROGEL_PACK', 'VELVETFRUIT_EXTRACT']:
            if product not in state.order_depths: continue
            pos = state.position.get(product, 0)
            limit = self.limits[product]
            
            raw_fair = self.state_data['ema'][product] * 0.4 + vwaps[product] * 0.6
            
            # Bot Strategy: Mark 67 (buys) and Mark 49 (sells) for Velvetfruit
            if product == 'VELVETFRUIT_EXTRACT':
                mark67_flow = self.state_data['bot_flow'][product].get('Mark 67', 0)
                mark49_flow = self.state_data['bot_flow'][product].get('Mark 49', 0)
                if mark67_flow > 10: raw_fair += 1.0 # Shadow the buyer
                if mark49_flow < -10: raw_fair -= 1.0 # Shadow the seller
                
            fair = max(min(raw_fair, mids[product] + 1.5), mids[product] - 1.5)
            
            target_pos = -net_option_delta if product == 'VELVETFRUIT_EXTRACT' else 0
            pos_offset = pos - target_pos
            skew = (pos_offset / limit) * 2.5
            
            order_depth = state.order_depths[product]
            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else fair - 1
            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else fair + 1
            
            our_bid = math.floor(fair - 0.5 - skew)
            our_ask = math.ceil(fair + 0.5 - skew)
            
            our_bid = min(our_bid, best_bid + 1 if (best_ask - best_bid) > 1 else best_bid)
            our_ask = max(our_ask, best_ask - 1 if (best_ask - best_bid) > 1 else best_ask)

            if our_bid >= our_ask:
                our_bid = our_ask - 1
                
            orders = []
            bid_qty = limit - pos
            ask_qty = -limit - pos
            if bid_qty > 0: orders.append(Order(product, int(our_bid), bid_qty))
            if ask_qty < 0: orders.append(Order(product, int(our_ask), ask_qty))
            result[product] = orders
            
        # 6. Cleanup Bot Flow to save space in traderData
        # Filter out small flows and non-Mark bots
        new_bot_flow = {}
        for p in self.state_data['bot_flow']:
            new_bot_flow[p] = {b: f for b, f in self.state_data['bot_flow'][p].items() if abs(f) > 0.1 and 'Mark' in str(b)}
        self.state_data['bot_flow'] = new_bot_flow

        traderData = json.dumps(self.state_data)
        return result, conversions, traderData
