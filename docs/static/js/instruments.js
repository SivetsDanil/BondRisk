(async function () {
  'use strict';

  const list = document.getElementById('instruments');
  const status = document.getElementById('instruments-status');
  const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 });

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  try {
    const { dataset, instruments } = await window.bondRisk.loadCatalog();
    document.getElementById('dataset-label').textContent = dataset === 'demo' ? 'Тестовые данные' : 'Рыночный снимок';
    if (!instruments.length) {
      status.textContent = 'В справочнике пока нет облигаций.';
      return;
    }

    const rows = instruments.map(instrument => {
      const name = element('strong', instrument.name, 'name');
      const isin = element('span', `${instrument.isin} · ${instrument.currency}`, 'isin-id');
      const coupon = instrument.coupon_type === 'floating' ? 'плавающий купон' : 'фиксированный купон';
      const terms = element('p', `Номинал ${number.format(instrument.face_value)} ${instrument.currency} · котировка ${number.format(instrument.quote_percent)}% · ${coupon}`, 'hint');
      const details = element('div');
      details.append(name, isin, terms);

      const link = element('a', 'К расчёту', 'button button-primary');
      link.href = `./index.html?isin=${encodeURIComponent(instrument.isin)}`;
      link.setAttribute('aria-label', `Открыть расчёт для ${instrument.isin}`);
      const row = element('li');
      row.append(details, link);
      return row;
    });
    list.append(...rows);
    list.hidden = false;
    status.hidden = true;
  } catch (error) {
    status.textContent = error.message || 'Не удалось загрузить справочник.';
  }
})();
