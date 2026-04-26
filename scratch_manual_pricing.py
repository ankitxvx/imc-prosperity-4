import numpy as np

def price_aether_options():
    # Simulation Parameters
    S0 = 10000 # Example base price, user will need to adjust based on UI
    vol = 2.51 # 251%
    drift = 0.0
    steps_per_day = 4
    days_per_year = 252
    
    n_sims = 100000
    
    # Time durations in years
    t_2w = 10.0 / days_per_year
    t_3w = 15.0 / days_per_year
    
    dt = 1.0 / (days_per_year * steps_per_day)
    
    # Simulating paths for 3 weeks (60 steps)
    n_steps = 15 * steps_per_day
    
    # Standard GBM Path generation
    # dS = S * drift * dt + S * vol * dW
    # S(t+dt) = S(t) * exp((drift - 0.5 * vol**2) * dt + vol * sqrt(dt) * Z)
    
    Z = np.random.standard_normal((n_sims, n_steps))
    path_multipliers = np.exp((drift - 0.5 * vol**2) * dt + vol * np.sqrt(dt) * Z)
    paths = np.ones((n_sims, n_steps + 1)) * S0
    for i in range(n_steps):
        paths[:, i+1] = paths[:, i] * path_multipliers[:, i]
    
    # 2-week and 3-week levels
    s_2w = paths[:, 10 * steps_per_day]
    s_3w = paths[:, 15 * steps_per_day]
    
    # We need to provide strikes. I will use a few around S0.
    # User should update these based on the actual UI options.
    strikes = [9000, 9500, 10000, 10500, 11000]
    
    print(f"--- Aether Crystal Pricing (S0={S0}, Vol=251%) ---")
    
    for K in strikes:
        print(f"\nStrike K = {K}:")
        
        # Vanilla
        c_2w = np.mean(np.maximum(s_2w - K, 0))
        p_2w = np.mean(np.maximum(K - s_2w, 0))
        c_3w = np.mean(np.maximum(s_3w - K, 0))
        p_3w = np.mean(np.maximum(K - s_3w, 0))
        
        print(f"  Vanilla 2w: Call={c_2w:.2f}, Put={p_2w:.2f}")
        print(f"  Vanilla 3w: Call={c_3w:.2f}, Put={p_3w:.2f}")
        
        # Binary Put (Assume payoff is 1000 units for pricing ratio)
        binary_p_3w = np.mean(s_3w < K) * 1000
        print(f"  Binary Put 3w (1000 payoff): {binary_p_3w:.2f}")
        
        # Knock-Out Put (Strike K, Barrier B)
        # Assuming barrier is below strike for a put. 
        # Example Barrier B = 0.9 * S0
        B = 0.9 * S0
        barrier_breached = np.any(paths[:, :15*steps_per_day+1] < B, axis=1)
        ko_put_payoff = np.maximum(K - s_3w, 0)
        ko_put_payoff[barrier_breached] = 0
        ko_put_price = np.mean(ko_put_payoff)
        print(f"  Knock-Out Put 3w (Barrier {B}): {ko_put_price:.2f}")

    # Chooser Option
    # Expires in 3w. At 2w, choose Call or Put (3w expiry).
    # Value at 2w = max(Call(S_2w, K, 1w), Put(S_2w, K, 1w))
    # We need to simulate the final week from each S_2w or use BS formula at t=2w.
    # Simplest: Since r=0, Call - Put = S - K. So max(C, P) = max(C, C - (S-K)) = C + max(0, K-S) if S<K else C.
    # Actually, at t=2w, it becomes a 1-week option.
    # Fair value = np.mean( Value_at_2w )
    
    # Let's approximate the 1-week value at t=2w using BS or a nested sim.
    # With r=0, max(Call, Put) = Call + max(K - S_2w, 0) = Put + max(S_2w - K, 0).
    
    def bs_call_simple(S, K, T, sigma):
        from scipy.stats import norm
        if T <= 0: return np.maximum(S - K, 0)
        d1 = (np.log(S / K) + (0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        return S * norm.cdf(d1) - K * norm.cdf(d2)

    # For Chooser, let's just use the sim paths to the end and pick the best at 2w
    # Wait, the chooser says: "At 2w, buyer chooses... it then behaves like a standard option for the final week".
    # This means at t=2w, we look at S_2w and K. 
    # If we choose Call, payoff at 3w is max(S_3w - K, 0).
    # If we choose Put, payoff at 3w is max(K - S_3w, 0).
    # Optimal choice at 2w is the one with higher expectation (fair value) at 3w.
    # Since r=0, Put(S_2w) - Call(S_2w) = K - S_2w.
    # So we choose Call if S_2w > K, and Put if S_2w < K.
    
    for K in strikes:
        choose_call = s_2w > K
        payoff = np.where(choose_call, np.maximum(s_3w - K, 0), np.maximum(K - s_3w, 0))
        chooser_price = np.mean(payoff)
        print(f"  Chooser Option 3w (K={K}): {chooser_price:.2f}")

if __name__ == '__main__':
    price_aether_options()
