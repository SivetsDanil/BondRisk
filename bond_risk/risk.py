import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext


BASIS_POINT = Decimal('0.0001')
LIMIT = Decimal('1000000000000')
CENT = Decimal('0.01')
MAX_POSITIONS = 100


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class Bond:
    isin: str
    name: str
    currency: str
    face_value: Decimal
    quote_percent: Decimal
    fx_to_rub: Decimal
    coupon_type: str
    modified_duration: Decimal = None
    convexity: Decimal = None
    payments_per_year: int = None
    source: str = ''


def normalize_isin(value):
    return value.strip().upper() if isinstance(value, str) else ''


def is_valid_isin(isin):
    if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', isin):
        return False
    digits = ''.join(char if char.isdigit() else str(ord(char) - 55) for char in isin)
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char) * (2 if index % 2 else 1)
        total += digit - 9 if digit > 9 else digit
    return total % 10 == 0


def parse_amount(value, mode):
    if not isinstance(value, (str, float, int)) or isinstance(value, bool):
        raise InputError('Введите количество или стоимость позиции.')
    if not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?', str(value)):
        raise InputError('Введите количество или стоимость позиции числом.')
    try:
        amount = Decimal(str(value).replace(',', '.'))
    except InvalidOperation as error:
        raise InputError('Введите количество или стоимость позиции числом.') from error
    if not 0 < abs(amount) <= LIMIT:
        raise InputError('Введите ненулевое число по модулю не больше 10¹².')
    if mode == 'quantity' and amount != amount.to_integral_value():
        raise InputError('Количество бумаг должно быть целым.')
    if mode == 'rub' and amount != amount.quantize(CENT):
        raise InputError('Введите стоимость с точностью до копеек.')
    return amount


def calculate_position(position, find_bond):
    if not isinstance(position, dict):
        raise InputError('Некорректная позиция.')
    isin = normalize_isin(position.get('isin'))
    if not is_valid_isin(isin):
        raise InputError('Проверьте ISIN и его контрольную цифру.')
    bond = find_bond(isin)
    if bond is None:
        raise InputError('В выбранном справочнике нет бумаги с таким ISIN.')
    mode = position.get('mode')
    if mode not in ('quantity', 'rub'):
        raise InputError('Выберите способ ввода позиции.')
    amount = parse_amount(position.get('amount'), mode)

    if bond.coupon_type == 'floating' and bond.payments_per_year:
        duration = Decimal(1) / bond.payments_per_year
        convexity = Decimal(0)
    elif bond.coupon_type == 'fixed' and bond.modified_duration is not None and bond.convexity is not None:
        duration = bond.modified_duration
        convexity = bond.convexity
    else:
        raise InputError('В справочнике отсутствуют параметры риска для этой бумаги.')

    fair_value = amount
    if mode == 'quantity':
        fair_value *= bond.face_value * (bond.quote_percent / 100) * bond.fx_to_rub
    dv01 = fair_value * (-duration * BASIS_POINT + convexity / 2 * BASIS_POINT ** 2)
    return {'isin': isin, 'fairValue': fair_value, 'duration': duration,
            'convexity': convexity, 'dv01': dv01}


def calculate_scenario(positions, find_bond):
    if not isinstance(positions, list) or not positions:
        raise InputError('Добавьте хотя бы одну позицию.')
    if len(positions) > MAX_POSITIONS:
        raise InputError(f'Допустимо до {MAX_POSITIONS} позиций.')

    with localcontext() as context:
        context.prec = 44
        rows = []
        for index, position in enumerate(positions, start=1):
            try:
                rows.append(calculate_position(position, find_bond))
            except InputError as error:
                raise InputError(f'Позиция {index}. {error}') from error
        return {'rows': rows, 'total': sum(row['dv01'] for row in rows)}
