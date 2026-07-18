# BITGET_API_CATALOG.md — catalogue EXHAUSTIF des endpoints REST Bitget (v2 + v3)

> **Source autoritative** : SDK officiel `github.com/tiagosiebler/bitget-api` (clients REST v2 & v3).
> Complète le référentiel curé [`BITGET_REFERENCE.md`](BITGET_REFERENCE.md) (frais, règles d'usage, WebSocket,
> limites de débit, écosystème). **Discipline constitutionnelle** — un endpoint listé n'est PAS branché :
>
> 1. toute capacité est d'abord **vérifiée contre l'API réelle** (clé **Trade-only**, lecture) puis **mesurée
>    IC nette de frais** avant tout armement (mesure-d'abord) ;
> 2. l'**exécution** (⚙️) passe EXCLUSIVEMENT par les modules bornés `spot_executor` / `futures_executor` /
>    surfaces §67 (`bitget_execute`) — jamais d'appel POST direct ; les murs 50/250, ×5, stop −5 % tiennent ;
> 3. les **RETRAITS** (⛔) sont **hors de portée** : clé Trade-only, **aucun code de retrait n'existe** — ils
>    sont catalogués pour mémoire, jamais à implémenter.
>
> Colonnes : **Bot** ✅ = déjà câblé · **Auth** 🔑 privé / — public · **⚑** ⚙️ exécution / ⛔ retrait.
>
> ⚠️ **SDK ≠ API live.** Ce catalogue reflète la *surface du SDK* ; quelques chemins peuvent être **absents
> en réel** (constaté 18/07 : `mix/market/long-short-ratio` → **404**). Endpoints publics **vérifiés live**
> le 18/07 : `v3/market/liquidations`, `mix/market/position-long-short`, `mix/market/funding-time`,
> `v3/market/spot-net-flow` (tous `code=00000`). Vérifier **contre l'API réelle** avant tout usage.
> Généré le **18/07/2026**.

## Vue d'ensemble

- **413 endpoints** = **236 v2** + **177 v3** · **29 câblés** par le bot.
- **v2** = API du bot (compte classique). **v3** = API unifiée (compte UTA/`set-leverage`/`move-positions`/
  liquidations publiques/collateral) — le bot **reste v2/compte classique** (décision : cloisonnement du risque).
- Familles v2 : spot 54 · mix/futures 73 · earn 36 · broker 22 · copy 19 · convert 7 · margin 6 · tax 4 · p2p 4 · user 4 · account 3 · common 2 · public 2.

---

# API V2 — 236 endpoints · 27 câblés

## v2 · account — Compte — assets agrégés, funding, bot  ·  3 endpoints (1 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
| ✅ | GET | 🔑 |  | `/api/v2/account/all-account-balance` | `getBalances` |  |
|  | GET | 🔑 |  | `/api/v2/account/bot-assets` | `getBotAccount` | accountType |
|  | GET | 🔑 |  | `/api/v2/account/funding-assets` | `getFundingAssets` | coin |

## v2 · broker — Broker — sous-comptes, commissions, rebates  ·  22 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 |  | `/api/v2/broker/account/create-subaccount` | `createSubaccount` | subaccountName, label |
|  | GET | 🔑 |  | `/api/v2/broker/account/info` | `getBrokerInfo` |  |
|  | POST | 🔑 |  | `/api/v2/broker/account/modify-subaccount` | `modifySubaccount` | ModifySubRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/account/subaccount-email` | `getSubaccountEmail` | subUid |
|  | GET | 🔑 |  | `/api/v2/broker/account/subaccount-list` | `getSubaccounts` | GetSubAccountsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/agent-commission` | `getAgentCommissionDetail` | GetAgentCommissionDetailRequestV2 |
|  | GET | 🔑 | ⛔RETRAIT | `/api/v2/broker/all-sub-deposit-withdrawal` | `getAllSubDepositWithdrawalRecords` | GetAllSubDepositWithdrawalRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/commissions` | `getBrokerCommissions` | GetBrokerCommissionsRequestV2 |
|  | POST | 🔑 |  | `/api/v2/broker/customer-asset` | `getAgentCustomerAssets` | AgentCustomerAssetRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/customer-commissions` | `getAgentCustomerCommissions` | GetAgentCustomerCommissionsRequestV2 |
|  | POST | 🔑 |  | `/api/v2/broker/customer-deposit` | `getAgentCustomerDeposits` | AgentCustomerDepositRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/customer-kyc-result` | `getAgentCustomerKycResult` | GetAgentCustomerKycResultRequestV2 |
|  | POST | 🔑 |  | `/api/v2/broker/customer-list` | `getAgentCustomerList` | AgentCustomerListRequestV2 |
|  | POST | 🔑 |  | `/api/v2/broker/customer-trade-volume` | `getAgentCustomerTradeVolume` | AgentCustomerTradeVolumeRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/order-commission` | `getBrokerOrderCommission` | GetBrokerOrderCommissionRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/rebate-info` | `getBrokerRebateInfo` | GetBrokerRebateInfoRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/sub-customer-list` | `getAgentSubCustomerList` | GetAgentSubCustomerListRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/subaccount-deposit` | `subaccountDepositRecords` | SubDepositRecordsRequestV2 |
|  | GET | 🔑 | ⛔RETRAIT | `/api/v2/broker/subaccount-withdrawal` | `subaccountWithdrawalRecords` | SubWithdrawalRecordsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/subaccounts` | `getBrokerSubaccounts` | GetBrokerSubaccountsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/total-commission` | `getBrokerTotalCommission` | GetBrokerTotalCommissionRequestV2 |
|  | GET | 🔑 |  | `/api/v2/broker/trade-volume` | `getBrokerTradeVolume` | GetBrokerTradeVolumeRequestV2 |

## v2 · common — Common — taux de frais  ·  2 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v2/common/all-trade-rate` | `getAllTradeRates` | GetAllTradeRatesRequestV2 |
|  | GET | 🔑 |  | `/api/v2/common/trade-rate` | `getTradeRate` | GetTradeRateRequestV2 |

## v2 · convert — Convert — conversion instantanée + BGB  ·  7 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 |  | `/api/v2/convert/bgb-convert` | `convertBGB` | coinList |
|  | GET | 🔑 |  | `/api/v2/convert/bgb-convert-coin-list` | `getConvertBGBCoins` |  |
|  | GET | 🔑 |  | `/api/v2/convert/bgb-convert-records` | `getConvertBGBHistory` | GetConvertBGBHistoryRequestV2 |
|  | GET | 🔑 |  | `/api/v2/convert/convert-record` | `getConvertHistory` | GetConvertHistoryRequestV2 |
|  | GET | 🔑 |  | `/api/v2/convert/currencies` | `getConvertCoins` |  |
|  | GET | 🔑 |  | `/api/v2/convert/quoted-price` | `getConvertQuotedPrice` | ConvertQuoteRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/convert/trade` | `convert` | ConvertRequestV2 |

## v2 · copy — Copy-trading — traders/followers spot & futures  ·  19 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v2/copy/mix-broker/query-traders` | `getBrokerTraders` |  |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/copy/mix-follower/cancel-trader` | `unfollowFuturesTrader` | traderId |
|  | GET | 🔑 |  | `/api/v2/copy/mix-follower/query-settings` | `getFuturesFollowerSettings` | traderId |
|  | GET | 🔑 |  | `/api/v2/copy/mix-follower/query-traders` | `getFuturesFollowerTraders` | GetFuturesFollowerTradersRequestV2 |
|  | POST | 🔑 |  | `/api/v2/copy/mix-follower/setting-tpsl` | `updateFuturesFollowerTPSL` | UpdateFuturesFollowerTPSLRequestV2 |
|  | POST | 🔑 |  | `/api/v2/copy/mix-follower/settings` | `updateFuturesFollowerSettings` | UpdateFuturesFollowerSettingsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/copy/mix-trader/order-total-detail` | `getFuturesTraderOrder` |  |
|  | GET | 🔑 |  | `/api/v2/copy/mix-trader/profit-details` | `getFuturesTraderProfitShare` | coin, pageSize, pageNo |
|  | GET | 🔑 |  | `/api/v2/copy/mix-trader/profit-history-summarys` | `getFuturesTraderProfitHistory` |  |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/copy/spot-follower/cancel-trader` | `unfollowSpotTrader` | traderId |
|  | GET | 🔑 |  | `/api/v2/copy/spot-follower/query-settings` | `getSpotFollowerSettings` | traderId |
|  | GET | 🔑 |  | `/api/v2/copy/spot-follower/query-traders` | `getSpotFollowerTraders` | pageNo, pageSize, startTime, endTime |
|  | POST | 🔑 |  | `/api/v2/copy/spot-follower/setting-tpsl` | `updateSpotFollowerTPSL` | trackingNo, stopSurplusPrice, stopLossPrice |
|  | POST | 🔑 |  | `/api/v2/copy/spot-follower/settings` | `updateSpotFollowerSettings` | traderId, autoCopy, mode, settings |
|  | POST | 🔑 |  | `/api/v2/copy/spot-follower/stop-order` | `cancelSpotFollowerOrder` | trackingNoList |
|  | GET | 🔑 |  | `/api/v2/copy/spot-trader/config-query-settings` | `getSpotTraderConfiguration` |  |
|  | GET | 🔑 |  | `/api/v2/copy/spot-trader/order-total-detail` | `getSpotTraderOrder` |  |
|  | GET | 🔑 |  | `/api/v2/copy/spot-trader/profit-details` | `getSpotTraderUnrealizedProfit` | coin, pageNo, pageSize |
|  | GET | 🔑 |  | `/api/v2/copy/spot-trader/profit-summarys` | `getSpotTraderProfit` |  |

## v2 · earn — Earn — savings · elite · sharkfin · loan  ·  36 endpoints (1 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v2/earn/account/assets` | `getEarnAccount` | coin |
|  | GET | 🔑 |  | `/api/v2/earn/elite/assets` | `getEarnEliteAssets` |  |
|  | GET | 🔑 |  | `/api/v2/earn/elite/product` | `getEarnEliteProducts` |  |
|  | GET | 🔑 |  | `/api/v2/earn/elite/records` | `getEarnEliteRecords` | GetEarnEliteRecordsRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/earn/elite/redeem` | `redeemEarnElite` | RedeemEarnEliteRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/elite/redeem-info` | `getEarnEliteRedeemInfo` | GetEarnEliteRedeemInfoRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/earn/elite/subscribe` | `subscribeEarnElite` | EarnEliteSubscribeRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/elite/subscribe-info` | `getEarnEliteSubscribeInfo` | GetEarnEliteSubscribeInfoRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/elite/subscribe-result` | `getEarnEliteSubscribeResult` | GetEarnEliteSubscribeResultRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/earn/loan/borrow` | `borrowLoan` | BorrowLoanRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/loan/borrow-history` | `getLoanHistory` | GetLoanHistoryRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/loan/debts` | `getLoanDebts` |  |
|  | GET | 🔑 |  | `/api/v2/earn/loan/ongoing-orders` | `getOngoingLoanOrders` | orderId, loanCoin, pledgeCoin |
|  | GET | — |  | `/api/v2/earn/loan/public/coinInfos` | `getLoanCurrencies` | coin |
|  | GET | — |  | `/api/v2/earn/loan/public/hour-interest` | `getLoanEstInterestAndBorrowable` | GetLoanEstInterestAndBorrowableRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/loan/reduces` | `getLoanLiquidationRecords` | GetLiquidationRecordsRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/earn/loan/repay` | `repayLoan` | RepayLoanRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/loan/repay-history` | `getRepayHistory` | GetLoanRepayHistoryRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/loan/revise-history` | `getLoanPledgeRateHistory` | GetLoanPledgeRateHistoryRequestV2 |
|  | POST | 🔑 |  | `/api/v2/earn/loan/revise-pledge` | `updateLoanPledgeRate` | ModifyLoanPledgeRateRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/savings/account` | `getEarnSavingsAccount` |  |
| ✅ | GET | 🔑 |  | `/api/v2/earn/savings/assets` | `getEarnSavingsAssets` | GetEarnSavingsAssetsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/savings/product` | `getEarnSavingsProducts` | coin, filter |
|  | GET | 🔑 |  | `/api/v2/earn/savings/records` | `getEarnSavingsRecords` | GetEarnSavingsRecordsRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/earn/savings/redeem` | `earnRedeemSavings` | RedeemSavingsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/savings/redeem-result` | `getEarnSavingsRedemptionResult` | orderId, periodType |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/earn/savings/subscribe` | `earnSubscribeSavings` | productId, periodType, amount |
|  | GET | 🔑 |  | `/api/v2/earn/savings/subscribe-info` | `getEarnSavingsSubscription` | productId, periodType |
|  | GET | 🔑 |  | `/api/v2/earn/savings/subscribe-result` | `getEarnSavingsSubscriptionResult` | productId, periodType |
|  | GET | 🔑 |  | `/api/v2/earn/sharkfin/account` | `getSharkfinAccount` |  |
|  | GET | 🔑 |  | `/api/v2/earn/sharkfin/assets` | `getSharkfinAssets` | GetSharkfinAssetsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/earn/sharkfin/product` | `getSharkfinProducts` | coin, limit, idLessThan |
|  | GET | 🔑 |  | `/api/v2/earn/sharkfin/records` | `getSharkfinRecords` | GetSharkfinRecordsRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/earn/sharkfin/subscribe` | `subscribeSharkfin` | productId, amount |
|  | GET | 🔑 |  | `/api/v2/earn/sharkfin/subscribe-info` | `getSharkfinSubscription` | productId |
|  | GET | 🔑 |  | `/api/v2/earn/sharkfin/subscribe-result` | `getSharkfinSubscriptionResult` | orderId |

## v2 · margin — Marge isolée/croisée — emprunt/remboursement/ordres  ·  6 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v2/margin/${marginType}/account/risk-rate` | `getMarginRiskRate` | marginType |
|  | GET | 🔑 |  | `/api/v2/margin/${marginType}/fills` | `getMarginHistoricOrderFills` | marginType |
|  | GET | 🔑 |  | `/api/v2/margin/${marginType}/open-orders` | `getMarginOpenOrders` | marginType |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/margin/${marginType}/place-order` | `marginSubmitOrder` | marginType |
|  | GET | 🔑 |  | `/api/v2/margin/${marginType}/tier-data` | `getMarginTierConfiguration` | marginType, coin |
|  | GET | — |  | `/api/v2/margin/currencies` | `getMarginCurrencies` |  |

## v2 · mix — Futures USDT-M/COIN-M (« mix ») — marché · compte · position · order  ·  73 endpoints (17 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v2/mix/account/account` | `getFuturesAccountAsset` | FuturesSingleAccountRequestV2 |
| ✅ | GET | 🔑 |  | `/api/v2/mix/account/accounts` | `getFuturesAccountAssets` | productType |
|  | GET | 🔑 |  | `/api/v2/mix/account/bill` | `getFuturesAccountBills` | FuturesAccountBillRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/account/interest-history` | `getFuturesInterestHistory` | FuturesInterestHistoryRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/account/isolated-symbols` | `getFuturesIsolatedSymbols` | FuturesIsolatedSymbolsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/account/liq-price` | `getFuturesLiquidationPrice` | FuturesLiquidationPriceRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/account/max-open` | `getFuturesMaxOpenableQuantity` | FuturesMaxOpenRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/account/open-count` | `getFuturesOpenCount` | FuturesOpenCountRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/account/set-asset-mode` | `setFuturesAssetMode` | productType, assetMode |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/account/set-auto-margin` | `setFuturesPositionAutoMargin` | FuturesSetAutoMarginRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/account/set-leverage` | `setFuturesLeverage` | FuturesSetLeverageRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/account/set-margin` | `setFuturesPositionMargin` | FuturesSetPositionMarginRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/account/set-margin-mode` | `setFuturesMarginMode` | FuturesSetMarginModeRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/account/set-position-mode` | `setFuturesPositionMode` | productType, posMode |
|  | GET | 🔑 |  | `/api/v2/mix/account/sub-account-assets` | `getFuturesSubAccountAssets` | productType |
|  | GET | 🔑 |  | `/api/v2/mix/account/switch-union-usdt` | `getSwitchUnionUsdt` |  |
|  | GET | 🔑 |  | `/api/v2/mix/account/transfer-limits` | `getUnionTransferLimits` | GetUnionTransferLimitsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/account/union-config` | `getUnionConfig` |  |
|  | POST | 🔑 |  | `/api/v2/mix/account/union-convert` | `unionConvert` | UnionConvertRequestV2 |
| ✅ | GET | — |  | `/api/v2/mix/market/account-long-short` | `getFuturesActiveLongShortAccountData` | symbol, period |
| ✅ | GET | — |  | `/api/v2/mix/market/candles` | `getFuturesCandles` | FuturesCandlesRequestV2 |
| ✅ | GET | — |  | `/api/v2/mix/market/contracts` | `getFuturesContractConfig` | symbol, productType |
| ✅ | GET | — |  | `/api/v2/mix/market/current-fund-rate` | `getFuturesCurrentFundingRate` | symbol, productType |
|  | GET | — |  | `/api/v2/mix/market/discount-rate` | `getFuturesDiscountRate` |  |
|  | GET | — |  | `/api/v2/mix/market/exchange-rate` | `getFuturesInterestExchangeRate` |  |
| ✅ | GET | — |  | `/api/v2/mix/market/fills` | `getFuturesRecentTrades` | FuturesRecentTradesRequestV2 |
|  | GET | — |  | `/api/v2/mix/market/fills-history` | `getFuturesHistoricTrades` | FuturesHistoricTradesRequestV2 |
| ✅ | GET | — |  | `/api/v2/mix/market/funding-time` | `getFuturesNextFundingTime` | symbol, productType |
| ✅ | GET | — |  | `/api/v2/mix/market/history-candles` | `getFuturesHistoricCandles` | FuturesCandlesRequestV2 |
| ✅ | GET | — |  | `/api/v2/mix/market/history-fund-rate` | `getFuturesHistoricFundingRates` | symbol, productType, pageSize, pageNo |
|  | GET | — |  | `/api/v2/mix/market/history-index-candles` | `getFuturesHistoricIndexPriceCandles` | FuturesCandlesRequestV2 |
|  | GET | — |  | `/api/v2/mix/market/history-mark-candles` | `getFuturesHistoricMarkPriceCandles` | FuturesCandlesRequestV2 |
|  | GET | — |  | `/api/v2/mix/market/isolated-borrow-rate` | `getIsolatedMarginBorrowingRatio` | symbol, period |
|  | GET | — |  | `/api/v2/mix/market/loan-growth` | `getMarginLoanGrowthRate` | symbol, period, coin |
| ✅ | GET | — |  | `/api/v2/mix/market/long-short` | `getFuturesActiveBuySellVolumeData` | symbol, period |
|  | GET | — |  | `/api/v2/mix/market/long-short-ratio` | `getFuturesLongShortRatio` | symbol, period, coin |
| ✅ | GET | — |  | `/api/v2/mix/market/merge-depth` | `getFuturesMergeDepth` | FuturesMergeDepthRequestV2 |
|  | GET | — |  | `/api/v2/mix/market/oi-limit` | `getFuturesOiLimit` | FuturesOiLimitRequestV2 |
| ✅ | GET | — |  | `/api/v2/mix/market/open-interest` | `getFuturesOpenInterest` | symbol, productType |
| ✅ | GET | — |  | `/api/v2/mix/market/position-long-short` | `getFuturesActiveLongShortPositionData` | symbol, period |
|  | GET | — |  | `/api/v2/mix/market/query-position-lever` | `getFuturesPositionTier` | productType, symbol |
|  | GET | — |  | `/api/v2/mix/market/symbol-price` | `getFuturesSymbolPrice` | symbol, productType |
| ✅ | GET | — |  | `/api/v2/mix/market/taker-buy-sell` | `getFuturesActiveTakerBuySellVolumeData` | symbol, period |
| ✅ | GET | — |  | `/api/v2/mix/market/ticker` | `getFuturesTicker` | symbol, productType |
| ✅ | GET | — |  | `/api/v2/mix/market/tickers` | `getFuturesAllTickers` | productType |
|  | GET | — |  | `/api/v2/mix/market/union-interest-rate-history` | `getFuturesInterestRateHistory` | coin |
|  | GET | — |  | `/api/v2/mix/market/vip-fee-rate` | `getFuturesVIPFeeRate` |  |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/batch-cancel-orders` | `futuresBatchCancelOrders` | FuturesBatchCancelOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/batch-place-order` | `futuresBatchSubmitOrders` | FuturesBatchOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/cancel-all-orders` | `futuresCancelAllOrders` | FuturesCancelAllOrdersRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/cancel-order` | `futuresCancelOrder` | FuturesCancelOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/cancel-plan-order` | `futuresCancelPlanOrder` | FuturesCancelPlanOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/click-backhand` | `futuresSubmitReversal` | FuturesReversalOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/close-positions` | `futuresFlashClosePositions` | FuturesFlashClosePositionsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/detail` | `getFuturesOrder` | FuturesGetOrderRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/fill-history` | `getFuturesHistoricOrderFills` | FuturesGetHistoricalFillsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/fills` | `getFuturesFills` | FuturesGetOrderFillsRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/modify-order` | `futuresModifyOrder` | FuturesModifyOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/modify-plan-order` | `futuresModifyPlanOrder` | FuturesModifyPlanOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/modify-tpsl-order` | `futuresModifyTPSLPOrder` | FuturesModifyTPSLOrderRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/orders-history` | `getFuturesHistoricOrders` | FuturesGetHistoryOrdersRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/orders-pending` | `getFuturesOpenOrders` | FuturesGetOpenOrdersRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/orders-plan-history` | `getFuturesHistoricPlanOrders` | FuturesGetHistoryPlanOrdersRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/orders-plan-pending` | `getFuturesPlanOrders` | FuturesGetPlanOrdersRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/place-order` | `futuresSubmitOrder` | FuturesPlaceOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/place-plan-order` | `futuresSubmitPlanOrder` | FuturesPlanOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/place-pos-tpsl` | `futuresSubmitPositionTPSL` | FuturesPositionTPSLOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/mix/order/place-tpsl-order` | `futuresSubmitTPSLOrder` | FuturesTPSLOrderRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/order/plan-sub-order` | `getFuturesTriggerSubOrder` | planType, planOrderId, productType |
|  | GET | 🔑 |  | `/api/v2/mix/position/adlRank` | `getFuturesPositionAdlRank` | FuturesPositionAdlRankRequestV2 |
| ✅ | GET | 🔑 |  | `/api/v2/mix/position/all-position` | `getFuturesPositions` | productType, marginCoin |
|  | GET | 🔑 |  | `/api/v2/mix/position/history-position` | `getFuturesHistoricPositions` | FuturesHistoricalPositionsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/mix/position/single-position` | `getFuturesPosition` | productType, symbol, marginCoin |

## v2 · p2p — P2P — annonces, ordres, marchands  ·  4 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v2/p2p/advList` | `getP2PMerchantAdvertisementList` | GetMerchantAdvertisementsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/p2p/merchantInfo` | `getP2PMerchantInfo` |  |
|  | GET | 🔑 |  | `/api/v2/p2p/merchantList` | `getP2PMerchantList` | GetP2PMerchantsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/p2p/orderList` | `getP2PMerchantOrders` | GetMerchantP2POrdersRequestV2 |

## v2 · public — Public — annonces, heure serveur  ·  2 endpoints (1 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
| ✅ | GET | — |  | `/api/v2/public/annoucements` | `getAnnouncements` | GetAnnouncementsRequestV2 |
|  | GET | — |  | `/api/v2/public/time` | `getServerTime` |  |

## v2 · spot — Spot — marché · public · trade · compte · wallet · ins-loan  ·  54 endpoints (7 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
| ✅ | GET | 🔑 |  | `/api/v2/spot/account/assets` | `getSpotAccountAssets` | coin, assetType |
|  | GET | 🔑 |  | `/api/v2/spot/account/bills` | `getSpotAccountBills` | GetSpotAccountBillsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/account/deduct-info` | `getSpotBGBDeductInfo` |  |
|  | GET | 🔑 |  | `/api/v2/spot/account/info` | `getSpotAccount` |  |
|  | GET | 🔑 |  | `/api/v2/spot/account/subaccount-assets` | `getSpotSubAccountAssets` |  |
|  | POST | 🔑 |  | `/api/v2/spot/account/switch-deduct` | `spotSwitchBGBDeduct` | deduct |
|  | GET | 🔑 |  | `/api/v2/spot/account/transferRecords` | `getSpotTransferHistory` | GetSpotTransferRecordRequestV2 |
|  | POST | 🔑 |  | `/api/v2/spot/account/upgrade` | `upgradeToUnifiedAccount` | subUid |
|  | GET | 🔑 |  | `/api/v2/spot/account/upgrade-status` | `getUnifiedAccountSwitchStatus` | subUid |
|  | GET | 🔑 |  | `/api/v2/spot/ins-loan/loan-order` | `getLoanOrder` | GetInstLoanOrderRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/ins-loan/ltv-convert` | `getLoanLTVConvert` | GetInstLoanLTVConvertRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/ins-loan/product-infos` | `getLoanProductInfo` | GetInstLoanProductInfoRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/ins-loan/repaid-history` | `getLoanRepaidHistory` | GetInstLoanRepaidHistoryRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/ins-loan/risk-unit` | `getLoanRiskUnit` |  |
|  | GET | 🔑 |  | `/api/v2/spot/ins-loan/symbols` | `getLoanSymbols` | GetInstLoanSymbolsRequestV2 |
|  | GET | — |  | `/api/v2/spot/market/auction` | `getSpotCallAuction` | SpotCallAuctionRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/market/candles` | `getSpotCandles` | SpotCandlesRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/market/fills` | `getSpotRecentTrades` | symbol, limit |
|  | GET | 🔑 |  | `/api/v2/spot/market/fills-history` | `getSpotHistoricTrades` | SpotHistoricTradesRequestV2 |
| ✅ | GET | — |  | `/api/v2/spot/market/fund-flow` | `getSpotFundFlow` | symbol, period |
|  | GET | — |  | `/api/v2/spot/market/fund-net-flow` | `getSpotFundNetFlowData` | symbol |
|  | GET | 🔑 |  | `/api/v2/spot/market/history-candles` | `getSpotHistoricCandles` | SpotHistoricCandlesRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/market/merge-depth` | `getSpotMergeDepth` | symbol, precision, limit |
| ✅ | GET | 🔑 |  | `/api/v2/spot/market/orderbook` | `getSpotOrderBookDepth` | symbol, type, limit |
|  | GET | — |  | `/api/v2/spot/market/support-symbols` | `getTradeDataSupportSymbols` |  |
| ✅ | GET | 🔑 |  | `/api/v2/spot/market/tickers` | `getSpotTicker` | symbol |
|  | GET | 🔑 |  | `/api/v2/spot/market/vip-fee-rate` | `getSpotVIPFeeRate` |  |
| ✅ | GET | 🔑 |  | `/api/v2/spot/market/whale-net-flow` | `getSpotWhaleNetFlowData` | symbol |
|  | GET | 🔑 |  | `/api/v2/spot/public/coins` | `getSpotCoinInfo` | coin |
| ✅ | GET | 🔑 |  | `/api/v2/spot/public/symbols` | `getSpotSymbolInfo` | symbol |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/batch-cancel-order` | `spotBatchCancelOrders` | SpotBatchCancelOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/batch-orders` | `spotBatchSubmitOrders` | SpotBatchOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/cancel-order` | `spotCancelOrder` | SpotCancelOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/cancel-plan-order` | `spotCancelPlanOrder` | clientOid, orderId |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/cancel-replace-order` | `spotCancelandSubmitOrder` | SpotCancelandSubmitOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/cancel-symbol-order` | `spotCancelSymbolOrder` | symbol |
|  | GET | 🔑 |  | `/api/v2/spot/trade/current-plan-order` | `getSpotCurrentPlanOrders` | GetSpotCurrentPlanOrdersRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/trade/fills` | `getSpotFills` | GetSpotFillsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/trade/history-orders` | `getSpotHistoricOrders` | GetSpotHistoryOrdersRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/trade/history-plan-order` | `getSpotHistoricPlanOrders` | GetSpotHistoryPlanOrdersRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/modify-plan-order` | `spotModifyPlanOrder` | SpotModifyPlanOrderRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/trade/orderInfo` | `getSpotOrder` | GetSpotOrderInfoRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/place-order` | `spotSubmitOrder` | SpotOrderRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/trade/place-plan-order` | `spotSubmitPlanOrder` | SpotPlanOrderRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/trade/plan-sub-order` | `getSpotPlanSubOrder` | planOrderId |
| ✅ | GET | 🔑 |  | `/api/v2/spot/trade/unfilled-orders` | `getSpotOpenOrders` | GetSpotOpenOrdersRequestV2 |
|  | POST | 🔑 | ⛔RETRAIT | `/api/v2/spot/wallet/cancel-withdrawal` | `spotCancelWithdrawal` | orderId |
|  | GET | 🔑 |  | `/api/v2/spot/wallet/deposit-address` | `getSpotDepositAddress` | coin, chain, size |
|  | GET | 🔑 |  | `/api/v2/spot/wallet/deposit-records` | `getSpotDepositHistory` | GetSpotDepositRecordRequestV2 |
|  | POST | 🔑 |  | `/api/v2/spot/wallet/subaccount-transfer` | `spotSubTransfer` | SpotSubAccountTransferRequestV2 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v2/spot/wallet/transfer` | `spotTransfer` | SpotTransferRequestV2 |
|  | GET | 🔑 |  | `/api/v2/spot/wallet/transfer-coin-info` | `getSpotTransferableCoins` | fromType, toType |
|  | POST | 🔑 | ⛔RETRAIT | `/api/v2/spot/wallet/withdrawal` | `spotWithdraw` | SpotWithdrawalRequestV2 |
|  | GET | 🔑 | ⛔RETRAIT | `/api/v2/spot/wallet/withdrawal-records` | `getSpotWithdrawalHistory` | GetSpotWithdrawalRecordRequestV2 |

## v2 · tax — Tax — relevés fiscaux  ·  4 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v2/tax/future-record` | `getFuturesTransactionRecords` | GetFuturesTransactionsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/tax/margin-record` | `getMarginTransactionRecords` | GetMarginTransactionsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/tax/p2p-record` | `getP2PTransactionRecords` | GetP2PTransactionsRequestV2 |
|  | GET | 🔑 |  | `/api/v2/tax/spot-record` | `getSpotTransactionRecords` | GetSpotTransactionsRequestV2 |

## v2 · user — User — sous-comptes virtuels/agent  ·  4 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 |  | `/api/v2/user/create-agent-subaccount` | `createAgentSubaccount` | CreateAgentSubaccountRequestV2 |
|  | POST | 🔑 |  | `/api/v2/user/create-virtual-subaccount` | `createVirtualSubaccount` | subAccountList |
|  | POST | 🔑 |  | `/api/v2/user/modify-virtual-subaccount` | `modifyVirtualSubaccount` | ModifyVirtualSubRequestV2 |
|  | GET | 🔑 |  | `/api/v2/user/virtual-subaccount-list` | `getVirtualSubaccounts` | limit, idLessThan, status |

---

# API V3 — 177 endpoints · 2 câblés

## v3 · account — Compte — assets agrégés, funding, bot  ·  47 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/adjust-account-mode` | `adjustAccountMode` | AdjustAccountModeRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/all-fee-rate` | `getAllFeeRates` | GetAllFeeRatesRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/assets` | `getBalances` |  |
|  | POST | 🔑 | ⛔RETRAIT | `/api/v3/account/cancel-withdrawal` | `cancelWithdrawal` | CancelWithdrawalRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/collateral-type` | `getCollateralType` |  |
|  | GET | 🔑 |  | `/api/v3/account/convert-records` | `getConvertRecords` | GetConvertRecordsRequestV3 |
|  | GET | — |  | `/api/v3/account/custom-collateral-coins` | `getCustomCollateralCoins` |  |
|  | GET | 🔑 |  | `/api/v3/account/deduct-info` | `getDeductInfo` |  |
|  | GET | 🔑 |  | `/api/v3/account/delta-info` | `getDeltaInfo` |  |
|  | POST | 🔑 |  | `/api/v3/account/deposit-account` | `setDepositAccount` | SetDepositAccountRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/deposit-address` | `getDepositAddress` | GetDepositAddressRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/deposit-records` | `getDepositRecords` | GetDepositRecordsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/fee-rate` | `getFeeRate` | GetFeeRateRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/financial-records` | `getFinancialRecords` | GetFinancialRecordsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/funding-assets` | `getFundingAssets` | GetFundingAssetsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/info` | `getAccountInfo` |  |
|  | POST | 🔑 |  | `/api/v3/account/max-open-available` | `getMaxOpenAvailable` | GetMaxOpenAvailableRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/max-transferable` | `getMaxTransferable` | GetMaxTransferableRequestV3 |
|  | GET | 🔑 | ⛔RETRAIT | `/api/v3/account/max-withdrawal` | `getMaxWithdrawal` | GetMaxWithdrawalRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/move-position-history` | `getMovePositionHistory` | GetMovePositionHistoryRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/move-positions` | `movePositions` | MovePositionsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/open-interest-limit` | `getOpenInterestLimit` | GetOpenInterestLimitRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/payment-coins` | `getPaymentCoins` |  |
|  | GET | 🔑 |  | `/api/v3/account/pre-set-leverage` | `preSetLeverage` | PreSetLeverageRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/reality-fills` | `getRealityFills` | GetRealityFillsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/reality-orderbook` | `getRealityOrderBook` | GetRealityOrderBookRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/repay` | `submitRepay` | RepayRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/repayable-coins` | `getRepayableCoins` |  |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/set-collateral-type` | `setCollateralType` | SetCollateralTypeRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/set-hold-mode` | `setHoldMode` | holdMode |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/set-leverage` | `setLeverage` | SetLeverageRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/set-margin` | `setMargin` | SetMarginRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/settings` | `getAccountSettings` |  |
|  | GET | 🔑 |  | `/api/v3/account/sub-deposit-address` | `getSubDepositAddress` | GetSubDepositAddressRequestV3 |
|  | POST | 🔑 |  | `/api/v3/account/sub-deposit-records` | `getSubDepositRecords` | GetSubDepositRecordsRequestV3 |
|  | POST | 🔑 |  | `/api/v3/account/sub-master-transfer` | `subMasterTransfer` | SubMasterTransferRequestV3 |
|  | POST | 🔑 |  | `/api/v3/account/sub-transfer` | `subAccountTransfer` | SubAccountTransferRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/sub-transfer-record` | `getSubTransferRecords` | GetSubTransferRecordsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/sub-unified-assets` | `getSubUnifiedAssets` | GetSubUnifiedAssetsRequestV3 |
|  | POST | 🔑 |  | `/api/v3/account/switch` | `downgradeAccountToClassic` |  |
|  | POST | 🔑 |  | `/api/v3/account/switch-deduct` | `switchDeduct` | SwitchDeductRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/switch-status` | `getUnifiedAccountSwitchStatus` |  |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/account/transfer` | `submitTransfer` | TransferRequestV3 |
|  | GET | 🔑 |  | `/api/v3/account/transferable-coins` | `getTransferableCoins` | GetTransferableCoinsRequestV3 |
|  | POST | 🔑 | ⛔RETRAIT | `/api/v3/account/withdraw` | `submitWithdraw` | WithdrawRequestV3 |
|  | GET | 🔑 | ⛔RETRAIT | `/api/v3/account/withdraw-address` | `getWithdrawAddressBook` | GetWithdrawAddressBookRequestV3 |
|  | GET | 🔑 | ⛔RETRAIT | `/api/v3/account/withdrawal-records` | `getWithdrawRecords` | GetWithdrawRecordsRequestV3 |

## v3 · broker — Broker — sous-comptes, commissions, rebates  ·  11 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 | ⛔RETRAIT | `/api/v3/broker/all-sub-deposit-withdrawal` | `getBrokerAllSubDepositWithdrawal` | GetBrokerAllSubDepositWithdrawalRequestV3 |
|  | GET | 🔑 |  | `/api/v3/broker/commission` | `getBrokerCommission` | GetBrokerCommissionRequestV3 |
|  | POST | 🔑 |  | `/api/v3/broker/create-sub` | `createBrokerSubAccount` | CreateBrokerSubAccountRequestV3 |
|  | POST | 🔑 |  | `/api/v3/broker/create-sub-apikey` | `createBrokerSubApiKey` | CreateBrokerSubApiKeyRequestV3 |
|  | POST | 🔑 |  | `/api/v3/broker/delete-sub-apikey` | `deleteBrokerSubApiKey` | DeleteBrokerSubApiKeyRequestV3 |
|  | POST | 🔑 |  | `/api/v3/broker/modify-sub` | `modifyBrokerSubAccount` | ModifyBrokerSubAccountRequestV3 |
|  | POST | 🔑 |  | `/api/v3/broker/modify-sub-apikey` | `modifyBrokerSubApiKey` | ModifyBrokerSubApiKeyRequestV3 |
|  | GET | 🔑 |  | `/api/v3/broker/query-sub-apikey` | `getBrokerSubApiKey` | GetBrokerSubApiKeyRequestV3 |
|  | POST | 🔑 |  | `/api/v3/broker/sub-deposit-address` | `getBrokerSubDepositAddress` | GetBrokerSubDepositAddressRequestV3 |
|  | GET | 🔑 |  | `/api/v3/broker/sub-list` | `getBrokerSubAccountList` | GetBrokerSubAccountListRequestV3 |
|  | POST | 🔑 | ⛔RETRAIT | `/api/v3/broker/sub-withdrawal` | `brokerSubWithdrawal` | BrokerSubWithdrawalRequestV3 |

## v3 · copy — Copy-trading — traders/followers spot & futures  ·  5 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v3/copy/futures/max-transferable` | `getCopyFuturesMaxTransferable` | GetCopyFuturesMaxTransferableRequestV3 |
|  | GET | 🔑 |  | `/api/v3/copy/futures/position-summary` | `getCopyFuturesPositionSummary` |  |
|  | GET | 🔑 |  | `/api/v3/copy/futures/trading-pairs` | `getCopyFuturesTradingPairs` |  |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/copy/futures/transfer` | `copyFuturesTransfer` | CopyFuturesTransferRequestV3 |
|  | GET | 🔑 |  | `/api/v3/copy/futures/transfer-record` | `getCopyFuturesTransferRecords` | GetCopyFuturesTransferRecordRequestV3 |

## v3 · earn — Earn — savings · elite · sharkfin · loan  ·  8 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v3/earn/elite-assets` | `getEarnEliteAssets` |  |
|  | GET | 🔑 |  | `/api/v3/earn/elite-product` | `getEarnEliteProducts` |  |
|  | GET | 🔑 |  | `/api/v3/earn/elite-records` | `getEarnEliteRecords` | GetEarnEliteRecordsRequestV3 |
|  | POST | 🔑 |  | `/api/v3/earn/elite-redeem` | `redeemEarnElite` | RedeemEarnEliteRequestV3 |
|  | GET | 🔑 |  | `/api/v3/earn/elite-redeem-info` | `getEarnEliteRedeemInfo` | GetEarnEliteRedeemInfoRequestV3 |
|  | POST | 🔑 |  | `/api/v3/earn/elite-subscribe` | `subscribeEarnElite` | EarnEliteSubscribeRequestV3 |
|  | GET | 🔑 |  | `/api/v3/earn/elite-subscribe-info` | `getEarnEliteSubscribeInfo` | GetEarnEliteSubscribeInfoRequestV3 |
|  | GET | 🔑 |  | `/api/v3/earn/elite-subscribe-result` | `getEarnEliteSubscribeResult` | GetEarnEliteSubscribeResultRequestV3 |

## v3 · ins-loan — Institutional Loan (VIP)  ·  9 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 |  | `/api/v3/ins-loan/bind-uid` | `bindLoanUid` | BindUidRequestV3 |
|  | GET | 🔑 |  | `/api/v3/ins-loan/ensure-coins-convert` | `getLoanMarginCoinInfo` | GetEnsureCoinsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/ins-loan/loan-order` | `getLoanOrder` | GetLoanOrderRequestV3 |
|  | GET | 🔑 |  | `/api/v3/ins-loan/ltv-convert` | `getLoanLTVConvert` | GetLTVConvertRequestV3 |
|  | GET | 🔑 |  | `/api/v3/ins-loan/product-infos` | `getLoanProductInfo` | GetProductInfosRequestV3 |
|  | GET | 🔑 |  | `/api/v3/ins-loan/repaid-history` | `getLoanRepaidHistory` | GetRepaidHistoryRequestV3 |
|  | GET | 🔑 |  | `/api/v3/ins-loan/risk-unit` | `getLoanRiskUnit` |  |
|  | GET | 🔑 |  | `/api/v3/ins-loan/symbols` | `getLoanSymbols` | GetSymbolsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/ins-loan/transfered` | `getLoanTransfered` | GetTransferedRequestV3 |

## v3 · loan — Crypto Loan  ·  11 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/loan/borrow` | `loanBorrow` | LoanBorrowRequestV3 |
|  | GET | 🔑 |  | `/api/v3/loan/borrow-history` | `getLoanBorrowHistory` | GetLoanBorrowHistoryRequestV3 |
|  | GET | 🔑 |  | `/api/v3/loan/borrow-ongoing` | `getLoanBorrowOngoing` | GetLoanBorrowOngoingRequestV3 |
|  | GET | 🔑 |  | `/api/v3/loan/coins` | `getLoanCoins` | GetLoanCoinsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/loan/debts` | `getLoanDebts` |  |
|  | GET | 🔑 |  | `/api/v3/loan/interest` | `getLoanInterest` | GetLoanInterestRequestV3 |
|  | GET | 🔑 |  | `/api/v3/loan/pledge-rate-history` | `getLoanPledgeRateHistory` | GetLoanPledgeRateHistoryRequestV3 |
|  | GET | 🔑 |  | `/api/v3/loan/reduces` | `getLoanReduces` | GetLoanReducesRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/loan/repay` | `loanRepay` | LoanRepayRequestV3 |
|  | GET | 🔑 |  | `/api/v3/loan/repay-history` | `getLoanRepayHistory` | GetLoanRepayHistoryRequestV3 |
|  | POST | 🔑 |  | `/api/v3/loan/revise-pledge` | `loanRevisePledge` | LoanRevisePledgeRequestV3 |

## v3 · market — Market data (v3 unifié)  ·  34 endpoints (2 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | — |  | `/api/v3/market/candles` | `getCandles` | GetCandlesRequestV3 |
|  | GET | — |  | `/api/v3/market/cash-dividend-records` | `getCashDividendRecords` | GetCashDividendRecordsRequestV3 |
|  | GET | — |  | `/api/v3/market/current-fund-rate` | `getCurrentFundingRate` | GetCurrentFundingRateRequestV3 |
|  | GET | — |  | `/api/v3/market/discount-rate` | `getDiscountRate` |  |
|  | GET | — |  | `/api/v3/market/fee-group` | `getMarketFeeGroup` | GetMarketFeeGroupRequestV3 |
|  | GET | — |  | `/api/v3/market/fills` | `getFills` | GetPublicFillsRequestV3 |
|  | GET | — |  | `/api/v3/market/futures-account-long-short` | `getFuturesAccountLongShort` | GetFuturesTradingDataRequestV3 |
| ✅ | GET | — |  | `/api/v3/market/futures-active-buy-sell` | `getFuturesActiveBuySell` | GetFuturesTradingDataRequestV3 |
|  | GET | — |  | `/api/v3/market/futures-long-short` | `getFuturesLongShort` | GetFuturesTradingDataRequestV3 |
|  | GET | — |  | `/api/v3/market/futures-position-long-short` | `getFuturesPositionLongShort` | GetFuturesTradingDataRequestV3 |
|  | GET | — |  | `/api/v3/market/history-candles` | `getHistoryCandles` | GetHistoryCandlesRequestV3 |
|  | GET | — |  | `/api/v3/market/history-fund-rate` | `getHistoryFundingRate` | GetHistoryFundingRateRequestV3 |
|  | GET | — |  | `/api/v3/market/index-components` | `getIndexComponents` | GetIndexComponentsRequestV3 |
|  | GET | — |  | `/api/v3/market/instruments` | `getInstruments` | GetInstrumentsRequestV3 |
| ✅ | GET | — |  | `/api/v3/market/liquidations` | `getLiquidations` | GetLiquidationsRequestV3 |
|  | GET | — |  | `/api/v3/market/margin-isolated-borrow` | `getMarginIsolatedBorrow` | GetMarginIsolatedBorrowRequestV3 |
|  | GET | — |  | `/api/v3/market/margin-loan-growth` | `getMarginLoanGrowth` | GetMarginLoanGrowthRequestV3 |
|  | GET | — |  | `/api/v3/market/margin-loans` | `getMarginLoans` | GetMarginLoansRequestV3 |
|  | GET | — |  | `/api/v3/market/margin-long-short` | `getMarginLongShort` | GetMarginLongShortRequestV3 |
|  | GET | — |  | `/api/v3/market/oi-limit` | `getContractsOi` | GetContractsOiRequestV3 |
|  | GET | — |  | `/api/v3/market/open-interest` | `getOpenInterest` | GetOpenInterestRequestV3 |
|  | GET | — |  | `/api/v3/market/orderbook` | `getOrderBook` | GetOrderBookRequestV3 |
|  | GET | — |  | `/api/v3/market/position-tier` | `getPositionTier` | GetPositionTierRequestV3 |
|  | GET | — |  | `/api/v3/market/proof-of-reserves` | `getProofOfReserves` |  |
|  | GET | — |  | `/api/v3/market/risk-reserve` | `getRiskReserve` | GetRiskReserveRequestV3 |
|  | GET | — |  | `/api/v3/market/risk-reserve-all` | `getRiskReserveAll` | GetRiskReserveAllRequestV3 |
|  | GET | — |  | `/api/v3/market/risk-reserve-hour` | `getRiskReserveHour` | GetRiskReserveRequestV3 |
|  | GET | — |  | `/api/v3/market/rpi-orderbook` | `getRpiOrderBook` | GetRpiOrderBookRequestV3 |
|  | GET | — |  | `/api/v3/market/rpi-symbols` | `getRpiSymbols` |  |
|  | GET | — |  | `/api/v3/market/score-weights` | `getMarketScoreWeights` | GetMarketScoreWeightsRequestV3 |
|  | GET | — |  | `/api/v3/market/spot-fund-flow` | `getSpotFundFlow` | GetSpotFundFlowRequestV3 |
|  | GET | — |  | `/api/v3/market/spot-net-flow` | `getSpotNetFlow` | GetSpotNetFlowRequestV3 |
|  | GET | — |  | `/api/v3/market/spot-whale-flow` | `getSpotWhaleFlow` | GetSpotWhaleFlowRequestV3 |
|  | GET | — |  | `/api/v3/market/tickers` | `getTickers` | GetTickersRequestV3 |

## v3 · p2p — P2P — annonces, ordres, marchands  ·  18 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 |  | `/api/v3/p2p/ad-create` | `createP2pAd` | CreateP2pAdRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/ad-info` | `getP2pAdInfo` | GetP2pAdInfoRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/ad-limit` | `getP2pAdLimit` | GetP2pAdLimitRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/ad-list` | `getP2pAdList` | GetP2pAdListRequestV3 |
|  | POST | 🔑 |  | `/api/v3/p2p/ad-operate` | `operateP2pAd` | OperateP2pAdRequestV3 |
|  | POST | 🔑 |  | `/api/v3/p2p/ad-update` | `updateP2pAd` | UpdateP2pAdRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/all-orders` | `getP2pAllOrders` | GetP2pAllOrdersRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/balance` | `getP2pBalance` | GetP2pBalanceRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/currencies` | `getP2pCurrencies` |  |
|  | GET | 🔑 |  | `/api/v3/p2p/exchange-rate` | `getP2pExchangeRate` | GetP2pExchangeRateRequestV3 |
|  | POST | 🔑 |  | `/api/v3/p2p/fee-simulate` | `simulateP2pFee` | P2pFeeSimulateRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/my-ads` | `getP2pMyAds` | GetP2pMyAdsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/order-info` | `getP2pOrderInfo` | GetP2pOrderInfoRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/p2p/order-pay` | `confirmP2pOrderPayment` | P2pOrderActionRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/p2p/order-release` | `releaseP2pOrderAsset` | P2pOrderActionRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/pay-method` | `getP2pPayMethods` |  |
|  | GET | 🔑 |  | `/api/v3/p2p/pending-orders` | `getP2pPendingOrders` | GetP2pPendingOrdersRequestV3 |
|  | GET | 🔑 |  | `/api/v3/p2p/user-info` | `getP2pUserInfo` |  |

## v3 · position — Position (v3 unifié)  ·  3 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v3/position/adlRank` | `getPositionAdlRank` |  |
|  | GET | 🔑 |  | `/api/v3/position/current-position` | `getCurrentPosition` | GetCurrentPositionRequestV3 |
|  | GET | 🔑 |  | `/api/v3/position/history-position` | `getPositionHistory` | GetPositionHistoryRequestV3 |

## v3 · public — Public — annonces, heure serveur  ·  1 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | — |  | `/api/v3/public/time` | `getServerTime` |  |

## v3 · tax — Tax — relevés fiscaux  ·  1 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | GET | 🔑 |  | `/api/v3/tax/records` | `getTaxRecords` | GetTaxRecordsRequestV3 |

## v3 · trade — Trade (v3 unifié) — ordres, stratégies, batch  ·  21 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/batch-modify-order` | `batchModifyOrders` | BatchModifyOrderRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/cancel-batch` | `cancelBatchOrders` | CancelBatchOrdersRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/cancel-order` | `cancelOrder` | CancelOrderRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/cancel-reality-order` | `cancelRealityOrder` | CancelRealityOrderRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/cancel-strategy-order` | `cancelStrategyOrder` | CancelStrategyOrderRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/cancel-symbol-order` | `cancelAllOrders` | CancelAllOrdersRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/close-positions` | `closeAllPositions` | CloseAllPositionsRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/countdown-cancel-all` | `countdownCancelAll` | CountdownCancelAllRequestV3 |
|  | GET | 🔑 |  | `/api/v3/trade/fills` | `getTradeFills` | GetFillsRequestV3 |
|  | GET | 🔑 |  | `/api/v3/trade/history-orders` | `getHistoryOrders` | GetHistoryOrdersRequestV3 |
|  | GET | 🔑 |  | `/api/v3/trade/history-strategy-orders` | `getHistoryStrategyOrders` | GetHistoryStrategyOrdersRequestV3 |
|  | GET | 🔑 |  | `/api/v3/trade/loan-data` | `getLoanData` |  |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/modify-order` | `modifyOrder` | ModifyOrderRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/modify-strategy-order` | `modifyStrategyOrder` | ModifyStrategyOrderRequestV3 |
|  | GET | 🔑 |  | `/api/v3/trade/order-info` | `getOrderInfo` | GetOrderInfoRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/place-batch` | `placeBatchOrders` | PlaceBatchOrdersRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/place-order` | `submitNewOrder` | PlaceOrderRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/place-reality-order` | `placeRealityOrder` | PlaceRealityOrderRequestV3 |
|  | POST | 🔑 | ⚙️EXEC | `/api/v3/trade/place-strategy-order` | `submitStrategyOrder` | PlaceStrategyOrderRequestV3 |
|  | GET | 🔑 |  | `/api/v3/trade/unfilled-orders` | `getUnfilledOrders` | GetUnfilledOrdersRequestV3 |
|  | GET | 🔑 |  | `/api/v3/trade/unfilled-strategy-orders` | `getUnfilledStrategyOrders` | GetUnfilledStrategyOrdersRequestV3 |

## v3 · user — User — sous-comptes virtuels/agent  ·  8 endpoints (0 câblés)

| Bot | Verbe | Auth | ⚑ | Endpoint | Méthode SDK | Type params |
|---|---|---|---|---|---|---|
|  | POST | 🔑 |  | `/api/v3/user/create-sub` | `createSubAccount` | CreateSubAccountRequestV3 |
|  | POST | 🔑 |  | `/api/v3/user/create-sub-api` | `createSubAccountApiKey` | CreateSubAccountApiKeyRequestV3 |
|  | POST | 🔑 |  | `/api/v3/user/delete-sub-api` | `deleteSubAccountApiKey` | DeleteSubAccountApiKeyRequestV3 |
|  | POST | 🔑 |  | `/api/v3/user/freeze-sub` | `freezeSubAccount` | FreezeSubAccountRequestV3 |
|  | POST | 🔑 |  | `/api/v3/user/sub-account/agent-create` | `createAgentSubAccount` | CreateAgentSubAccountRequestV3 |
|  | GET | 🔑 |  | `/api/v3/user/sub-api-list` | `getSubAccountApiKeys` | GetSubAccountApiKeysRequestV3 |
|  | GET | 🔑 |  | `/api/v3/user/sub-list` | `getSubAccountList` | GetSubAccountListRequestV3 |
|  | POST | 🔑 |  | `/api/v3/user/update-sub-api` | `updateSubAccountApiKey` | UpdateSubAccountApiKeyRequestV3 |

