import json
from trader import Trader
from datamodel import TradingState, OrderDepth, Trade

def test_trader():
    t = Trader()
    
    # Mocking a basic state
    listings = {}
    order_depths = {
        'HYDROGEL_PACK': OrderDepth(),
        'VELVETFRUIT_EXTRACT': OrderDepth(),
        'VEV_5000': OrderDepth()
    }
    order_depths['HYDROGEL_PACK'].buy_orders = {9950: 10}
    order_depths['HYDROGEL_PACK'].sell_orders = {9960: -10}
    order_depths['VELVETFRUIT_EXTRACT'].buy_orders = {5240: 10}
    order_depths['VELVETFRUIT_EXTRACT'].sell_orders = {5250: -10}
    order_depths['VEV_5000'].buy_orders = {250: 10}
    order_depths['VEV_5000'].sell_orders = {260: -10}
    
    own_trades = {}
    market_trades = {
        'VELVETFRUIT_EXTRACT': [Trade('VELVETFRUIT_EXTRACT', 5245, 20, buyer='Mark 67', seller='Mark 49', timestamp=100)],
        'VEV_5000': [Trade('VEV_5000', 255, 10, buyer='Mark 01', seller='Mark 22', timestamp=100)]
    }
    position = {'HYDROGEL_PACK': 0, 'VELVETFRUIT_EXTRACT': 0, 'VEV_5000': 0}
    observations = None
    
    state = TradingState(
        traderData="",
        timestamp=1000,
        listings=listings,
        order_depths=order_depths,
        own_trades=own_trades,
        market_trades=market_trades,
        position=position,
        observations=observations
    )
    
    result, conversions, traderData = t.run(state)
    print("Execution successful!")
    print("TraderData sample:", traderData[:200])
    
    # Check if flow was recorded
    data = json.loads(traderData)
    print("Bot Flow Sample (Velvetfruit):", data['bot_flow'].get('VELVETFRUIT_EXTRACT'))
    print("Bot Flow Sample (VEV_5000):", data['bot_flow'].get('VEV_5000'))

if __name__ == '__main__':
    test_trader()
