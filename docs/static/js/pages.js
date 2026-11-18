(function () {
  'use strict';

  const instruments = window.bondRiskDemo;
  const byIsin = new Map(instruments.map(instrument => [instrument.isin, instrument]));
  const basisPoint = 0.0001;

  async function request(path, options) {
    const response = await fetch(path, options);
    if (!response.ok && !response.headers.get('Content-Type')?.includes('application/json')) {
      throw new Error('Сервер сейчас недоступен. Повторите попытку.');
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? 'Ошибка сервера.');
    return data;
  }

  function loadCatalog() {
    return window.bondRiskServer ? request('/api/instruments') : { dataset: 'demo', snapshot: null, instruments };
  }

  function calculate(positions, revision) {
    if (window.bondRiskServer) {
      return request('/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions, revision }),
      });
    }

    const rows = positions.map(({ isin, mode, amount }) => {
      const instrument = byIsin.get(isin);
      if (!instrument) throw new Error('В тестовом справочнике нет бумаги с таким ISIN.');

      const floating = instrument.coupon_type === 'floating';
      const duration = floating ? 1 / instrument.payments_per_year : Number(instrument.modified_duration);
      const convexity = floating ? 0 : Number(instrument.convexity);
      const fairValue = mode === 'rub' ? Number(amount)
        : Number(amount) * instrument.face_value * (instrument.quote_percent / 100) * instrument.fx_to_rub;
      const dv01 = fairValue * (-duration * basisPoint + convexity / 2 * basisPoint ** 2);
      return { isin, fairValue, duration, convexity, dv01 };
    });
    return { rows, total: rows.reduce((sum, row) => sum + row.dv01, 0) };
  }

  window.bondRisk = { loadCatalog, calculate };
})();
