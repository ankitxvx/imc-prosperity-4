import pandas as pd
import glob

def analyze_bots():
    files = glob.glob('ROUND_4/trades_round_4_day_*.csv')
    df_list = []
    for f in files:
        df = pd.read_csv(f, sep=';')
        df_list.append(df)
        
    trades = pd.concat(df_list)
    
    # Analyze by bot
    bots = pd.unique(trades[['buyer', 'seller']].values.ravel('K'))
    
    for bot in sorted(bots):
        print(f"--- {bot} ---")
        bot_trades_buy = trades[trades['buyer'] == bot]
        bot_trades_sell = trades[trades['seller'] == bot]
        
        for symbol in trades['symbol'].unique():
            bought = bot_trades_buy[bot_trades_buy['symbol'] == symbol]['quantity'].sum()
            sold = bot_trades_sell[bot_trades_sell['symbol'] == symbol]['quantity'].sum()
            net = bought - sold
            
            # approximate PnL based on VWAP of their trades
            buy_vol = bot_trades_buy[bot_trades_buy['symbol'] == symbol]['quantity']
            buy_price = bot_trades_buy[bot_trades_buy['symbol'] == symbol]['price']
            buy_vwap = (buy_vol * buy_price).sum() / buy_vol.sum() if buy_vol.sum() > 0 else 0
            
            sell_vol = bot_trades_sell[bot_trades_sell['symbol'] == symbol]['quantity']
            sell_price = bot_trades_sell[bot_trades_sell['symbol'] == symbol]['price']
            sell_vwap = (sell_vol * sell_price).sum() / sell_vol.sum() if sell_vol.sum() > 0 else 0
            
            if bought > 0 or sold > 0:
                print(f"  {symbol}: Net {net:5d} (Bought: {bought}, Sold: {sold}) | Buy VWAP: {buy_vwap:.1f}, Sell VWAP: {sell_vwap:.1f}")

if __name__ == '__main__':
    analyze_bots()
