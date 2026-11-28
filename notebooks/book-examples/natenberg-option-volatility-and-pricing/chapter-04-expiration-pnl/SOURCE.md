Publication: Sheldon Natenberg, Option Volatility and Pricing
Edition: Second edition
Chapter: 4 — expiration P&L of basic positions
Published parameters: The book supplies payoff definitions; the contracts and premiums are market examples, not published parameters, and nothing is tuned.

For settlement value S, strike K, call premium c, put premium p and contract multiplier m:

- Long call: m × (max(S − K, 0) − c); short call: its negative.
- Long put: m × (max(K − S, 0) − p); short put: its negative.

These are expiration diagnostics without fees or margin. `realized_pnl` means P&L at expiry-day settlement, computed from settlement prices; it is not a traded realization.

## Exchange rules

The exchange's [English equity index option rules](http://www.cffex.com.cn/u/cms/www/202009/242034095sbm.pdf), accessed 2026-11-28, state in Article 21:

> The exercise-settlement price on the last trading day shall be determined as follows:
>
> (1) for a call, the exercise-settlement price shall be the difference between its final settlement price and its strike price if the former is higher than the latter, and zero if otherwise;
>
> (2) for a put, the exercise-settlement price shall be the difference between its strike price and final settlement price if the former is higher than the latter, and zero if otherwise.

Article 22 states:

> The final settlement price of the Contract is the arithmetic average price of the underlying index during the last two trading hours on the last trading day, rounded to two decimal places.

Article 30 states:

> Exercise of the Contracts shall result in cash settlement based on the exercise-settlement price on the expiration date and the corresponding positions shall be closed out.

The exchange's [English CSI 300 index futures rules](http://www.cffex.com.cn/u/cms/www/201808/281719129xyq.pdf), accessed 2026-11-28, state in Article 15:

> The final settlement price of the Contract is the arithmetic average price of the underlying index during the last two trading hours on the last trading day, rounded to two decimal places.

The [revised option rules](http://www.cffex.com.cn/cn/ssxz/20221214/43100.html), accessed 2026-11-28, retain these provisions in Articles 21, 22 and 30. An official [2024 delivery notice](http://www.cffex.com.cn/en_new/Notices/20240315/37305.html) identifies the same final settlement value for matching IO and IF contracts.

The diagnostic therefore uses the same-month IF expiry-day settlement as S_T: both contracts use the same underlying index and final settlement formula. Separately, in the twelve sampled expiries, each option's observed expiry-day settlement equals its intrinsic value at the same-month IF settlement. For example, IO2403C3550 on 2024-03-15 settled at 4.21 = 3554.21 − 3550, and IO2409P3200 on 2024-09-20 settled at 14.87 = 3200 − 3185.13. Consequently, observed call settlement minus put settlement equals IF settlement minus K. The observed index close is not represented as official settlement.

**Boundary note:** For each expiry, the strike is chosen nearest the expiry-day IF settlement. This look-ahead is adequate for checking textbook curves, not a strategy leg-selection rule. Any historical strategy must lock its legs from the contract chain visible on the entry date, without look-ahead.
