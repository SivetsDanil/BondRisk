import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree

from .risk import Bond, InputError, is_valid_isin, normalize_isin


CBR_URL = 'https://www.cbr.ru/scripts/XML_daily.asp'
MARKET_FIELDS = {'isin', 'name', 'currency', 'face_value', 'quote_percent', 'coupon_type',
                 'modified_duration', 'convexity', 'payments_per_year', 'source'}


def cbr_rates(requested_date):
    address = f'{CBR_URL}?{urlencode({"date_req": requested_date.strftime("%d/%m/%Y")})}'
    try:
        with urlopen(address, timeout=15) as response:
            content = response.read(512 * 1024 + 1)
        if len(content) > 512 * 1024:
            raise ValueError('превышен размер ответа')
        return parse_cbr_rates(content, requested_date)
    except (OSError, ValueError, ElementTree.ParseError, InvalidOperation) as error:
        raise InputError(f'Не удалось загрузить дневные курсы Банка России: {error}') from error


def parse_cbr_rates(content, requested_date):
    root = ElementTree.fromstring(content)
    actual = datetime.strptime(root.get('Date', ''), '%d.%m.%Y').date()
    if root.tag != 'ValCurs' or actual > requested_date:
        raise ValueError('курсы вернулись с некорректной датой')
    rates = {'RUB': Decimal(1)}
    for item in root.findall('Valute'):
        code = item.findtext('CharCode', '').strip()
        nominal = parse_number(item.findtext('Nominal', ''), 'Nominal', minimum=Decimal('1'))
        value = parse_number(item.findtext('Value', ''), 'Value', minimum=Decimal('0.000000000001'))
        rates[code] = value / nominal
    if len(rates) < 2:
        raise ValueError('возвращён пустой справочник курсов')
    return actual, rates


def parse_number(value, field, minimum=None):
    try:
        result = Decimal(value.strip().replace(',', '.'))
    except InvalidOperation as error:
        raise InputError(f'Укажите числовое значение поля {field}.') from error
    if not result.is_finite() or abs(result) > Decimal('1e12') or (minimum is not None and result < minimum):
        raise InputError(f'Поле {field} вне допустимого диапазона.')
    return result


def load_market_csv(path, rates):
    bonds = []
    seen = set()
    with path.open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        if not MARKET_FIELDS.issubset(reader.fieldnames or []):
            missing = ', '.join(sorted(MARKET_FIELDS - set(reader.fieldnames or [])))
            raise InputError(f'В CSV нет столбцов: {missing}.')
        for row in reader:
            try:
                if len(bonds) >= 5000:
                    raise InputError('Справочник может содержать до 5 000 бумаг.')
                if None in row or any(row[key] is None for key in MARKET_FIELDS):
                    raise InputError('Количество значений не соответствует столбцам CSV.')
                bond = parse_bond(row, rates)
                if bond.isin in seen:
                    raise InputError(f'ISIN {bond.isin} повторяется.')
                seen.add(bond.isin)
                bonds.append(bond)
            except InputError as error:
                raise InputError(f'Строка {reader.line_num}. {error}') from error
    if not bonds:
        raise InputError('CSV не содержит облигаций.')
    return bonds


def parse_bond(row, rates):
    isin = normalize_isin(row['isin'])
    if not is_valid_isin(isin) or 'DEMO' in isin:
        raise InputError('Укажите действительный ISIN с контрольной цифрой.')
    name, source = row['name'].strip(), row['source'].strip()
    if not name or not source:
        raise InputError('Укажите название и источник рыночных параметров.')
    currency = row['currency'].strip().upper()
    if not re.fullmatch('[A-Z]{3}', currency) or currency not in rates:
        raise InputError(f'Для валюты {currency} нет курса.')
    positive = Decimal('0.00000001')
    face = parse_number(row['face_value'], 'face_value', minimum=positive)
    quote = parse_number(row['quote_percent'], 'quote_percent', minimum=positive)
    kind = row['coupon_type'].strip().lower()
    if kind == 'fixed':
        duration = parse_number(row['modified_duration'], 'modified_duration', minimum=Decimal(0))
        convexity = parse_number(row['convexity'], 'convexity')
        return Bond(isin, name, currency, face, quote, rates[currency], kind, duration, convexity, source=source)
    if kind == 'floating':
        payments = row['payments_per_year'].strip()
        if not re.fullmatch(r'[1-9]\d?', payments):
            raise InputError('Для плавающего купона укажите от 1 до 99 выплат в год.')
        return Bond(isin, name, currency, face, quote, rates[currency], kind,
                    payments_per_year=int(payments), source=source)
    raise InputError('Тип купона должен быть fixed или floating.')
