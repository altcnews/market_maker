# Market maker on BitMEX

* Instrument: ETH
* Algorithm: Avellaneda & Stoikov (2008)
* Practical Modifications: 
  1. Remove terminal state (market active 24/7)
  2. Add dynamic inventory control
  3. Redesign API queries for better reaction time.
* Performance: live trading results: drawdown due to large absurd moves of the market
* Future Improvements:
  1. Introduce microstructural trend indicators: VPIN
  2. Stablize system. BitMEX API is unstable and unreliable/
