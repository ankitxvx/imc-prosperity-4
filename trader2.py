from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import jsonpickle

class Trader:

    # -------- CONFIG --------
    POSITION_LIMITS = {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
    }

    VOUCHER_LIMIT = 300

    # Key participants
    MARK_01 = "Mark 01"  # buyer
    MARK_22 = "Mark 22"  # seller
    MARK_67 = "Mark 67"  # velvet buyer
    MARK_49 = "Mark 49"  # velvet seller

    FLOW_DECAY = 0.9
    FLOW_IMPACT = 0.05

    def run(self, state: TradingState):

        # -------- LOAD STATE --------
        if state.traderData:
            data = jsonpickle.decode(state.traderData)
        else:
            data = {"flow": {}}

        flow: Dict = data["flow"]
        result = {}

        # -------- DECAY OLD FLOW --------
        for product in flow:
            for trader in flow[product]:
                flow[product][trader] *= self.FLOW_DECAY

        # -------- UPDATE FLOW FROM TRADES --------
        for product, trades in state.market_trades.items():
            if product not in flow:
                flow[product] = {}

            for trade in trades:
                buyer = trade.buyer
                seller = trade.seller
                qty = trade.quantity

                if buyer:
                    flow[product][buyer] = flow[product].get(buyer, 0) + qty
                if seller:
                    flow[product][seller] = flow[product].get(seller, 0) - qty

        # -------- MAIN TRADING LOOP --------
        for product, order_depth in state.order_depths.items():

            orders: List[Order] = []

            if not order_depth.buy_orders or not order_depth.sell_orders:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2

            position = state.position.get(product, 0)
            product_flow = flow.get(product, {})

            # -------- FAIR PRICE --------
            fair_price = mid_price

            # Velvetfruit momentum signal
            if product == "VELVETFRUIT_EXTRACT":
                f67 = product_flow.get(self.MARK_67, 0)
                f49 = product_flow.get(self.MARK_49, 0)
                net_flow = f67 - abs(f49)
                fair_price += self.FLOW_IMPACT * net_flow

            # -------- BUY LOGIC --------
            if best_ask < fair_price:
                volume = min(-order_depth.sell_orders[best_ask], 10)

                # Voucher special: exploit Mark 22 dumping
                if "VOUCHER" in product:
                    if product_flow.get(self.MARK_22, 0) < -20:
                        volume = min(volume * 2, 50)

                # Position limit check
                limit = self.VOUCHER_LIMIT if "VOUCHER" in product else self.POSITION_LIMITS.get(product, 100)
                volume = min(volume, limit - position)

                if volume > 0:
                    orders.append(Order(product, best_ask, volume))

            # -------- SELL LOGIC --------
            if best_bid > fair_price:
                volume = min(order_depth.buy_orders[best_bid], 10)

                # Voucher special: sell to Mark 01
                if "VOUCHER" in product:
                    if product_flow.get(self.MARK_01, 0) > 20:
                        volume = min(volume * 2, 50)

                # Position limit check
                limit = self.VOUCHER_LIMIT if "VOUCHER" in product else self.POSITION_LIMITS.get(product, 100)
                volume = min(volume, position + limit)

                if volume > 0:
                    orders.append(Order(product, best_bid, -volume))

            result[product] = orders

        # -------- SAVE STATE --------
        traderData = jsonpickle.encode(data)

        return result, 0, traderData