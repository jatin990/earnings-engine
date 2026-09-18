import React from 'react';

export interface DealRecord {
  deal_date: string;
  symbol: string;
  client_name: string;
  buyer_name?: string | null;
  seller_name?: string | null;
  direction: 'BUY' | 'SELL';
  quantity: number;
  trade_price: number;
  value_cr: number;
  deal_type: string;
  exchange: string;
}

export interface InflowMetrics {
  symbol: string;
  asof_date: string;
  horizon_days: number;
  window_start?: string;
  total_buy_cr: number;
  total_sell_cr: number;
  net_inflow_cr: number;
  total_deals: number;
  sentiment: 'ACCUMULATION' | 'DISTRIBUTION' | 'NEUTRAL';
}

interface StockBlockDealsProps {
  deals: DealRecord[];
  inflowMetrics?: InflowMetrics;
  loading?: boolean;
}

export const StockBlockDeals: React.FC<StockBlockDealsProps> = ({
  deals,
  inflowMetrics,
  loading = false,
}) => {
  if (loading) {
    return (
      <div className="p-8 text-center text-slate-400 bg-slate-900 border border-slate-800 rounded-xl animate-pulse">
        Loading institutional block deals and flow metrics...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Institutional Flow Summary Metrics Card */}
      {inflowMetrics && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-5 bg-slate-900 border border-slate-800 rounded-xl">
          <div>
            <div className="text-xs font-medium text-slate-400">Analysis Window</div>
            <div className="text-lg font-semibold text-slate-100 mt-0.5">
              {inflowMetrics.horizon_days} Days
            </div>
            <div className="text-[11px] text-slate-500">
              {inflowMetrics.window_start ? `From ${inflowMetrics.window_start}` : `Up to ${inflowMetrics.asof_date}`}
            </div>
          </div>

          <div>
            <div className="text-xs font-medium text-slate-400">Total Bought</div>
            <div className="text-lg font-semibold text-emerald-400 mt-0.5">
              ₹{inflowMetrics.total_buy_cr.toLocaleString(undefined, { minimumFractionDigits: 2 })} Cr
            </div>
            <div className="text-[11px] text-slate-500">Institutional Purchases</div>
          </div>

          <div>
            <div className="text-xs font-medium text-slate-400">Total Sold</div>
            <div className="text-lg font-semibold text-rose-400 mt-0.5">
              ₹{inflowMetrics.total_sell_cr.toLocaleString(undefined, { minimumFractionDigits: 2 })} Cr
            </div>
            <div className="text-[11px] text-slate-500">Institutional Selling</div>
          </div>

          <div>
            <div className="text-xs font-medium text-slate-400">Net Flow & Sentiment</div>
            <div
              className={`text-lg font-bold mt-0.5 ${
                inflowMetrics.net_inflow_cr >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {inflowMetrics.net_inflow_cr >= 0 ? '+' : ''}
              ₹{inflowMetrics.net_inflow_cr.toLocaleString(undefined, { minimumFractionDigits: 2 })} Cr
            </div>
            <div className="mt-1">
              <span
                className={`inline-block text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded ${
                  inflowMetrics.sentiment === 'ACCUMULATION'
                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                    : inflowMetrics.sentiment === 'DISTRIBUTION'
                    ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                    : 'bg-slate-800 text-slate-300'
                }`}
              >
                {inflowMetrics.sentiment}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Deals Data Table */}
      <div className="overflow-x-auto border border-slate-800 rounded-xl bg-slate-900 shadow-sm">
        <table className="w-full text-left text-sm text-slate-300">
          <thead className="bg-slate-800/70 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-800">
            <tr>
              <th className="py-3 px-4">Date</th>
              <th className="py-3 px-4">Participant / Client</th>
              <th className="py-3 px-4">Type</th>
              <th className="py-3 px-4">Action</th>
              <th className="py-3 px-4 text-right">Quantity</th>
              <th className="py-3 px-4 text-right">Avg Price (₹)</th>
              <th className="py-3 px-4 text-right">Value (₹ Cr)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {deals && deals.length > 0 ? (
              deals.map((deal, idx) => {
                const displayName = deal.client_name || deal.buyer_name || deal.seller_name || 'Participant';
                const isBuy = deal.direction === 'BUY';

                return (
                  <tr key={`${deal.deal_date}-${deal.client_name}-${idx}`} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 whitespace-nowrap text-slate-400 font-mono text-xs">
                      {deal.deal_date}
                    </td>
                    <td className="py-3 px-4 font-medium text-slate-100 max-w-xs truncate" title={displayName}>
                      {displayName}
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 text-[11px] font-mono rounded bg-slate-800 text-slate-400 border border-slate-700">
                        {deal.deal_type}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded ${
                          isBuy
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                            : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                        }`}
                      >
                        {deal.direction}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-slate-200">
                      {deal.quantity.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-slate-200">
                      ₹{deal.trade_price.toFixed(2)}
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-semibold text-slate-100">
                      ₹{deal.value_cr.toFixed(2)}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={7} className="text-center py-12 text-slate-500">
                  <div className="flex flex-col items-center justify-center space-y-1">
                    <span>No block or bulk deals recorded for this period.</span>
                    <span className="text-xs text-slate-600">Institutional transactions will appear here when filed with the exchange.</span>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
