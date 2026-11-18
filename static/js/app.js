(function () {
  'use strict';

  const $ = id => document.getElementById(id);
  const currency = new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB' });
  const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 });
  const money = value => currency.format(Math.abs(value) < 0.005 ? 0 : value);
  const signedMoney = value => value >= 0.005 ? `+${money(value)}` : money(value);
  const maxPositions = Number(document.body.dataset.maxPositions);
  const instruments = new Map();
  const findInstrument = isin => instruments.get(isin);
  let positions = [];
  let editing = -1;
  let revision = 0;
  let result = null;
  let calculating = false;
  let loading = true;
  let marketRevision = null;

  async function request(path, options) {
    const response = await fetch(path, options);
    if (!response.ok && !response.headers.get('Content-Type')?.includes('application/json')) {
      throw new Error('Сервер сейчас недоступен. Повторите попытку.');
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? 'Ошибка сервера.');
    return data;
  }

  function node(tag, label, className) {
    const element = document.createElement(tag);
    if (label !== undefined) element.textContent = label;
    if (className) element.className = className;
    return element;
  }

  function syncFields() {
    const isin = $('isin').value.trim().toUpperCase();
    const instrument = findInstrument(isin);
    const rubMode = $('mode').value === 'rub';
    $('amount-label').textContent = rubMode ? 'Стоимость позиции, ₽' : 'Количество бумаг';
    $('amount').placeholder = rubMode ? 'Например, 9 500' : 'Например, 10';
    $('instrument-info').hidden = !instrument;
    $('position-preview').hidden = true;
    if (!instrument) return;

    $('instrument-name').textContent = instrument.name;
    const coupon = instrument.coupon_type === 'floating'
      ? `Плавающий купон · выплат в год: ${instrument.payments_per_year}` : 'Фиксированный купон';
    const quote = `${number.format(instrument.quote_percent)}%`;
    const face = `${number.format(instrument.face_value)} ${instrument.currency}`;
    const fx = `${number.format(instrument.fx_to_rub)} ₽`;
    const source = instrument.source ? ` · ${instrument.source}` : '';
    $('instrument-terms').textContent = `${coupon} · номинал ${face} · котировка ${quote} · курс ${fx}${source}`;
    const amount = parseAmount();
    if (!rubMode && isValidAmount(amount, 'quantity')) {
      const position = { isin, mode: 'quantity', amount };
      $('position-preview').textContent = `Стоимость позиции ${money(previewValue(position))}`;
      $('position-preview').hidden = false;
    }
  }

  function clearError() {
    $('form-error').hidden = true;
    $('isin').removeAttribute('aria-invalid');
    $('amount').removeAttribute('aria-invalid');
  }

  function showFormError(message, field) {
    $('form-error').textContent = message;
    $('form-error').hidden = false;
    if (field) {
      field.setAttribute('aria-invalid', 'true');
      field.focus();
    }
  }

  function parseAmount() {
    const raw = $('amount').value.trim().replace(/^−/, '-');
    if (!/^[+-]?(?:\d+|\d{1,3}(?:[ \u00a0\u202f]\d{3})+)(?:[.,]\d+)?$/.test(raw)) return '';
    return raw.replace(/[ \u00a0\u202f]/g, '').replace(',', '.');
  }

  function isValidAmount(amount, mode) {
    if (!amount || Number(amount) === 0 || Math.abs(Number(amount)) > 1e12) return false;
    const fraction = (amount.split('.')[1] ?? '').replace(/0+$/, '');
    return fraction.length <= (mode === 'quantity' ? 0 : 2);
  }

  function isValidIsin(isin) {
    if (!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin)) return false;
    const digits = isin.replace(/[A-Z]/g, letter => String(letter.charCodeAt(0) - 55));
    const total = Array.from(digits).reverse().reduce((sum, digit, index) => {
      const value = Number(digit) * (index % 2 ? 2 : 1);
      return sum + (value > 9 ? value - 9 : value);
    }, 0);
    return total % 10 === 0;
  }

  function previewValue(position) {
    const instrument = findInstrument(position.isin);
    if (position.mode === 'rub') return Number(position.amount);
    return Number(position.amount) * instrument.face_value * (instrument.quote_percent / 100) * instrument.fx_to_rub;
  }

  function resetForm() {
    $('position-form').reset();
    editing = -1;
    $('form-heading').textContent = 'Новая позиция';
    $('save-position').textContent = 'Добавить позицию';
    $('cancel-edit').hidden = true;
    clearError();
    syncFields();
    renderResult();
  }

  function addOrUpdate(event) {
    event.preventDefault();
    clearError();
    const isin = $('isin').value.trim().toUpperCase();
    if (!isValidIsin(isin)) return showFormError('Проверьте ISIN и его контрольную цифру.', $('isin'));
    if (!findInstrument(isin)) return showFormError('В выбранном справочнике нет бумаги с таким ISIN.', $('isin'));
    if (editing === -1 && positions.length >= maxPositions) {
      return showFormError(`Допустимо до ${maxPositions} позиций.`);
    }

    const position = { isin, mode: $('mode').value, amount: parseAmount() };
    if (!isValidAmount(position.amount, position.mode)) {
      const message = position.mode === 'quantity'
        ? 'Введите целое ненулевое количество бумаг по модулю не больше 10¹².'
        : 'Введите ненулевую сумму с точностью до копеек по модулю не больше 10¹².';
      return showFormError(message, $('amount'));
    }
    if (editing === -1) positions.push(position);
    else positions[editing] = position;
    resetForm();
    positionsChanged();
    $('isin').focus();
  }

  function editPosition(index) {
    editing = index;
    const position = positions[index];
    $('isin').value = position.isin;
    $('mode').value = position.mode;
    $('amount').value = String(position.amount).replace('.', ',');
    $('form-heading').textContent = 'Редактирование позиции';
    $('save-position').textContent = 'Сохранить изменения';
    $('cancel-edit').hidden = false;
    clearError();
    syncFields();
    renderResult();
    $('isin').focus();
  }

  function removePosition(index) {
    positions.splice(index, 1);
    if (editing === index) resetForm();
    else if (editing > index) editing -= 1;
    positionsChanged();
    $('isin').focus();
  }

  function positionsChanged() {
    revision += 1;
    result = null;
    render();
  }

  function render() {
    $('position-count').textContent = positions.length;
    $('position-count').setAttribute('aria-label', `Количество позиций: ${positions.length}`);
    $('positions-empty').hidden = positions.length > 0;
    $('table-wrapper').hidden = positions.length === 0;
    renderResult();

    $('position-rows').replaceChildren(...positions.map((position, index) => {
      const instrument = findInstrument(position.isin);
      const row = node('tr');
      const bond = node('td');
      bond.append(node('span', instrument.name, 'name'), node('span', position.isin, 'isin-id'));
      const amount = position.mode === 'quantity' ? `${number.format(position.amount)} шт.` : 'Прямой ввод';
      const side = position.amount < 0 ? 'Шорт' : 'Лонг';
      const input = node('td');
      input.dataset.label = 'Позиция';
      input.append(node('span', amount, 'num'), node('span', side, 'isin-id'));
      const values = result?.rows[index];
      const actions = node('td');
      actions.dataset.label = 'Действия';
      const group = node('div', undefined, 'row-actions');
      const edit = node('button', 'Изменить', 'row-button');
      edit.type = 'button';
      edit.setAttribute('aria-label', `Изменить позицию ${index + 1}, ${position.isin}`);
      edit.addEventListener('click', () => editPosition(index));
      const remove = node('button', 'Удалить', 'row-button remove');
      remove.type = 'button';
      remove.setAttribute('aria-label', `Удалить позицию ${index + 1}, ${position.isin}`);
      remove.addEventListener('click', () => removePosition(index));
      group.append(edit, remove);
      actions.append(group);
      const cost = node('td', money(values?.fairValue ?? previewValue(position)), 'num');
      cost.dataset.label = 'Стоимость';
      const dv01 = node('td', values ? signedMoney(values.dv01) : '—', 'num');
      dv01.dataset.label = 'DV01';
      row.append(bond, input, cost, dv01, actions);
      return row;
    }));
  }

  function renderResult() {
    $('calculate').disabled = loading || calculating || editing !== -1 || positions.length === 0;
    const value = $('result-value');
    const detail = $('result-detail');
    value.textContent = result ? signedMoney(result.total) : '—';
    value.dataset.sign = result?.total <= -0.005 ? 'negative' : '';

    if (calculating) detail.textContent = 'Выполняется расчёт…';
    else if (editing !== -1) detail.textContent = 'Сохраните или отмените правку перед расчётом.';
    else if (result?.total >= 0.005) detail.textContent = 'Оценка роста стоимости введённых позиций.';
    else if (result?.total <= -0.005) detail.textContent = 'Оценка снижения стоимости введённых позиций.';
    else if (result) detail.textContent = 'Изменение стоимости меньше 0,005 ₽ по модулю.';
    else if (positions.length) detail.textContent = 'Запустите расчёт для текущих позиций.';
    else detail.textContent = 'Добавьте позицию и запустите расчёт.';
  }

  async function runCalculation() {
    const activeRevision = revision;
    calculating = true;
    render();
    let errorMessage;
    try {
      const calculated = await request('/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions, revision: marketRevision }),
      });
      if (activeRevision === revision) result = calculated;
    } catch (error) {
      result = null;
      errorMessage = error.message;
    } finally {
      calculating = false;
      render();
      if (activeRevision === revision && errorMessage) {
        $('result-detail').textContent = `Расчёт не выполнен. ${errorMessage}`;
      }
    }
  }

  function renderCatalog() {
    const visible = Array.from(instruments.values()).slice(0, 6);
    $('catalog').replaceChildren(...visible.map(instrument => {
      const button = node('button', undefined, 'catalog-item');
      button.type = 'button';
      const label = node('span');
      label.append(node('strong', instrument.name), node('span', instrument.isin, 'isin-id'));
      button.append(label, node('span', instrument.currency, 'currency'));
      button.addEventListener('click', () => {
        $('isin').value = instrument.isin;
        clearError();
        syncFields();
        $('amount').focus();
      });
      return button;
    }));
  }

  async function start() {
    $('save-position').disabled = true;
    $('load-example').disabled = true;
    try {
      const { dataset, snapshot, instruments: items } = await request('/api/instruments');
      if (!items.length) throw new Error('Рыночный справочник пуст. Импортируйте CSV и обновите страницу.');
      for (const instrument of items) instruments.set(instrument.isin, instrument);
      const selectedIsin = new URLSearchParams(window.location.search).get('isin');
      if (instruments.has(selectedIsin)) {
        $('isin').value = selectedIsin;
        syncFields();
      }
      if (snapshot) {
        marketRevision = snapshot.revision;
        $('dataset-label').textContent = `Рыночный снимок ${snapshot.market_date.split('-').reverse().join('.')}`;
      }
      if (items.length > 6) $('catalog-hint').textContent = 'Выберите бумагу из списка или введите другой ISIN из справочника.';
      renderCatalog();
      loading = false;
      $('save-position').disabled = false;
      $('load-example').hidden = dataset !== 'demo';
      $('load-example').disabled = dataset !== 'demo';
      render();
    } catch (error) {
      $('catalog-error').hidden = false;
      $('catalog-error').textContent = error.message || 'Не удалось загрузить справочник.';
    }
  }

  $('position-form').addEventListener('submit', addOrUpdate);
  $('isin').addEventListener('input', () => { clearError(); syncFields(); });
  $('amount').addEventListener('input', () => { clearError(); syncFields(); });
  $('mode').addEventListener('change', () => { clearError(); syncFields(); });
  $('cancel-edit').addEventListener('click', () => { resetForm(); $('isin').focus(); });
  $('calculate').addEventListener('click', runCalculation);
  $('load-example').addEventListener('click', () => {
    if (positions.length && !confirm('Заменить текущие позиции демонстрационным примером?')) return;
    positions = [
      { isin: 'RUDEMO000016', mode: 'quantity', amount: '10' },
      { isin: 'XSDEMO000020', mode: 'quantity', amount: '-2' },
    ];
    resetForm();
    positionsChanged();
  });

  start();
})();
